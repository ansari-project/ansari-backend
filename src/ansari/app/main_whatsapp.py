from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from ansari.agents import Ansari
from ansari.ansari_logger import get_logger
from ansari.config import get_settings
from ansari.presenters.whatsapp_presenter import WhatsAppPresenter

logger = get_logger(__name__)

# Create a router in order to make the FastAPI functions here an extension of the main FastAPI app
router = APIRouter()

# Initialize the agent
ansari = Ansari(get_settings())

chosen_whatsapp_biz_num = (
    get_settings().WHATSAPP_BUSINESS_PHONE_NUMBER_ID.get_secret_value()
    if not get_settings().DEBUG_MODE
    else get_settings().WHATSAPP_TEST_BUSINESS_PHONE_NUMBER_ID.get_secret_value()
)

# Initialize the presenter with the agent and credentials
presenter = WhatsAppPresenter(
    agent=ansari,
    access_token=get_settings().WHATSAPP_ACCESS_TOKEN_FROM_SYS_USER.get_secret_value(),
    business_phone_number_id=chosen_whatsapp_biz_num,
    api_version=get_settings().WHATSAPP_API_VERSION,
)
presenter.present()


@router.get("/whatsapp/v1")
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


@router.post("/whatsapp/v1")
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
    if isinstance(result, str):
        if "error" in result.lower():
            presenter.send_whatsapp_message(
                "There's a problem with the server. Kindly send again later..."
            )
            return
        return

    # Get relevant info from Meta's API
    (
        business_phone_number_id,
        from_whatsapp_number,
        incoming_msg_type,
        incoming_msg_body,
    ) = result

    if incoming_msg_type != "text":
        msg_type = (
            incoming_msg_type + "s"
            if not incoming_msg_type.endswith("s")
            else incoming_msg_type
        )
        msg_type = msg_type.replace("unsupporteds", "this media type")
        await presenter.send_whatsapp_message(
            from_whatsapp_number,
            f"Sorry, I can't process {msg_type} yet. Please send me a text message.",
        )
        return

    # Send acknowledgment message
    if get_settings().DEBUG_MODE:
        await presenter.send_whatsapp_message(
            from_whatsapp_number, f"Ack: {incoming_msg_body}"
        )

    # Actual code to process the incoming message using Ansari agent then reply to the sender
    await presenter.process_and_reply_to_whatsapp_sender(
        from_whatsapp_number, incoming_msg_body
    )