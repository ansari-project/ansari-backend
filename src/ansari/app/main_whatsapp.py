# This file aims to extend `main_api.py` with FastAPI endpoints which handle incoming WhatsApp webhook messages.
# NOTE: the `BackgroundTasks` logic is inspired by this issue and chat (respectively):
# https://stackoverflow.com/questions/72894209/whatsapp-cloud-api-sending-old-message-inbound-notification-multiple-time-on-my
# https://www.perplexity.ai/search/explain-fastapi-s-backgroundta-rnpU7D19QpSxp2ZOBzNUyg
# Steps:
#    1. Import necessary modules and configure logging.
#    2. Create a FastAPI router to extend the main FastAPI app found in `main_api.py`.
#       (Therefore, this file can only be tested by running `main_api.py`.)
#    3. Initialize the Ansari agent with settings.
#    4. Initialize the WhatsAppPresenter with the agent and credentials.
#       Tricky NOTE: Unlike other files, the presenter's role here is just to provide functions for handling WhatsApp messages,
#                    so the actual "presenting" here is technically the values returned by FastAPI's endpoints.
#    5. Define a GET endpoint to handle WhatsApp webhook verification.
#    6. Define a POST endpoint to handle incoming WhatsApp messages.

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, Response

from ansari.agents import Ansari, AnsariClaude
from ansari.ansari_logger import get_logger
from ansari.config import get_settings
from ansari.presenters.whatsapp_presenter import WhatsAppPresenter

logger = get_logger(__name__)

# Create a router in order to make the FastAPI functions here an extension of the main FastAPI app
router = APIRouter()

# Initialize the Ansari agent
agent_type = get_settings().AGENT
whatsapp_enabled = get_settings().WHATSAPP_ENABLED

if agent_type == "Ansari":
    ansari = Ansari(get_settings())
elif agent_type == "AnsariClaude":
    ansari = AnsariClaude(get_settings())
else:
    raise ValueError(f"Unknown agent type: {agent_type}. Must be one of: Ansari, AnsariClaude")

chosen_whatsapp_biz_num = get_settings().WHATSAPP_BUSINESS_PHONE_NUMBER_ID.get_secret_value()

# Initialize the presenter with the agent and credentials
presenter = WhatsAppPresenter(
    agent=ansari,
    access_token=get_settings().WHATSAPP_ACCESS_TOKEN_FROM_SYS_USER.get_secret_value(),
    business_phone_number_id=chosen_whatsapp_biz_num,
    api_version=get_settings().WHATSAPP_API_VERSION,
)
presenter.present()


@router.get("/whatsapp/v1")
async def verification_webhook(request: Request) -> str | None:
    """Handles the WhatsApp webhook verification request.

    Args:
        request (Request): The incoming HTTP request.

    Returns:
        Optional[str]: The challenge string if verification is successful, otherwise raises an HTTPException.

    """
    mode = request.query_params.get("hub.mode")
    verify_token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode and verify_token:
        if mode == "subscribe" and verify_token == get_settings().WHATSAPP_VERIFY_TOKEN_FOR_WEBHOOK.get_secret_value():
            logger.info("WHATSAPP WEBHOOK VERIFIED SUCCESFULLY!")
            # Tricky note: apparently, you have to wrap the challenge in an HTMLResponse
            # in order for meta to accept and verify the callback
            # source: https://stackoverflow.com/a/74394602/13626137
            return HTMLResponse(challenge)
        raise HTTPException(status_code=403, detail="Forbidden")
    raise HTTPException(status_code=400, detail="Bad Request")


@router.post("/whatsapp/v1")
async def main_webhook(request: Request, background_tasks: BackgroundTasks) -> Response:
    """Handles the incoming WhatsApp webhook message.

    Args:
        request (Request): The incoming HTTP request.
        background_tasks (BackgroundTasks): The background tasks to be executed.

    Returns:
        Response: HTTP response with status code 200.

    """
    # Wait for the incoming webhook message to be received as JSON
    data = await request.json()

    if get_settings().DEV_MODE:
        if "statuses" in (value := data.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {})):
            recipient_id = data["entry"][0]["changes"][0]["value"]["statuses"][0].get("recipient_id") or "unknown"
            # logger.debug(f"Incoming whatsapp webhook status from {recipient_id}")
            pass
        else:
            recipient_id = ((messages := (value.get("messages", []) or [])) and messages[0].get("from")) or "unknown"
            logger.debug(f"Incoming whatsapp webhook message from {recipient_id}")

    # # Logging the origin (host) of the incoming webhook message
    # logger.debug(f"ORIGIN of the incoming webhook message: {json.dumps(request, indent=4)}")

    # Terminate if incoming webhook message is empty/invalid/msg-status-update(sent,delivered,read)
    try:
        result = await presenter.extract_relevant_whatsapp_message_details(data)
    except Exception as e:
        logger.error(f"Error extracting message details: {e}")
        return Response(status_code=200)
    else:
        if isinstance(result, str):
            return Response(status_code=200)

    # Get relevant info from Meta's API
    (
        from_whatsapp_number,
        incoming_msg_type,
        incoming_msg_body,
    ) = result

    # Workaround while locally developing:
    #   don't process other dev's whatsapp recepient phone nums coming from staging env.
    #   (as both stage Meta app / local-.env-file have same testing number)
    dev_num_sub_str = "<your dev. number>"
    if get_settings().DEV_MODE and dev_num_sub_str not in from_whatsapp_number:
        logger.debug(
            f"Incoming message from {from_whatsapp_number} (doesn't have {dev_num_sub_str}). \
            Therefore, will not process it as it's not cur. dev."
        )
        return Response(status_code=200)

    if not whatsapp_enabled:
        background_tasks.add_task(
            presenter.send_whatsapp_message,
            from_whatsapp_number,
            "Ansari for WhatsApp is down for maintenance, please try again later or visit our website at https://ansari.chat.",
        )
        return Response(status_code=200)

    # Check if the user's phone number is stored in users_whatsapp table and register if not
    # Returns false if user's not found and thier registration fails
    user_found: bool = await presenter.check_and_register_user(
        from_whatsapp_number,
        incoming_msg_type,
        incoming_msg_body,
    )
    if not user_found:
        background_tasks.add_task(
            presenter.send_whatsapp_message,
            from_whatsapp_number,
            "Sorry, we couldn't register you to our Database. Please try again later.",
        )
        return Response(status_code=200)

    # Check if the incoming message is a location
    if incoming_msg_type == "location":
        # NOTE: Currently, will not handle location messages
        background_tasks.add_task(
            presenter.handle_unsupported_message,
            from_whatsapp_number,
            incoming_msg_type,
        )
        return Response(status_code=200)

    # Check if the incoming message is a media type other than text
    if incoming_msg_type != "text":
        background_tasks.add_task(
            presenter.handle_unsupported_message,
            from_whatsapp_number,
            incoming_msg_type,
        )
        return Response(status_code=200)

    # Rest of the code below is for processing text messages sent by the whatsapp user
    incoming_msg_text = incoming_msg_body["body"]

    # # Send acknowledgment message (only when DEV_MODE)
    # # and if dev. doesn't need it, comment it out :]
    # if get_settings().DEV_MODE:
    #     await presenter.send_whatsapp_message(
    #         from_whatsapp_number,
    #         f"Ack: {incoming_msg_text}",
    #     )

    # Send a typing indicator to the sender
    # Side note: As of 2024-12-21, Meta's WhatsApp API does not support typing indicators
    # Source: Search "typing indicator whatsapp api" on Google
    background_tasks.add_task(presenter.send_whatsapp_message, from_whatsapp_number, "...")

    # Actual code to process the incoming message using Ansari agent then reply to the sender
    background_tasks.add_task(
        presenter.handle_text_message,
        from_whatsapp_number,
        incoming_msg_text,
    )

    return Response(status_code=200)
