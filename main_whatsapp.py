import logging
import os
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from agents.ansari import Ansari
from config import get_settings
from presenters.whatsapp_presenter import WhatsAppPresenter

# Initialize logging
logger = logging.getLogger(__name__)
logging_level = get_settings().LOGGING_LEVEL.upper()
logger.setLevel(logging_level)

# Initialize FastAPI app
app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Initialize the agent
ansari = Ansari(get_settings())

# Initialize the presenter with the agent and credentials
presenter = WhatsAppPresenter(
    agent=ansari,
    access_token=get_settings().WHATSAPP_ACCESS_TOKEN_FROM_SYS_USER.get_secret_value(),
    business_phone_number_id=get_settings().WHATSAPP_BUSINESS_PHONE_NUMBER_ID.get_secret_value(),
    api_version=get_settings().WHATSAPP_API_VERSION,
)
presenter.present()

if __name__ == "__main__":
    # Start a Uvicorn server to run the FastAPI application
    # Note: if you instead run
    #   uvicorn main_whatsapp:app --host YOUR_HOST --port YOUR_PORT
    # in the terminal, then this block will be ignored
    filename_without_extension = os.path.splitext(os.path.basename(__file__))[0]
    uvicorn.run(
        f"{filename_without_extension}:app", host="127.0.0.1", port=8000, reload=True
    )


@app.get("/whatsapp/v1")
async def verification_webhook(request: Request) -> Optional[str]:
    """
    Handles the WhatsApp webhook verification request.

    Args:
        request (Request): The incoming HTTP request.

    Returns:
        Optional[str]: The challenge string if verification is successful, otherwise raises an HTTPException.
    """
    mode = request.query_params.get("hub.mode")
    verify_token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode and verify_token:
        if (
            mode == "subscribe"
            and verify_token
            == get_settings().WHATSAPP_VERIFY_TOKEN_FOR_WEBHOOK.get_secret_value()
        ):
            logger.info("WHATSAPP WEBHOOK VERIFIED SUCCESFULLY!")
            # Tricky note: apparently, you have to wrap the challenge in an HTMLResponse
            # in order for meta to accept and verify the callback
            # source: https://stackoverflow.com/a/74394602/13626137
            return HTMLResponse(challenge)
        else:
            raise HTTPException(status_code=403, detail="Forbidden")
    else:
        raise HTTPException(status_code=400, detail="Bad Request")


@app.post("/whatsapp/v1")
async def main_webhook(request: Request) -> None:
    """
    Handles the incoming WhatsApp webhook message.

    Args:
        request (Request): The incoming HTTP request.

    Returns:
        None
    """
    # Wait for the incoming webhook message to be received as JSON
    data = await request.json()

    # Terminate if incoming webhook message is empty/invalid/msg-status-update(sent,delivered,read)
    result = await presenter.extract_relevant_whatsapp_message_details(data)
    if not result:
        logger.debug(
            f"whatsapp incoming message that will not be considered by the webhook: \n{data}"
        )
        return
    logger.info(data)

    # Get relevant info from Meta's API
    business_phone_number_id, from_whatsapp_number, incoming_msg_body = result

    # # Send acknowledgment message
    # # (uncomment this and comment any function(s) below it when you want to quickly test that the webhook works)
    # await presenter.send_whatsapp_message(
    #     from_whatsapp_number, f"Ack: {incoming_msg_body}"
    # )

    # Actual code to process the incoming message using Ansari agent then reply to the sender
    await presenter.process_and_reply_to_whatsapp_sender(
        from_whatsapp_number, incoming_msg_body
    )
