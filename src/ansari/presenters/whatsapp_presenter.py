# Unlike other files, the presenter's role here is just to provide functions for handling WhatsApp interactions

import copy
import re
from datetime import datetime
from typing import Any, Literal, Optional

import httpx

from ansari.agents.ansari import Ansari
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
        self.agent = agent
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
        json_data = {
            "messaging_product": "whatsapp",
            "to": user_whatsapp_number,
            "text": {"body": msg_body},
        }

        async with httpx.AsyncClient() as client:
            logger.debug(f"SENDING REQUEST TO: {url}")
            response = await client.post(url, headers=headers, json=json_data)
            response.raise_for_status()  # Raise an exception for HTTP errors
            if msg_body != "...":
                logger.info(
                    f"Ansari responsded to WhatsApp user: {user_whatsapp_number} with:\n{msg_body}",
                )

    def _calculate_time_passed(self, last_message_time: Optional[datetime]) -> tuple[float, str]:
        if last_message_time is None:
            passed_time = float("inf")
        else:
            passed_time = (datetime.now() - last_message_time).total_seconds()

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
            user_id_whatsapp = db.retrieve_user_info(source=SourceType.WHATSAPP, phone_num=user_whatsapp_number)[0]

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

            # Append the user's message to the history retrieved from the DB
            user_msg = db.convert_message_llm(["user", incoming_txt_msg, None, None, None])[0]
            msg_history.append(user_msg)

            # Setup `MessageLogger` for Ansari, so it can log user's/Ansari's message to DB
            agent = copy.deepcopy(self.agent)
            agent.set_message_logger(MessageLogger(db, SourceType.WHATSAPP, user_id_whatsapp, thread_id))

            # Send the thread's history to the Ansari agent which will
            #   log (i.e., append) the message history's last user message to DB,
            #   process the history,
            #   log (i.e., append) Ansari's output to DB,
            # TODO(odyash, good_first_issue): change `stream` to False (and remove comprehensive loop)
            #   when `Ansari` is capable of handling it
            response = [tok for tok in agent.replace_message_history(msg_history, stream=True) if tok]
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
