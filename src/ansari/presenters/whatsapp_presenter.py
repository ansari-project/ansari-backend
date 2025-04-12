# Unlike other files, the presenter's role here is just to provide functions for handling WhatsApp interactions

import re
from datetime import datetime, timezone
from typing import Any, Literal, Optional

import httpx

from ansari.agents.ansari import Ansari
from ansari.agents.ansari_claude import AnsariClaude
from ansari.ansari_db import AnsariDB, MessageLogger, SourceType
from ansari.ansari_logger import get_logger
from ansari.config import get_settings
from ansari.util.general_helpers import get_language_direction_from_text, get_language_from_text

logger = get_logger(__name__)

# Initialize the DB and agent
# TODO(odyash): A question for others: should I refer `db` of this file and `main_api.py` to a single instance of AnsariDB?
#    instead of duplicating `db` instances? Will this cost more resources?
db = AnsariDB(get_settings())


class WhatsAppPresenter:
    def __init__(
        self,
        agent: Ansari,
        access_token,
        business_phone_number_id,
        api_version="v21.0",
    ):
        self.settings = agent.settings
        self.access_token = access_token
        self.meta_api_url = f"https://graph.facebook.com/{api_version}/{business_phone_number_id}/messages"

    async def extract_relevant_whatsapp_message_details(
        self,
        body: dict[str, Any],
    ) -> tuple[str, str, str] | str | None:
        """Extracts relevant whatsapp message details from the incoming webhook payload.

        Args:
            body (Dict[str, Any]): The JSON body of the incoming request.

        Returns:
            Optional[Tuple[str, str, str]]: A tuple containing the business phone number ID,
            the sender's WhatsApp number and the their message (if the extraction is successful).
            Returns None if the extraction fails.

        """
        # logger.debug(f"Received payload from WhatsApp user:\n{body}")

        if not (
            body.get("object")
            and (entry := body.get("entry", []))
            and (changes := entry[0].get("changes", []))
            and (value := changes[0].get("value", {}))
        ):
            error_msg = f"Invalid received payload from WhatsApp user and/or problem with Meta's API :\n{body}"
            logger.error(
                error_msg,
            )
            raise Exception(error_msg)

        if "statuses" in value:
            # status = value["statuses"]["status"]
            # timestamp = value["statuses"]["timestamp"]
            # # This log isn't important if we don't want to track when an Ansari's replied message is
            # # delivered to or read by the recipient
            # logger.debug(
            #     f"WhatsApp status update received:\n({status} at {timestamp}.)",
            # )
            return "status update"

        if "messages" not in value:
            error_msg = f"Unsupported message type received from WhatsApp user:\n{body}"
            logger.error(
                error_msg,
            )
            raise Exception(error_msg)

        incoming_msg = value["messages"][0]

        # Extract the phone number of the WhatsApp sender
        user_whatsapp_number = incoming_msg["from"]
        # Meta API note: Meta sends "errors" key when receiving unsupported message types
        # (e.g., video notes, gifs sent from giphy, or polls)
        incoming_msg_type = incoming_msg["type"] if incoming_msg["type"] in incoming_msg.keys() else "errors"
        # Extract the message of the WhatsApp sender (could be text, image, etc.)
        incoming_msg_body = incoming_msg[incoming_msg_type]

        logger.info(f"Received a supported whatsapp message from {user_whatsapp_number}: {incoming_msg_body}")

        return (
            user_whatsapp_number,
            incoming_msg_type,
            incoming_msg_body,
        )

    async def check_and_register_user(
        self,
        user_whatsapp_number: str,
        incoming_msg_type: str,
        incoming_msg_body: dict,
    ) -> None:
        """
        Checks if the user's phone number is stored in the users table.
        If not, registers the user with the preferred language.

        Args:
            user_whatsapp_number (str): The phone number of the WhatsApp sender.
            incoming_msg_type (str): The type of the incoming message (e.g., text, location).
            incoming_msg_body (dict): The body of the incoming message.

        Returns:
            None
        """
        # Check if the user's phone number exists in users table
        if db.account_exists(phone_num=user_whatsapp_number):
            return True

        # Else, register the user with the detected language
        if incoming_msg_type == "text":
            incoming_msg_text = incoming_msg_body["body"]
            user_lang = get_language_from_text(incoming_msg_text)
        else:
            # TODO(odyash, good_first_issue): use lightweight library/solution that gives us language from country code
            # instead of hardcoding "en" in below code
            user_lang = "en"

        status: Literal["success", "failure"] = db.register(
            source=SourceType.WHATSAPP,
            phone_num=user_whatsapp_number,
            preferred_language=user_lang,
        )["status"]

        if status == "success":
            logger.info(f"Registered new whatsapp user (lang: {user_lang})!: {user_whatsapp_number}")
            return True
        else:
            logger.error(f"Failed to register new whatsapp user: {user_whatsapp_number}")
            return False

    async def send_whatsapp_message(
        self,
        user_whatsapp_number: str,
        msg_body: str,
    ) -> None:
        """Sends a message to the WhatsApp sender.

        Args:
            user_whatsapp_number (str): The sender's WhatsApp number.
            msg_body (str): The message body to be sent.

        """
        url = self.meta_api_url
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        # Split the message if it exceeds WhatsApp's character limit
        message_parts = self._split_long_messages(msg_body)

        try:
            async with httpx.AsyncClient() as client:
                logger.debug(f"SENDING REQUEST TO: {url}")

                logger.info(
                    f"Ansari responded to WhatsApp user {user_whatsapp_number} with the following message part(s):\n\n"
                )

                # If we have multiple parts, send them sequentially
                for part in message_parts:
                    json_data = {
                        "messaging_product": "whatsapp",
                        "to": user_whatsapp_number,
                        "text": {"body": part},
                    }

                    response = await client.post(url, headers=headers, json=json_data)
                    response.raise_for_status()  # Raise an exception for HTTP errors

                    if msg_body != "...":
                        logger.info("\n".join(f"[Part {i + 1}]: \n{part}" for i, part in enumerate(message_parts)))

        except Exception as e:
            logger.error(f"Error sending message: {e}. Details are in next log.")
            logger.exception(e)

    def _calculate_time_passed(self, last_message_time: Optional[datetime]) -> tuple[float, str]:
        if last_message_time is None:
            passed_time = float("inf")
        else:
            passed_time = (datetime.now(timezone.utc) - last_message_time).total_seconds()

        # Log the time passed since the last message
        if passed_time < 60:
            passed_time_logging = f"{passed_time:.1f}sec"
        elif passed_time < 3600:
            passed_time_logging = f"{passed_time / 60:.1f}mins"
        elif passed_time < 86400:
            passed_time_logging = f"{passed_time / 3600:.1f}hours"
        else:
            passed_time_logging = f"{passed_time / 86400:.1f}days"

        return passed_time, passed_time_logging

    def _get_retention_time_in_seconds(self) -> int:
        reten_hours = get_settings().WHATSAPP_CHAT_RETENTION_HOURS
        allowed_time = reten_hours * 60 * 60
        return allowed_time

    def _get_whatsapp_markdown(self, msg: str) -> str:
        """Convert conventional markdown syntax to WhatsApp's markdown syntax"""

        msg_direction = get_language_direction_from_text(msg)

        # Replace text surrounded with single "*" with "_"
        #   (as WhatsApp doesn't support italic text with "*"; it uses "_" instead)
        # Regex details:
        # (?<![\*_])  # Negative lookbehind: Ensures that the '*' is not preceded by '*' or '_'
        # \*          # Matches a literal '*'
        # ([^\*_]+?)  # Non-greedy match: Captures one or more characters that are not '*' or '_'
        #   "Captures" mean it can be obtained via \1 in the replacement string
        # \*          # Matches a literal '*'
        # (?![\*_])   # Negative lookahead: Ensures that the '*' is not followed by '*' or '_'
        pattern = re.compile(r"(?<![\*_])\*([^\*_]+?)\*(?![\*_])")
        msg = pattern.sub(r"_\1_", msg)

        # Replace "**" (markdown bold) with "*" (whatsapp bold)
        msg = msg.replace("**", "*")

        # Match headers (#*) (that doesn't have a space before it (i.e., in the middle of a text))
        #   where there's text directly after them
        # NOTE: the `\**_*` part is to neglect any */_ in the returned group (.*?)
        pattern = re.compile(r"(?! )#+ \**_*(.*?)\**_*\n(?!\n)")

        # Replace them with bold (*) and italic (_) markdown syntax
        #   and add extra newline (to leave space between header and content)
        msg = pattern.sub(r"*_\1_*\n\n", msg)

        # Match headers (#*) (that doesn't have a space before it (i.e., in the middle of a text))
        #   where there's another newline directly after them
        # NOTE: the `\**_*` part is to neglect any */_ in the returned group (.*?)
        pattern = re.compile(r"(?! )#+ \**_*(.*?)\**_*\n\n")

        # Replace them with bold (*) and italic (_) markdown syntax
        msg = pattern.sub(r"*_\1_*\n\n", msg)

        # As nested text always appears in left side, even if text is RTL, which could be confusing to the reader,
        #   we decided to manipulate the nesting symbols (i.e., \d+\. , * , - , etc) so that they appear in right side
        # NOTE: added "ltr" for consistency of formatting across different languages
        if msg_direction in ["ltr", "rtl"]:
            # Replace lines that start with (possibly indented) "- " or "* " with "-- "
            msg = re.sub(r"(\s*)[\*-] ", r"\1-- ", msg)

            # Replace the dot numbered lists (1. , etc.) with a dash (e.g., 1 - )
            msg = re.sub(r"(\s*)(\d+)(\.) ", r"\1\2 - ", msg, flags=re.MULTILINE)

        return msg

    def _split_long_messages(self, msg_body: str) -> list[str]:
        """Split long messages into smaller chunks based on formatted headers or other patterns.

        This method implements a multi-level splitting strategy for messages that exceed
        WhatsApp's character limit (4000):
        1. First tries to split by header pattern (*_HEADER_*)
        2. If that's not possible, tries to split by bold text (*BOLD*)
        3. Finally falls back to paragraph-based splitting

        Args:
            msg_body (str): The message body to split if necessary

        Returns:
            list[str]: A list of message chunks that can be sent separately

        Example:
            >>> msg = "*_First Header_*\nSome text here...\n\n*_Second Header_*\nMore text..."
            >>> _split_long_messages(msg)
            ['*_First Header_*\nSome text here...', '*_Second Header_*\nMore text...']
        """
        # WhatsApp character limit
        MAX_LENGTH = 4000

        # If message is already under the limit, return it as is
        if len(msg_body) <= MAX_LENGTH:
            return [msg_body]

        # Strategy 1: Try to split by formatted headers (*_HEADER_*)
        header_chunks = self._split_by_headers(msg_body, MAX_LENGTH)
        if len(header_chunks) > 1:
            return header_chunks

        # Strategy 2: Try to split by bold formatting (*BOLD*)
        bold_chunks = self._split_by_bold_text(msg_body, MAX_LENGTH)
        if len(bold_chunks) > 1:
            return bold_chunks

        # Strategy 3: Fall back to paragraph-based splitting
        return self._split_by_paragraphs(msg_body, MAX_LENGTH)

    def _split_by_headers(self, text: str, max_length: int) -> list[str]:
        """Split text by formatted header pattern (*_HEADER_*).

        Args:
            text (str): Text to split
            max_length (int): Maximum allowed length of each chunk

        Returns:
            list[str]: List of text chunks split by headers

        Example:
            >>> text = "Text before header\n*_First Header_*\nText\n\n*_Second Header_*\nMore text"
            >>> _split_by_headers(text, 1000)
            ['Text before header', '*_First Header_*\nText', '*_Second Header_*\nMore text']
        """
        # Look for *_HEADER_* pattern
        header_pattern = re.compile(r"\*_[^*_]+_\*")
        headers = list(header_pattern.finditer(text))

        # If we don't have multiple headers, we can't split effectively
        if not headers or len(headers) <= 1:
            return [text]

        chunks = []

        # Process each header as a potential chunk boundary
        for i, match in enumerate(headers):
            # For the first header, handle any text that comes before it
            if i == 0 and match.start() > 0:
                prefix = text[: match.start()]

                # Always include the text before the first header in its own message(s)
                # If it's too long, recursively split it
                if len(prefix) <= max_length:
                    chunks.append(prefix)
                else:
                    # If prefix is too long, split it using paragraph-based splitting
                    prefix_chunks = self._split_by_paragraphs(prefix, max_length)
                    chunks.extend(prefix_chunks)

            # Determine the end position for the chunk containing this header
            end_pos = headers[i + 1].start() if i < len(headers) - 1 else len(text)
            chunk = text[match.start() : end_pos]

            # If chunk fits within limit, add it directly
            if len(chunk) <= max_length:
                chunks.append(chunk)
            else:
                # Otherwise, try more aggressive splitting for this chunk
                # First try bold formatting, then paragraphs
                sub_chunks = self._split_by_bold_text(chunk, max_length)
                chunks.extend(sub_chunks)

        return chunks

    def _split_by_bold_text(self, text: str, max_length: int) -> list[str]:
        """Split text by looking for bold formatting (*TEXT*) patterns.

        This function splits text at bold formatting markers (*TEXT*) when the text
        exceeds the maximum length. It treats each bold pattern as a potential
        break point, always keeping the bold text with the content that follows it.

        Args:
            text (str): Text to split
            max_length (int): Maximum allowed length of each chunk

        Returns:
            list[str]: List of text chunks split by bold formatting

        Example:
            >>> text = "Some intro text\n*First bold section*\nMiddle content\n*Second bold*\nMore text"
            >>> _split_by_bold_text(text, 30)
            ['Some intro text', '*First bold section*\nMiddle content', '*Second bold*\nMore text']
        """
        if len(text) <= max_length:
            return [text]

        # Find *TEXT* patterns
        bold_pattern = re.compile(r"\*[^*]+\*")
        bold_matches = list(bold_pattern.finditer(text))

        # If we don't have enough bold patterns for effective splitting
        if not bold_matches or len(bold_matches) <= 1:
            return self._split_by_paragraphs(text, max_length)

        chunks = []

        # Process each bold pattern as a potential chunk boundary
        for i, match in enumerate(bold_matches):
            # For the first bold pattern, handle any text that comes before it
            if i == 0 and match.start() > 0:
                prefix = text[: match.start()]

                # Always include the text before the first bold pattern in its own message(s)
                # If it's too long, recursively split it
                if len(prefix) <= max_length:
                    chunks.append(prefix)
                else:
                    # If prefix is too long, split it using paragraph-based splitting
                    prefix_chunks = self._split_by_paragraphs(prefix, max_length)
                    chunks.extend(prefix_chunks)

            # Determine the end position for the chunk containing this bold pattern
            end_pos = bold_matches[i + 1].start() if i < len(bold_matches) - 1 else len(text)
            chunk = text[match.start() : end_pos]

            # If chunk fits within limit, add it directly
            if len(chunk) <= max_length:
                chunks.append(chunk)
            else:
                # Otherwise, fall back to paragraph splitting for this chunk
                sub_chunks = self._split_by_paragraphs(chunk, max_length)
                chunks.extend(sub_chunks)

        return chunks

    def _split_by_paragraphs(self, text: str, max_length: int) -> list[str]:
        """Split text by paragraphs or fall back to fixed-size chunks if needed.

        This method attempts to split text at natural paragraph breaks (double newlines). If paragraphs themselves are
        too long, it uses fixed-size chunk splitting as a fallback.

        Args:
            text (str): Text to split
            max_length (int): Maximum allowed length of each chunk

        Returns:
            list[str]: List of text chunks split by paragraphs or fixed chunks

        Example:
            >>> text = "This is paragraph 1.\\n\\nThis is paragraph 2.\\n\\nThis is a very long paragraph 3 that exceeds"
            >>> text += " the maximum length and will need to be split."
            >>> _split_by_paragraphs(text, 50)
            ['This is paragraph 1.', 'This is paragraph 2.', 'This is a very long paragraph 3 that exceeds the',
                ' maximum length and will need to be split.']
        """
        if len(text) <= max_length:
            return [text]

        chunks = []

        # Try splitting by paragraphs first (double newlines)
        paragraphs = re.split(r"\n\n+", text)

        if len(paragraphs) > 1:
            current = ""

            for para in paragraphs:
                # If adding this paragraph would exceed the limit
                if current and len(current) + len(para) + 2 > max_length:
                    chunks.append(current)
                    current = ""

                # If paragraph itself is too long, split it using fixed chunks
                if len(para) > max_length:
                    # Add any accumulated text first
                    if current:
                        chunks.append(current)
                        current = ""

                    # Use fixed-size chunk splitting for long paragraphs
                    para_chunks = self._split_by_fixed_chunks(para, max_length)
                    chunks.extend(para_chunks)
                else:
                    # Add paragraph to current chunk with proper separator
                    if current:
                        current += "\n\n" + para
                    else:
                        current = para

            # Don't forget the last chunk
            if current:
                chunks.append(current)

            return chunks
        else:
            # If text doesn't have paragraphs, use fixed-size chunk splitting
            return self._split_by_fixed_chunks(text, max_length)

    def _split_by_fixed_chunks(self, text: str, max_length: int) -> list[str]:
        """Split text into fixed-size chunks of maximum length.

        This is the simplest fallback approach, which just takes chunks of
        max_length characters until the entire text is processed.

        Args:
            text (str): Text to split
            max_length (int): Maximum allowed length of each chunk

        Returns:
            list[str]: List of text chunks of maximum length

        Example:
            >>> text = "This is a very long text that exceeds the maximum allowed length"
            >>> _split_by_fixed_chunks(text, 20)
            ['This is a very long ', 'text that exceeds the', ' maximum allowed len', 'gth']
        """
        # If text is already under the limit, return it as is
        if len(text) <= max_length:
            return [text]

        chunks = []

        # Simply take max_length characters at a time
        for i in range(0, len(text), max_length):
            chunks.append(text[i : i + max_length])

        return chunks

    async def handle_text_message(
        self,
        user_whatsapp_number: str,
        incoming_txt_msg: str,
    ) -> None:
        """Processes the incoming text message and sends a response to the WhatsApp sender.

        Args:
            user_whatsapp_number (str): The sender's WhatsApp number.
            incoming_txt_msg (str): The incoming text message from the sender.

        """
        try:
            logger.debug(f"Whatsapp user said: {incoming_txt_msg}")

            # Get user's ID from users_whatsapp table
            # NOTE: we're not checking for user's existence here, as we've already done that in `main_webhook()`
            user_id_whatsapp = db.retrieve_user_info(source=SourceType.WHATSAPP, phone_num=user_whatsapp_number)

            # Get details of the thread that the user last interacted with (i.e., max(updated_at))
            thread_id, last_msg_time = db.get_last_message_time_whatsapp(user_id_whatsapp)

            # Calculate the time passed since the last message
            passed_time, passed_time_logging = self._calculate_time_passed(last_msg_time)
            logger.debug(f"Time passed since user ({user_id_whatsapp})'s last whatsapp message: {passed_time_logging}")

            # Get the allowed retention time
            allowed_time = self._get_retention_time_in_seconds()

            # Create a new thread if
            #   no threads have been previously created,
            #   or the last message has passed the allowed retention time
            # NOTE: Technically, the `thread_id` condition is redundant,
            #   as `passed_time` will be `inf` when `last_message_time` is None, which happens when `thread_id` is None
            #   ... but we're keeping the condition for clarity and future-proofing :]
            if thread_id is None or passed_time > allowed_time:
                first_few_words = " ".join(incoming_txt_msg.split()[:6])

                result: dict = db.create_thread(SourceType.WHATSAPP, user_id_whatsapp, first_few_words)

                if "error" in result:
                    logger.error(f"Error creating a new thread for whatsapp user ({user_id_whatsapp}): {result['error']}")
                    await self.send_whatsapp_message(
                        user_whatsapp_number,
                        "An unexpected error occurred while creating a new chat session. Please try again later.",
                    )
                    return

                thread_id = result["thread_id"]

                logger.info(
                    f"Created a new thread for the whatsapp user ({user_id_whatsapp}), "
                    + "as the allowed retention time has passed."
                )

            # Get `message_history` from current thread (excluding incoming user's message, as it will be logged later)
            thread_name_and_history = db.get_thread_llm(thread_id, user_id_whatsapp)
            if "messages" not in thread_name_and_history:
                logger.error(f"Error retrieving message history for thread ({thread_id}) of user ({user_id_whatsapp})")
                await self.send_whatsapp_message(
                    user_whatsapp_number,
                    "An unexpected error occurred while getting your last chat session. Please try again later.",
                )
                return

            msg_history: list[dict] = thread_name_and_history["messages"]

            msg_history_for_debugging = [msg for msg in msg_history if msg["role"] in {"user", "assistant"}]
            logger.debug(
                f"#msgs (user/assistant only) retrieved for user ({user_id_whatsapp})'s current whatsapp thread: "
                + str(len(msg_history_for_debugging))
            )

            user_msg = {"role": "user", "content": [{"type": "text", "text": incoming_txt_msg}]}
            msg_history.append(user_msg)

            message_logger = MessageLogger(db, SourceType.WHATSAPP, user_id_whatsapp, thread_id)
            if self.settings.AGENT == "Ansari":
                agent = Ansari(settings=self.settings, message_logger=message_logger)
            elif self.settings.AGENT == "AnsariClaude":
                agent = AnsariClaude(settings=self.settings, message_logger=message_logger)

            # Send the thread's history to the Ansari agent which will
            #   log (i.e., append) the message history's last user message to DB,
            #   process the history,
            #   log (i.e., append) Ansari's output to DB,
            response = [tok for tok in agent.replace_message_history(msg_history)]
            response = "".join(response)

            # Convert conventional markdown syntax to WhatsApp's markdown syntax
            logger.debug(f"Response before markdown conversion: \n\n{response}")
            response = self._get_whatsapp_markdown(response)

            # Return the response back to the WhatsApp user if it's not empty
            #   Else, send an error message to the user
            if response:
                await self.send_whatsapp_message(user_whatsapp_number, response)
            else:
                logger.warning("Response was empty. Sending error message.")
                await self.send_whatsapp_message(
                    user_whatsapp_number,
                    "Ansari returned an empty response. Please rephrase your question, then try again.",
                )
        except Exception as e:
            logger.error(f"Error processing message: {e}. Details are in next log.")
            logger.exception(e)
            await self.send_whatsapp_message(
                user_whatsapp_number,
                "An unexpected error occurred while processing your message. Please try again later.",
            )

    # NOTE: This function assumes `loc_lat` and `loc_long` columns are in `users` DB table
    #   If alternative columns are used (e.g., city), the function should be updated accordingly
    async def handle_location_message(
        self,
        user_whatsapp_number: str,
        incoming_msg_body: dict,
    ) -> None:
        """
        Handles an incoming location message by updating the user's location in the database
        and sending a confirmation message.

        Args:
            user_whatsapp_number (str): The phone number of the WhatsApp sender.
            incoming_msg_body (dict): The body of the incoming location message.

        Returns:
            None
        """
        loc = incoming_msg_body
        db.update_user_by_phone_num(user_whatsapp_number, {"loc_lat": loc["latitude"], "loc_long": loc["longitude"]})
        # TODO(odyash, good_first_issue): update msg below to also say something like:
        # 'Type "pt"/"prayer times" to get prayer times', then implement that feature
        await self.send_whatsapp_message(
            user_whatsapp_number,
            "Stored your location successfully!",  # This will help us give you accurate prayer times ISA 🙌.
        )

    async def handle_unsupported_message(
        self,
        user_whatsapp_number: str,
        incoming_msg_type: str,
    ) -> None:
        """
        Handles an incoming unsupported message by sending an appropriate response.

        Args:
            user_whatsapp_number (str): The phone number of the WhatsApp sender.
            incoming_msg_type (str): The type of the incoming message (e.g., image, video).

        Returns:
            None
        """
        msg_type = incoming_msg_type + "s" if not incoming_msg_type.endswith("s") else incoming_msg_type
        msg_type = msg_type.replace("unsupporteds", "this media type")
        await self.send_whatsapp_message(
            user_whatsapp_number,
            f"Sorry, I can't process {msg_type} yet. Please send me a text message.",
        )

    def present(self):
        pass
