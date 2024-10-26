import copy
import logging

import requests
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings

# Initialize logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

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


class WhatsAppClient:
    def __init__(self, agent, access_token, phone_number_id, version="v13.0"):
        self.agent = agent
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.api_url = (
            f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
        )

    def send_message(self, to_whatsapp_number, message):
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        data = {
            "messaging_product": "whatsapp",
            "to": to_whatsapp_number,
            "type": "text",
            "text": {"body": message},
        }
        response = requests.post(self.api_url, headers=headers, json=data)
        logger.info(f"Sent message to {to_whatsapp_number}: {message}")
        logger.debug(f"Response: {response.status_code}, {response.text}")

    def process_message(self, from_whatsapp_number, message_body):
        try:
            agent = copy.deepcopy(self.agent)
            logger.info(f"User said: {message_body}")

            # Process the input and get the final response
            # TODO: uncomment below, and remove the response line below it
            # response = agent.process_input(message_body)
            response = (
                "AI RESPONSE UNTIL process_input CAN BE IMPLEMENTED WITHOUT STREAMING"
            )

            if response:
                self.send_message(from_whatsapp_number, response)
            else:
                logger.warning("Response was empty. Sending error message.")
                self.send_message(
                    from_whatsapp_number,
                    "Ansari returned an empty response. Please rephrase your question, then try again.",
                )
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            self.send_message(
                from_whatsapp_number,
                "An unexpected error occurred while processing your message. Please try again later.",
            )


class WhatsAppPresenter:
    def __init__(self, agent, access_token, phone_number_id, version):
        self.agent = agent
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.version = version
        self.client = WhatsAppClient(agent, access_token, phone_number_id, version)

    def present(self):
        @app.post("/whatsapp")
        async def whatsapp_webhook(request: Request):
            data = await request.json()
            for entry in data.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    messages = value.get("messages", [])
                    for message in messages:
                        from_whatsapp_number = message["from"]
                        message_body = message["text"]["body"]
                        self.client.process_message(from_whatsapp_number, message_body)
            return {"status": "received"}

        # # Start the webhook
        # import uvicorn

        # uvicorn.run(app, host="0.0.0.0", port=8000)
