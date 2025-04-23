# Unlike other files, the presenter's role here is just to provide functions for handling WhatsApp interactions

import re
import asyncio
import time
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
db = AnsariDB(get_settings())


class WhatsAppPresenter:
    def __init__(
        self,
        agent: Ansari | None = None,
        access_token: str | None = None,
        business_phone_number_id: str | None = None,
        api_version: str = "v22.0",
        user_whatsapp_number: str | None = None,
        incoming_msg_type: str | None = None,
        incoming_msg_body: dict | None = None,
        message_id: str | None = None,
        message_unix_time: int | None = None,
    ):
        if agent:
            self.settings = agent.settings
        else:
            self.settings = get_settings()

        self.access_token = access_token
        self.business_phone_number_id = business_phone_number_id
        self.api_version = api_version
        self.meta_api_url = f"https://graph.facebook.com/{api_version}/{business_phone_number_id}/messages"

        # User-specific fields
        self.user_whatsapp_number = user_whatsapp_number
        self.incoming_msg_type = incoming_msg_type
        self.incoming_msg_body = incoming_msg_body
        self.message_id = message_id
        self.message_unix_time = message_unix_time
        self.typing_indicator_task = None
        self.first_indicator_time = None

    @classmethod
    def create_user_specific_presenter(
        cls,
        general_presenter,
        user_whatsapp_number: str,
        incoming_msg_type: str,
        incoming_msg_body: dict,
        message_id: str,
        message_unix_time: int | None = None,
    ):
        """Creates a user-specific presenter instance from a general presenter."""
        return cls(
            access_token=general_presenter.access_token,
            business_phone_number_id=general_presenter.business_phone_number_id,
            api_version=general_presenter.api_version,
            user_whatsapp_number=user_whatsapp_number,
            incoming_msg_type=incoming_msg_type,
            incoming_msg_body=incoming_msg_body,
            message_id=message_id,
            message_unix_time=message_unix_time,
        )

    async def extract_relevant_whatsapp_message_details(
        self,
        body: dict[str, Any],
    ) -> tuple[bool, str | None, str | None, dict | None, str | None, int | None]:
        """Extracts relevant whatsapp message details from the incoming webhook payload.

        Args:
            body (Dict[str, Any]): The JSON body of the incoming request.

        Returns:
            tuple[bool, Optional[str], Optional[str], Optional[dict], Optional[str], Optional[int]]:
                A tuple of:
                (is_status, user_whatsapp_number, incoming_msg_type, incoming_msg_body, message_id, message_unix_time)

        Raises:
            Exception: If the payload structure is invalid or unsupported.
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
            return True, None, None, None, None, None
        else:
            is_status = False

        # should never be entered
        if "messages" not in value:
            error_msg = f"Unsupported message type received from WhatsApp user:\n{body}"
            logger.error(
                error_msg,
            )
            raise Exception(error_msg)

        incoming_msg = value["messages"][0]

        # Extract and store the message ID for use in send_whatsapp_typing_indicator
        message_id = incoming_msg.get("id")
        # Extract the phone number of the WhatsApp sender
        user_whatsapp_number = incoming_msg["from"]
        # Extract timestamp from message (in Unix time format) and convert to int if present
        message_unix_time_str = incoming_msg.get("timestamp")
        message_unix_time = int(message_unix_time_str) if message_unix_time_str is not None else None
        # Meta API note: Meta sends "errors" key when receiving unsupported message types
        # (e.g., video notes, gifs sent from giphy, or polls)
        incoming_msg_type = incoming_msg["type"] if incoming_msg["type"] in incoming_msg.keys() else "errors"
        # Extract the message of the WhatsApp sender (could be text, image, etc.)
        incoming_msg_body = incoming_msg[incoming_msg_type]

        logger.info(f"Received a supported whatsapp message from {user_whatsapp_number}: {incoming_msg_body}")

        return (is_status, user_whatsapp_number, incoming_msg_type, incoming_msg_body, message_id, message_unix_time)

    async def check_and_register_user(self) -> bool:
        """
        Checks if the user's phone number is stored in the users table.
        If not, registers the user with the preferred language.

        Returns:
            bool: True if user exists or was successfully registered, False otherwise.
        """
        if not self.user_whatsapp_number:
            logger.error("User WhatsApp number not set in presenter instance")
            return False

        # Check if the user's phone number exists in users table
        if db.account_exists(phone_num=self.user_whatsapp_number):
            return True

        # Else, register the user with the detected language
        if self.incoming_msg_type == "text":
            incoming_msg_text = self.incoming_msg_body["body"]
            user_lang = get_language_from_text(incoming_msg_text)
        else:
            # TODO(odyash, good_first_issue): use lightweight library/solution that gives us language from country code
            # instead of hardcoding "en" in below code
            user_lang = "en"

        status: Literal["success", "failure"] = db.register(
            source=SourceType.WHATSAPP,
            phone_num=self.user_whatsapp_number,
            preferred_language=user_lang,
        )["status"]

        if status == "success":
            logger.info(f"Registered new whatsapp user (lang: {user_lang})!: {self.user_whatsapp_number}")
            return True
        else:
            logger.error(f"Failed to register new whatsapp user: {self.user_whatsapp_number}")
            return False

    async def send_typing_indicator_then_start_loop(self) -> None:
        """Sends a typing indicator and starts a loop to periodically send more while processing the message."""
        if not self.user_whatsapp_number or not self.message_id:
            logger.error("Cannot start typing indicator loop: missing user_whatsapp_number or message_id")
            return

        self.first_indicator_time = time.time()

        # Send the initial typing indicator
        await self._send_whatsapp_typing_indicator()

        # Start an async task that will keep sending typing indicators
        self.typing_indicator_task = asyncio.create_task(self._typing_indicator_loop())

    async def _typing_indicator_loop(self) -> None:
        """Loop that periodically sends typing indicators while processing a message."""
        MAX_DURATION_SECONDS = 300  # 5 minutes maximum
        INDICATOR_INTERVAL_SECONDS = 26  # Send indicator every 26 seconds

        try:
            while True:
                logger.debug("Currently in typing indicator loop (i.e., Ansari is taking longer than usual to respond)")
                # Sleep for the interval
                await asyncio.sleep(INDICATOR_INTERVAL_SECONDS)

                # Check if we've exceeded the maximum duration
                elapsed_time = time.time() - self.first_indicator_time
                if elapsed_time > MAX_DURATION_SECONDS:
                    logger.warning(f"Typing indicator loop exceeded maximum duration of {MAX_DURATION_SECONDS}s. Stopping.")
                    break

                # If we're still processing the message, send another typing indicator
                logger.debug(f"Sending follow-up typing indicator after {elapsed_time:.1f}s")
                await self._send_whatsapp_typing_indicator()

        except asyncio.CancelledError:
            logger.debug("cancelling asyncio task...")
        except Exception as e:
            logger.error(f"Error in typing indicator loop: {e}")
            logger.exception(e)

    async def _send_whatsapp_typing_indicator(self) -> None:
        """Sends a typing indicator to the WhatsApp sender."""
        if not self.user_whatsapp_number or not self.message_id:
            logger.error("Cannot send typing indicator: missing user_whatsapp_number or message_id")
            return

        url = self.meta_api_url
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient() as client:
                logger.debug(f"SENDING TYPING INDICATOR REQUEST TO: {url}")

                json_data = {
                    "messaging_product": "whatsapp",
                    "status": "read",
                    "message_id": self.message_id,
                    "typing_indicator": {"type": "text"},
                }

                response = await client.post(url, headers=headers, json=json_data)
                response.raise_for_status()  # Raise an exception for HTTP errors

                logger.debug(f"Sent typing indicator to WhatsApp user {self.user_whatsapp_number}")

        except Exception as e:
            logger.error(f"Error sending typing indicator: {e}. Details are in next log.")
            logger.exception(e)

    async def send_whatsapp_message(self, msg_body: str) -> None:
        """Sends a message to the WhatsApp sender.

        Args:
            msg_body (str): The message body to be sent.
        """
        if not self.user_whatsapp_number:
            logger.error("Cannot send message: missing user_whatsapp_number")
            return

        url = self.meta_api_url
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        # Split the message if it exceeds WhatsApp's character limit
        message_parts = self._split_long_messages(msg_body)

        # Stop the typing indicator before sending the actual message
        if self.typing_indicator_task and not self.typing_indicator_task.done():
            logger.debug("Typing indicator loop was cancelled (as Ansari will respond now)")
            self.typing_indicator_task.cancel()

        # Send the message(s) to the user
        try:
            async with httpx.AsyncClient() as client:
                logger.debug(f"SENDING REQUEST TO: {url}")

                logger.info(
                    f"Ansari responded to WhatsApp user {self.user_whatsapp_number} with the following message part(s):\n\n"
                )

                # If we have multiple parts, send them sequentially
                for part in message_parts:
                    json_data = {
                        "messaging_product": "whatsapp",
                        "to": self.user_whatsapp_number,
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

        # Process standard markdown syntax
        msg = self._convert_italic_syntax(msg)
        msg = self._convert_bold_syntax(msg)
        msg = self._convert_headers(msg)

        # Process lists based on text direction
        if msg_direction in ["ltr", "rtl"]:
            msg = self._format_nested_lists(msg)

        return msg

    def _convert_italic_syntax(self, text: str) -> str:
        """Convert markdown italic syntax (*text*) to WhatsApp italic syntax (_text_)"""
        # Regex details:
        # (?<![\*_])  # Negative lookbehind: Ensures that the '*' is not preceded by '*' or '_'
        # \*          # Matches a literal '*'
        # ([^\*_]+?)  # Non-greedy match: Captures one or more characters that are not '*' or '_'
        # \*          # Matches a literal '*'
        # (?![\*_])   # Negative lookahead: Ensures that the '*' is not followed by '*' or '_'
        #
        # This pattern carefully identifies standalone italic markers (*text*) while avoiding
        # matching bold markers (**text**) or mixed formatting.
        pattern = re.compile(r"(?<![\*_])\*([^\*_]+?)\*(?![\*_])")
        return pattern.sub(r"_\1_", text)

    def _convert_bold_syntax(self, text: str) -> str:
        """Convert markdown bold syntax (**text**) to WhatsApp bold syntax (*text*)"""
        return text.replace("**", "*")

    def _convert_headers(self, text: str) -> str:
        """Convert markdown headers to WhatsApp's bold+italic format"""
        # Process headers with content directly after them
        # (?! )     # Ensures there's no space before the hash (avoiding matching in middle of text)
        # #+ \**_*  # Matches one or more hash symbols and ignores any bold/italic markers already present
        # (.*?)     # Captures the header text (non-greedy)
        # \**_*\n   # Matches any trailing formatting markers and the newline
        # (?!\n)    # Ensures the newline isn't followed by another newline (i.e., not an isolated header)
        pattern = re.compile(r"(?! )#+ \**_*(.*?)\**_*\n(?!\n)")
        text = pattern.sub(r"*_\1_*\n\n", text)

        # Process headers with empty line after them
        pattern = re.compile(r"(?! )#+ \**_*(.*?)\**_*\n\n")
        return pattern.sub(r"*_\1_*\n\n", text)

    def _format_nested_lists(self, text: str) -> str:
        """
        Format only nested lists/bullet points with WhatsApp's special formatting.

        This handles:
        1. Nested bullet points within numbered lists
        2. Nested numbered lists within bullet points
        3. Purely nested bullet points
        4. Purely nested numbered lists

        Simple (non-nested) lists retain their original formatting.
        """
        lines = text.split("\n")
        processed_lines = []
        in_nested_section = False
        nested_section_indent = 0

        for i, line in enumerate(lines):
            # Check for indentation to detect nesting
            indent_match = re.match(r"^(\s+)", line) if line.strip() else None
            current_indent = len(indent_match.group(1)) if indent_match else 0

            # Check if this is a list item (numbered or bullet)
            is_numbered_item = re.match(r"^\s*\d+\.\s", line)
            is_bullet_item = re.match(r"^\s*[\*-]\s", line)

            # Determine if we're entering, in, or exiting a nested section
            if (is_numbered_item or is_bullet_item) and current_indent > 0:
                # This is a nested item
                if not in_nested_section:
                    in_nested_section = True
                    nested_section_indent = current_indent

                # Format nested items
                if is_numbered_item:
                    # Convert nested numbered list format: "  1. Item" -> "  1 - Item"
                    line = re.sub(r"(\s*)(\d+)(\.) ", r"\1\2 - ", line)
                elif is_bullet_item:
                    # Convert nested bullet format: "  - Item" or "  * Item" -> "  -- Item"
                    line = re.sub(r"(\s*)[\*-] ", r"\1-- ", line)

            elif in_nested_section and current_indent < nested_section_indent:
                # We're exiting the nested section
                in_nested_section = False

            # For non-nested items, leave them as they are
            processed_lines.append(line)

        return "\n".join(processed_lines)

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

    async def handle_text_message(self) -> None:
        """Processes the incoming text message and sends a response to the WhatsApp sender."""
        incoming_txt_msg = self.incoming_msg_body["body"]

        try:
            logger.debug(f"Whatsapp user said: {incoming_txt_msg}")

            # Get user's ID from users_whatsapp table
            # NOTE: we're not checking for user's existence here, as we've already done that in `main_webhook()`
            user_id_whatsapp = db.retrieve_user_info(source=SourceType.WHATSAPP, phone_num=self.user_whatsapp_number)

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
            #   log (i.e., append) Ansari's output to DB
            response = ""
            for token in agent.replace_message_history(msg_history):
                # NOTE: Check the `async_await_backgroundtasks_visualized.md` file
                #   for details on why we added this `await` line
                await asyncio.sleep(0)
                response += token

            # Convert conventional markdown syntax to WhatsApp's markdown syntax
            logger.debug(f"Response before markdown conversion: \n\n{response}")
            response = self._get_whatsapp_markdown(response)

            # Return the response back to the WhatsApp user if it's not empty
            #   Else, send an error message to the user
            if response:
                await self.send_whatsapp_message(response)
            else:
                logger.warning("Response was empty. Sending error message.")
                await self.send_whatsapp_message(
                    "Ansari returned an empty response. Please rephrase your question, then try again.",
                )
        except Exception as e:
            logger.error(f"Error processing message: {e}. Details are in next log.")
            logger.exception(e)
            await self.send_whatsapp_message(
                "An unexpected error occurred while processing your message. Please try again later.",
            )

    # NOTE: This function assumes `loc_lat` and `loc_long` columns are in `users` DB table
    #   If alternative columns are used (e.g., city), the function should be updated accordingly
    async def handle_location_message(self) -> None:
        """
        Handles an incoming location message by updating the user's location in the database
        and sending a confirmation message.
        """

        loc = self.incoming_msg_body
        db.update_user_by_phone_num(self.user_whatsapp_number, {"loc_lat": loc["latitude"], "loc_long": loc["longitude"]})
        # TODO(odyash, good_first_issue): update msg below to also say something like:
        # 'Type "pt"/"prayer times" to get prayer times', then implement that feature
        await self.send_whatsapp_message(
            "Stored your location successfully!",  # This will help us give you accurate prayer times ISA 🙌.
        )

    async def handle_unsupported_message(
        self,
    ) -> None:
        """
        Handles an incoming unsupported message by sending an appropriate response.
        """

        msg_type = self.incoming_msg_type + "s" if not self.incoming_msg_type.endswith("s") else self.incoming_msg_type
        msg_type = msg_type.replace("unsupporteds", "this media type")
        await self.send_whatsapp_message(
            f"Sorry, I can't process {msg_type} yet. Please send me a text message.",
        )

    def is_message_too_old(self) -> bool:
        """
        Checks if the incoming message is older than the allowed threshold (24 hours).

        Uses the message_unix_time attribute (timestamp in Unix time format - seconds since epoch)
        extracted during message processing to determine if the message is too old.

        Returns:
            bool: True if the message is older than 24 hours, False otherwise
        """
        # Define the too old threshold (24 hours in seconds)
        TOO_OLD_THRESHOLD = 24 * 60 * 60  # 24 hours in seconds

        # If there's no timestamp, message can't be verified as too old
        if not self.message_unix_time:
            logger.debug("No timestamp available, cannot determine message age")
            return False

        # Convert the Unix timestamp to a datetime object
        try:
            msg_time = datetime.fromtimestamp(self.message_unix_time, tz=timezone.utc)
            # Get the current time in UTC
            current_time = datetime.now(timezone.utc)
            # Calculate time difference in seconds
            time_diff = (current_time - msg_time).total_seconds()

            # Log the message age for debugging
            if time_diff < 60:
                age_logging = f"{time_diff:.1f} seconds"
            elif time_diff < 3600:
                age_logging = f"{time_diff / 60:.1f} minutes"
            elif time_diff < 86400:
                age_logging = f"{time_diff / 3600:.1f} hours"
            else:
                age_logging = f"{time_diff / 86400:.1f} days"

            logger.debug(f"Message age: {age_logging}")

            # Return True if the message is older than the threshold
            return time_diff > TOO_OLD_THRESHOLD

        except (ValueError, TypeError) as e:
            logger.error(f"Error parsing message timestamp: {e}")
            return False

    def present(self):
        pass
