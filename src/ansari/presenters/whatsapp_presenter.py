import copy
from datetime import datetime
from typing import Any

import httpx

from ansari.agents.ansari import Ansari
from ansari.ansari_db import AnsariDB, MessageLogger
from ansari.ansari_logger import get_logger
from ansari.config import get_settings
from ansari.util.general_helpers import get_language_from_text

logger = get_logger()

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

    async def handle_text_message(
        self,
        from_whatsapp_number: str,
        incoming_msg_body: str,
    ) -> None:
        """Processes the incoming message and sends a response to the WhatsApp sender.

        Args:
            from_whatsapp_number (str): The sender's WhatsApp number.
            incoming_msg_body (str): The incoming message body from the sender.

        """
        try:
            logger.info(f"Whatsapp user said: {incoming_msg_body}")

            # Get user's ID from users_whatsapp table
            user_id_whatsapp = db.retrieve_user_info_whatsapp(from_whatsapp_number, "id")[0]

            # Get details of thread with latest updated_at column
            thread_id, last_message_time = db.get_last_message_time_whatsapp(user_id_whatsapp)

            # Create a new thread if 3+ hours have passed since last message
            if thread_id is None or (datetime.now() - last_message_time).total_seconds() > 3 * 60 * 60:
                first_few_words = " ".join(incoming_msg_body.split()[:6])
                thread_id = db.create_thread_whatsapp(user_id_whatsapp, first_few_words)

            # Store incoming message to current thread it's assigned to
            db.append_message_whatsapp(user_id_whatsapp, thread_id, {"role": "user", "content": incoming_msg_body})

            # Get `message_history` from current thread (including incoming message)
            message_history = db.get_thread_llm_whatsapp(thread_id, user_id_whatsapp)

            # Setting up `MessageLogger` for Ansari, so it can log (i.e., store) its response to the DB
            agent = copy.deepcopy(self.agent)
            agent.set_message_logger(MessageLogger(db, user_id_whatsapp, thread_id, to_whatsapp=True))

            # Get final response from Ansari by sending `message_history`
            # TODO (odyash, good_first_issue): change `stream` to False (and remove comprehensive loop)
            #   when `Ansari` is capable of handling it
            response = [tok for tok in agent.replace_message_history(message_history, stream=True) if tok]
            response = "".join(response)

            if response:
                await self.send_whatsapp_message(from_whatsapp_number, response)
            else:
                logger.warning("Response was empty. Sending error message.")
                await self.send_whatsapp_message(
                    from_whatsapp_number,
                    "Ansari returned an empty response. Please rephrase your question, then try again.",
                )
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await self.send_whatsapp_message(
                from_whatsapp_number,
                "An unexpected error occurred while processing your message. Please try again later.",
            )

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
            status = value["statuses"]["status"]
            timestamp = value["statuses"]["timestamp"]
            # This log isn't important if we don't want to track when an Ansari's replied message is
            # delivered to or read by the recipient
            logger.debug(
                f"WhatsApp status update received:\n({status} at {timestamp}.)",
            )
            return "status update"

        if "messages" not in value:
            error_msg = f"Unsupported message type received from WhatsApp user:\n{body}"
            logger.error(
                error_msg,
            )
            raise Exception(error_msg)

        logger.info(f"Received payload from WhatsApp user:\n{body}")
        incoming_msg = value["messages"][0]

        # Extract the business phone number ID from the webhook payload
        business_phone_number_id = value["metadata"]["phone_number_id"]
        # Extract the phone number of the WhatsApp sender
        from_whatsapp_number = incoming_msg["from"]
        # Meta API note: Meta sends "errors" key when receiving unsupported message types
        # (e.g., video notes, gifs sent from giphy, or polls)
        incoming_msg_type = incoming_msg["type"] if incoming_msg["type"] in incoming_msg.keys() else "errors"
        # Extract the message of the WhatsApp sender (could be text, image, etc.)
        incoming_msg_body = incoming_msg[incoming_msg_type]

        return (
            business_phone_number_id,
            from_whatsapp_number,
            incoming_msg_type,
            incoming_msg_body,
        )

    async def check_and_register_user(
        self,
        from_whatsapp_number: str,
        incoming_msg_type: str,
        incoming_msg_body: dict,
    ) -> None:
        """
        Checks if the user's phone number is stored in the users_whatsapp table.
        If not, registers the user with the preferred language.

        Args:
            from_whatsapp_number (str): The phone number of the WhatsApp sender.
            incoming_msg_type (str): The type of the incoming message (e.g., text, location).
            incoming_msg_body (dict): The body of the incoming message.

        Returns:
            None
        """
        # Check if the user's phone number is stored in users_whatsapp table
        if not db.account_exists_whatsapp(phone_num=from_whatsapp_number):
            if incoming_msg_type == "text":
                incoming_msg_text = incoming_msg_body["body"]
                user_lang = get_language_from_text(incoming_msg_text)
            else:
                # TODO (odyash, good_first_issue): use lightweight library/solution that gives us language from country code
                # instead of hardcoding "en" in below code
                user_lang = "en"
            db.register_whatsapp(from_whatsapp_number, {"preferred_language": user_lang})

    async def send_whatsapp_message(
        self,
        from_whatsapp_number: str,
        msg_body: str,
    ) -> None:
        """Sends a message to the WhatsApp sender.

        Args:
            from_whatsapp_number (str): The sender's WhatsApp number.
            msg_body (str): The message body to be sent.

        """
        url = self.meta_api_url
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        json_data = {
            "messaging_product": "whatsapp",
            "to": from_whatsapp_number,
            "text": {"body": msg_body},
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=json_data)
            response.raise_for_status()  # Raise an exception for HTTP errors
            logger.info(
                f"Ansari responsded to WhatsApp user: {from_whatsapp_number} with:\n{msg_body}",
            )
            logger.debug(
                f"So, status code and text of that WhatsApp response:\n{response.status_code}\n{response.text}",
            )

    async def handle_location_message(
        self,
        from_whatsapp_number: str,
        incoming_msg_body: dict,
    ) -> None:
        """
        Handles an incoming location message by updating the user's location in the database
        and sending a confirmation message.

        Args:
            from_whatsapp_number (str): The phone number of the WhatsApp sender.
            incoming_msg_body (dict): The body of the incoming location message.

        Returns:
            None
        """
        loc = incoming_msg_body
        db.update_user_whatsapp(from_whatsapp_number, {"loc_lat": loc["latitude"], "loc_long": loc["longitude"]})
        # TODO (odyash, good_first_issue): update msg below to also say something like:
        # 'Type "pt"/"prayer times" to get prayer times', then implement that feature
        await self.send_whatsapp_message(
            from_whatsapp_number,
            "Stored your location successfully! This will help us give you accurate prayer times ISA 🙌.",
        )

    async def handle_unsupported_message(
        self,
        from_whatsapp_number: str,
        incoming_msg_type: str,
    ) -> None:
        """
        Handles an incoming unsupported message by sending an appropriate response.

        Args:
            from_whatsapp_number (str): The phone number of the WhatsApp sender.
            incoming_msg_type (str): The type of the incoming message (e.g., image, video).

        Returns:
            None
        """
        msg_type = incoming_msg_type + "s" if not incoming_msg_type.endswith("s") else incoming_msg_type
        msg_type = msg_type.replace("unsupporteds", "this media type")
        await self.send_whatsapp_message(
            from_whatsapp_number,
            f"Sorry, I can't process {msg_type} yet. Please send me a text message.",
        )

    def present(self):
        pass
