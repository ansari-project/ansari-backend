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

    # Logging the origin (host) of the incoming webhook message
    # logger.debug(f"ORIGIN of the incoming webhook message: {json.dumps(request, indent=4)}")

    # Wait for the incoming webhook message to be received as JSON
    data = await request.json()

    # Extract all relevant data in one go using the general presenter
    try:
        (
            is_status,
            from_whatsapp_number,
            incoming_msg_type,
            incoming_msg_body,
            message_id,
            message_unix_time,
        ) = await presenter.extract_relevant_whatsapp_message_details(data)
    except Exception as e:
        logger.error(f"Error extracting message details: {e}")
        return Response(status_code=200)

    # Terminate if the incoming message is a status message (e.g., "delivered")
    #   or if the incoming message is in the form of a list, not dict
    #   (shouldn't happen unless user sends a non-text message, which is not supported yet)
    if is_status or isinstance(incoming_msg_body, list):
        return Response(status_code=200)
    else:
        logger.debug(f"Incoming whatsapp webhook message from {from_whatsapp_number}")

    # Terminate if whatsapp is not enabled (i.e., via .env configurations, etc)
    if not whatsapp_enabled:
        # Create a temporary user-specific presenter just to send the message
        temp_presenter = WhatsAppPresenter.create_user_specific_presenter(
            presenter, from_whatsapp_number, None, None, None, None
        )
        background_tasks.add_task(
            temp_presenter.send_whatsapp_message,
            "Ansari for WhatsApp is down for maintenance, please try again later or visit our website at https://ansari.chat.",
        )
        return Response(status_code=200)

    # Temporary corner case while locally developing:
    #   Since the staging server is always running,
    #   and since we currently have the same testing number for both staging and local testing,
    #   therefore we need an indicator that a message is meant for a dev who's testing locally now
    #   and not for the staging server.
    #   This is done by prefixing the message with "!d " (e.g., "!d what is ansari?")
    # NOTE: Obviously, this temp. solution will be removed when we get a dedicated testing number for staging testing.
    if get_settings().DEPLOYMENT_TYPE == "staging" and incoming_msg_body.get("body", "").startswith("!d "):
        logger.debug("Incoming message is meant for a dev who's testing locally now, so will not process it in staging...")
        return Response(status_code=200)

    # Create a user-specific presenter for this message
    user_presenter = WhatsAppPresenter.create_user_specific_presenter(
        presenter,
        from_whatsapp_number,
        incoming_msg_type,
        incoming_msg_body,
        message_id,
        message_unix_time,
    )

    # Start the typing indicator loop that will continue until message is processed
    background_tasks.add_task(
        user_presenter.send_typing_indicator_then_start_loop,
    )

    # Check if the user's phone number is stored in users_whatsapp table and register if not
    # Returns false if user's not found and their registration fails
    user_found: bool = await user_presenter.check_and_register_user()
    if not user_found:
        background_tasks.add_task(
            user_presenter.send_whatsapp_message,
            "Sorry, we couldn't register you to our Database. Please try again later.",
        )
        return Response(status_code=200)

    # Check if there are more than 24 hours have passed from the user's message to the current time
    # If so, send a message to the user and return
    if user_presenter.is_message_too_old():
        response_msg = "Sorry, your message "
        user_msg_start = " ".join(incoming_msg_body.get("body", "").split(" ")[:5])
        if user_msg_start:
            response_msg_cont = ' "' + user_msg_start + '" '
        else:
            response_msg_cont = " "
        response_msg = f"Sorry, your message{response_msg_cont}is too old. Please send a new message."
        background_tasks.add_task(
            user_presenter.send_whatsapp_message,
            response_msg,
        )
        return Response(status_code=200)

    # Check if the incoming message is a location
    if incoming_msg_type == "location":
        # NOTE: Currently, will not handle location messages
        background_tasks.add_task(
            user_presenter.handle_unsupported_message,
        )
        return Response(status_code=200)

    # Check if the incoming message is a media type other than text
    if incoming_msg_type != "text":
        background_tasks.add_task(
            user_presenter.handle_unsupported_message,
        )
        return Response(status_code=200)

    # Rest of the code below is for processing text messages sent by the whatsapp user

    # Actual code to process the incoming message using Ansari agent then reply to the sender
    background_tasks.add_task(
        user_presenter.handle_text_message,
    )

    return Response(status_code=200)
