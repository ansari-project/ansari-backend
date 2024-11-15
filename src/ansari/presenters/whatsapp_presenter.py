import copy
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ansari.ansari_logger import get_logger
from ansari.config import get_settings

logger = get_logger(__name__)


# Initialize FastAPI app
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class WhatsAppPresenter:
    def __init__(
        self,
        agent,
        access_token,
        business_phone_number_id,
        api_version="v21.0",
    ):
        self.agent = agent
        self.access_token = access_token
        self.meta_api_url = f"https://graph.facebook.com/{api_version}/{business_phone_number_id}/messages"

    async def process_and_reply_to_whatsapp_sender(
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
            agent = copy.deepcopy(self.agent)
            logger.info(f"User said: {incoming_msg_body}")

            # Process the input and get the final response
            response = [tok for tok in agent.process_input(incoming_msg_body) if tok]
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
            and (messages := value.get("messages", []))
            and (incoming_msg := messages[0])
        ):
            logger.error(
                f"Invalid received payload from WhatsApp user and/or problem with Meta's API :\n{body}",
            )
            return "error"
        if "statuses" in value:
            status = value["statuses"]["status"]
            timestamp = value["statuses"]["timestamp"]
            logger.debug(
                f"WhatsApp status update received:\n({status} at {timestamp}.)",
            )
            return "status update"
        logger.info(f"Received payload from WhatsApp user:\n{body}")

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

    def present(self):
        pass
