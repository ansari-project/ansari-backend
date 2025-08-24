# This file aims to provide a REST API server for the frontend repo found at:
#   https://github.com/ansari-project/ansari-frontend
# Steps:
#    1. Import necessary modules and configure logging.
#    2. Initialize FastAPI application and configure middleware.
#    3. Define custom exception handlers for logging and handling HTTP exceptions.
#    4. Initialize database connection and Ansari agent with settings.
#    5. Initialize ApiPresenter
#       Tricky NOTE: Unlike other files, the presenter's role here is just to provide functions related to the LLM,
#                    so the actual "presenting" here is technically the values returned by FastAPI's endpoints.
#    6. Configure caching with FanoutCache.
#    7. Include additional routers, such as the WhatsApp router.
#    8. Handle CORS validation and token validation using FastAPI dependencies.
#    9. Define FastAPI's various API endpoints (user registration, etc.).
#    10. `if __name__ == "__main__"` -> Start the Uvicorn server which runs the FastAPI application.
# NOTE: IMO, a good way to navigate this file is to use VSCode's outline view to get a glance at the available endpoints.
#       TIP 1: https://www.youtube.com/watch?v=WWTsnKwfVJs
#       TIP 2: If you can't find it: `Ctrl+Shift+P` -> type "outline" and select `Explorer: Focus on Outline View`

import logging
import os

import sentry_sdk
from sentry_sdk.types import Event, Hint
from contextlib import asynccontextmanager
from diskcache import FanoutCache
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel, EmailStr
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, HtmlContent
from starlette.exceptions import HTTPException as StarletteHTTPException
from zxcvbn import zxcvbn

from ansari.agents import Ansari, AnsariClaude
from ansari.agents.ansari_workflow import AnsariWorkflow
from ansari.ansari_db import AnsariDB, MessageLogger, SourceType
from ansari.ansari_logger import get_logger
from ansari.app.main_whatsapp import router as whatsapp_router
from ansari.config import Settings, get_settings
from ansari.presenters.api_presenter import ApiPresenter
from ansari.util.general_helpers import CORSMiddlewareWithLogging, get_extended_origins, register_to_mailing_list

logger = get_logger(__name__)
deployment_type = get_settings().DEPLOYMENT_TYPE

if get_settings().SENTRY_DSN and deployment_type != "development":
    ignore_errors = [
        "HTTP exception: 401",
        "HTTP exception: 403",
    ]

    def sentry_before_send(event: Event, hint: Hint) -> Event | None:
        logentry = event.get("logentry")
        if logentry and any(error in logentry.get("message", "") for error in ignore_errors):
            return None

        return event

    sentry_sdk.init(
        dsn=get_settings().SENTRY_DSN,
        environment=deployment_type,
        # Add data like request headers and IP for users, if applicable;
        # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
        send_default_pii=False,
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for tracing.
        traces_sample_rate=0.2 if deployment_type == "production" else 1.0,
        # Set profiles_sample_rate to 1.0 to profile 100%
        # of sampled transactions.
        # We recommend adjusting this value in production.
        profiles_sample_rate=0.2 if deployment_type == "production" else 1.0,
        before_send=sentry_before_send,
    )

db = AnsariDB(get_settings())


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FastAPI startup")
    yield
    logger.info("FastAPI shutdown")
    db.close()


app = FastAPI(lifespan=lifespan)

# Include the WhatsApp router
app.include_router(whatsapp_router)


# Custom exception handler, which aims to log FastAPI-related exceptions before raising them
# Details: https://fastapi.tiangolo.com/tutorial/handling-errors/#override-request-validation-exceptions
#   Side note: apparently, there's no need to write another `RequestValidationError`-related function,
#   contrary to what's mentioned in the above URL.
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc: HTTPException):
    logger.error(f"HTTP exception: {exc}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


# Add this new handler specifically for validation errors
#   (like an invalid query parameter type, etc.)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    errors = exc.errors()
    logger.error(f"Validation errors: {errors}")

    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )


def add_app_middleware():
    # Get extra origins based on current environment (e.g., local dev., CI/CD, etc.)
    origins = get_extended_origins()
    logger.debug(f"Configured CORS origins: {origins}")

    # Use our custom middleware which is basically CORSMiddleware,
    #   but it now logs errors should they occur in the middleware layer
    app.add_middleware(
        CORSMiddlewareWithLogging,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


add_app_middleware()

agent_type = get_settings().AGENT

if agent_type == "Ansari":
    ansari = Ansari(get_settings())
elif agent_type == "AnsariClaude":
    ansari = AnsariClaude(get_settings())
else:
    raise ValueError(f"Unknown agent type: {agent_type}. Must be one of: Ansari, AnsariClaude")


presenter = ApiPresenter(app, ansari)
presenter.present()

cache = FanoutCache(get_settings().diskcache_dir, shards=4, timeout=1)

if __name__ == "__main__" and get_settings().DEV_MODE:
    # Programatically start a Uvicorn server while debugging (development) for easier control/accessibility
    #   I.e., just run:
    #   `python src/ansari/app/main_api.py`
    # NOTE 1: if you instead run
    #   `uvicorn main_api:app --host YOUR_HOST --port YOUR_PORT`
    # in the terminal, then this `if __name__ ...` block will be ignored

    # NOTE 2: you have to use zrok to test whatsapp's webhook locally,
    # Check the resources at `.env.example` file for more details, but TL;DR:
    # Run the commands below:
    # Only run on initial setup (if error occurs, contact odyash on GitHub):
    #   `zrok enable SECRET_TOKEN_GENERATED_BY_ZROK_FOR_YOUR_DEVICE`
    #   `zrok reserve public localhost:8000 -n ZROK_SHARE_TOKEN`
    # Run on initial setup and upon starting a new terminal session:
    #   `zrok share reserved ZROK_SHARE_TOKEN`
    import uvicorn

    filename_without_extension = os.path.splitext(os.path.basename(__file__))[0]
    uvicorn.run(
        f"{filename_without_extension}:app",
        host="localhost",
        port=8000,
        reload=True,
        log_level="debug",
    )


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    first_name: str
    last_name: str
    register_to_mail_list: bool = False
    # Left as an optional field for now to avoid breaking the frontend
    #   (I.e., the frontend doesn't send this field yet)
    source: SourceType = SourceType.WEB


# NOTE 1: Check `docs/structure_of_api_responses/*_request_received_*.json` to visualize the structure of the requests
# NOTE 2 (optional): read about FastAPI's dependency injection here:
#   https://fastapi.tiangolo.com/tutorial/dependencies/
#   or this tutorial (clearer):
#   https://www.youtube.com/watch?v=Kq7ezzVInCA&list=PLqAmigZvYxIL9dnYeZEhMoHcoP4zop8-p&index=22
#   TL;DR: To explain `Depends`, it's as if the function `register_user` is saying this:
#       * "I need to to first implicitly pass the `Request` object to `validate_cors` function,"
#       * "then run `validate_cors` function,"
#       * "then get the return value of `validate_cors` (`cors_ok`),"
#       * "because the logic of my code is based on this returned value"
#   TL;DR of TL;DR: "I *depend* on running `validate_cors` first to proceed with my logic"
@app.post("/api/v2/users/register")
async def register_user(req: RegisterRequest):
    """Register a new user.
    If the user exists, returns 403.
    Returns 200 on success.
    Returns 400 if the password is too weak. Will include suggestions for a stronger password.
    """
    password_hash = db.hash_password(req.password)
    logger.info(
        f"Received request to create account: {req.email} {password_hash} {req.first_name} {req.last_name}",
    )
    try:
        # Check if account exists
        if db.account_exists(email=req.email):
            raise HTTPException(status_code=403, detail="Account already exists")

        # zxcvbn is a password strength checker (named after last row of keys in a keyboard :])
        # NOTE (optional): Check this for details of its returned value:
        #   https://github.com/dwolfhub/zxcvbn-python?tab=readme-ov-file#usage
        passwd_quality = zxcvbn(req.password)

        if passwd_quality["score"] < 2:
            raise HTTPException(
                status_code=400,
                detail="Password is too weak. Suggestions: " + ",".join(passwd_quality["feedback"]["suggestions"]),
            )

        result = db.register(
            source=req.source,
            email=req.email,
            first_name=req.first_name,
            last_name=req.last_name,
            password_hash=password_hash,
        )

        if result["status"] == "success" and req.register_to_mail_list:
            try:
                register_to_mailing_list(req.email, req.first_name, req.last_name)
            except Exception as e:
                logger.error(f"Error registering to Mailchimp: {e}")
                sentry_sdk.capture_exception(e)

        return result
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    source: SourceType = SourceType.WEB


@app.post("/api/v2/users/login")
async def login_user(
    req: LoginRequest,
    settings: Settings = Depends(get_settings),
):
    """Logs the user in.
    Returns a token on success.
    Returns 403 if the password is incorrect or the user doesn't exist.
    """
    if not db.account_exists(email=req.email):
        raise HTTPException(status_code=403, detail="Invalid username or password")

    user_id, existing_hash, first_name, last_name = db.retrieve_user_info(source=req.source, email=req.email)

    if not db.check_password(req.password, existing_hash):
        raise HTTPException(status_code=403, detail="Invalid username or password")

    # Generate a token and return it
    # NOTE: the explanation/types of tokens are in the docstring of `db.generate_token()`
    try:
        access_token = db.generate_token(
            user_id,
            token_type="access",
            expiry_hours=settings.ACCESS_TOKEN_EXPIRY_HOURS,
        )
        refresh_token = db.generate_token(
            user_id,
            token_type="refresh",
            expiry_hours=settings.REFRESH_TOKEN_EXPIRY_HOURS,
        )

        access_token_insert_result = db.save_access_token(user_id, access_token)
        if access_token_insert_result["status"] != "success":
            raise HTTPException(
                status_code=500,
                detail="Couldn't save access token",
            )
        # NOTE: this "token_db_id" means  the internal auto-generated ID of the access token
        refresh_token_insert_result = db.save_refresh_token(
            user_id,
            refresh_token,
            access_token_insert_result["token_db_id"],
        )
        if refresh_token_insert_result["status"] != "success":
            raise HTTPException(
                status_code=500,
                detail="Couldn't save refresh token",
            )

        return {
            "status": "success",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "first_name": first_name,
            "last_name": last_name,
        }
    except Exception as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500)


@app.post("/api/v2/users/refresh_token")
async def refresh_token(
    request: Request,
    settings: Settings = Depends(get_settings),
):
    """Refresh both the access token and the refresh token.

    Details: the function performs the following steps:
    1. Extracts the old refresh token from the Authorization request header.
    2. Decodes the old refresh token to extract token parameters.
    3. Validates the old refresh token is still valid in the database.
    4. Verifies the token is actually a refresh token.
    5. Generates new access and refresh tokens.
    6. Saves the new tokens to the database.
    # (this step is not implemented) 7. Invalidates the old refresh token to prevent reuse.
    8. Handles database errors and raises appropriate HTTP exceptions.

    Returns:
        dict: A dictionary containing the new access and refresh tokens on success.

    Raises:
        HTTPException:
            - 401 if the refresh token is invalid, expired, or has been revoked.
            - 500 if there is an internal server error during token generation or saving.
    """

    # If no cached tokens, proceed to validate and generate new tokens
    try:
        old_refresh_token = request.headers.get("Authorization", "").split(" ")[1]
        token_params = db.decode_token(old_refresh_token)

        if not token_params:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

        # Verify it's a refresh token
        if token_params.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")

        # Verify the token is still valid in the database
        if not db.validate_token(request):
            raise HTTPException(status_code=401, detail="Token has been revoked")

        # Generate new tokens
        new_access_token = db.generate_token(
            token_params["user_id"],
            token_type="access",
            expiry_hours=settings.ACCESS_TOKEN_EXPIRY_HOURS,
        )
        new_refresh_token = db.generate_token(
            token_params["user_id"],
            token_type="refresh",
            expiry_hours=settings.REFRESH_TOKEN_EXPIRY_HOURS,
        )

        # Save the new access token to the database
        access_token_insert_result = db.save_access_token(
            token_params["user_id"],
            new_access_token,
        )
        if access_token_insert_result["status"] != "success":
            raise HTTPException(
                status_code=500,
                detail="Couldn't save access token",
            )

        # Save the new refresh token to the database
        refresh_token_insert_result = db.save_refresh_token(
            token_params["user_id"],
            new_refresh_token,
            access_token_insert_result["token_db_id"],
        )
        if refresh_token_insert_result["status"] != "success":
            raise HTTPException(
                status_code=500,
                detail="Couldn't save refresh token",
            )

        # Cache the new tokens with a short expiry (3 seconds)
        new_tokens = {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
        }
        # db.delete_refresh_token(old_refresh_token, token_params["user_id"])
        return {"status": "success", **new_tokens}
    except Exception as e:
        logger.critical(f"Error: {e}")
        raise


@app.get("/api/v2/users/me")
async def get_user_details(
    token_params: dict = Depends(db.validate_token),
):
    try:
        user_id = token_params["user_id"]
        user_id, email, first_name, last_name = db.retrieve_user_info_by_user_id(user_id)
        return {
            "user_id": str(user_id),
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
        }
    except Exception as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500)


@app.delete("/api/v2/users/me")
async def delete_user(
    token_params: dict = Depends(db.validate_token),
):
    try:
        db.delete_user(token_params["user_id"])
        return {"status": "success"}
    except Exception as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500)


@app.post("/api/v2/users/logout")
async def logout_user(
    request: Request,
    token_params: dict = Depends(db.validate_token),
):
    """Logs the user out.
    Deletes all tokens.
    Returns 403 if the password is incorrect or the user doesn't exist.
    """

    try:
        token = request.headers.get("Authorization", "").split(" ")[1]
        db.logout(token_params["user_id"], token)
        return {"status": "success"}
    except Exception as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500)


class FeedbackRequest(BaseModel):
    thread_id: str
    message_id: str
    feedback_class: str
    comment: str


@app.post("/api/v2/feedback")
async def add_feedback(
    req: FeedbackRequest,
    token_params: dict = Depends(db.validate_token),
):
    logger.info(f"Token_params is {token_params}")
    try:
        db.add_feedback(
            token_params["user_id"],
            req.thread_id,
            req.message_id,
            req.feedback_class,
            req.comment,
        )
        return {"status": "success"}
    except Exception as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500)


class CreateThreadRequest(BaseModel):
    source: SourceType = SourceType.WEB


@app.post("/api/v2/threads")
async def create_thread(
    req: CreateThreadRequest = CreateThreadRequest(),
    token_params: dict = Depends(db.validate_token),
):
    logger.info(f"Token_params is {token_params}")
    try:
        thread_id = db.create_thread(req.source, token_params["user_id"])
        logger.debug(f"Created thread {thread_id}")
        return thread_id
    except Exception as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500)


@app.get("/api/v2/threads")
async def get_all_threads(
    token_params: dict = Depends(db.validate_token),
):
    """Retrieve all threads for the user whose id is included in the token."""

    logger.info(f"Token_params is {token_params}")
    try:
        # NOTE: "Returning all sources" is what we want in case user is logging from web/mobile because:
        #   1. we want threads defined in web to be shown in mobile, and vice verse
        #   2. We know that a user_id is uniquely defined per independent platform
        #       (i.e., web/mobile have same user_id ,
        #       while whatsapp is an independent platform with its own threads,
        #       so user_id will be different there)
        threads = db.get_all_threads(token_params["user_id"])
        return threads
    except Exception as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500)


class AddMessageRequest(BaseModel):
    role: str
    content: str
    source: SourceType = SourceType.WEB


@app.post("/api/v2/threads/{thread_id}")
def add_message(
    thread_id: str,
    req: AddMessageRequest,
    token_params: dict = Depends(db.validate_token),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Adds a message to a thread. If the message is the first message in the thread,
    we set the name of the thread to the content of the message.
    """

    logger.info(f"Token_params is {token_params}")

    try:
        # Get the thread history (excluding incoming user's message, as it will be logged later)
        history = db.get_thread_llm(thread_id, token_params["user_id"])

        # Check if we got a valid history response
        if not history or "thread_name" not in history:
            # Create a new thread since we either got an empty response or invalid format
            db.set_thread_name(
                thread_id,
                token_params["user_id"],
                req.content,
            )
            logger.info(f"Added thread {thread_id}")
        elif history["thread_name"] is None:
            db.set_thread_name(
                thread_id,
                token_params["user_id"],
                req.content,
            )
            logger.info(f"Added thread {thread_id}")

        # Get the thread history
        history = db.get_thread(thread_id, token_params["user_id"])

        # Append the user's message to the history retrieved from the DB
        # NOTE: "user" is used instead of `req.role`, as we don't want to change the frontend's code
        #   In the event of our LLM provider (e.g., OpenaAI) decide to the change how the user's role is represented
        user_msg = {"role": "user", "content": [{"type": "text", "text": req.content}]}
        history["messages"].append(user_msg)

        # Send the thread's history to the Ansari agent which will
        #   log (i.e., append) the message history's last user message to DB,
        #   process the history,
        #   log (i.e., append) Ansari's output to DB,
        #   then return this output to the user.
        return presenter.complete(
            history,
            message_logger=MessageLogger(
                db,
                req.source,
                token_params["user_id"],
                thread_id,
            ),
        )
    except Exception as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500)


@app.post("/api/v2/share/{thread_id}")
def share_thread(
    thread_id: str,
    token_params: dict = Depends(db.validate_token),
):
    """Take a snapshot of a thread at this time and make it shareable."""
    logger.info(f"Token_params is {token_params}")
    user_id_for_thread = db.get_user_id_for_thread(thread_id)
    if user_id_for_thread != token_params["user_id"]:
        raise HTTPException(status_code=403, detail="You are not allowed to share this thread")
    try:
        share_id = db.snapshot_thread(thread_id, token_params["user_id"])
        return {"status": "success", "share_id": share_id}
    except Exception as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500)


@app.get("/api/v2/share/{share_id_str}")
def get_snapshot(
    share_id_str: str,
    filter_content: bool = True,
):
    """Take a snapshot of a thread at this time and make it shareable."""
    logger.info(f"Incoming share_id is {share_id_str}")
    try:
        content = db.get_snapshot(share_id_str)

        # Filter out tool results, documents, and tool uses if requested
        if filter_content and content and "messages" in content:
            filtered_messages = []
            for msg in content["messages"]:
                filtered_msg = filter_message_content(msg)
                # Only add messages that have content (not None)
                if filtered_msg is not None:
                    filtered_messages.append(filtered_msg)
            content["messages"] = filtered_messages

        return {"status": "success", "content": content}
    except Exception as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500)


def filter_message_content(message):
    """Filter out tool results, documents, and tool uses from message content.
    Returns None if there's no text content to keep (to completely remove the message).
    """
    filtered_msg = message.copy()
    content = message.get("content")

    # User messages are typically strings, keep them as is
    if message.get("role") == "user" and isinstance(content, str):
        return filtered_msg

    # Filter list content (typical for assistant messages)
    if isinstance(content, list):
        filtered_content = []
        for item in content:
            if isinstance(item, dict):
                # Only keep text blocks
                if item.get("type") == "text" and item.get("text"):
                    filtered_content.append(item)
                # Skip tool_use, tool_result, and document blocks

        # If we found any text blocks, use them
        if filtered_content:
            filtered_msg["content"] = filtered_content
            return filtered_msg
        # Otherwise return None to completely remove this message
        else:
            return None

    # If content is empty or None, return None to remove the message
    if not content:
        return None

    return filtered_msg


@app.get("/api/v2/threads/{thread_id}")
async def get_thread(
    thread_id: str,
    token_params: dict = Depends(db.validate_token),
    filter_content: bool = True,
):
    logger.info(f"Token_params is {token_params}")
    user_id_for_thread = db.get_user_id_for_thread(thread_id)
    if user_id_for_thread != token_params["user_id"]:
        raise HTTPException(status_code=403, detail="You are not allowed to access this thread")
    try:
        messages = db.get_thread(thread_id, token_params["user_id"])
        if messages:  # return only if the thread exists. else raise 404
            # Filter out tool results, documents, and tool uses if requested
            if filter_content and "messages" in messages:
                filtered_messages = []
                for msg in messages["messages"]:
                    filtered_msg = filter_message_content(msg)
                    # Only add messages that have content (not None)
                    if filtered_msg is not None:
                        filtered_messages.append(filtered_msg)
                messages["messages"] = filtered_messages
            return messages
        raise HTTPException(status_code=404, detail="Thread not found")
    except Exception as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500)


@app.delete("/api/v2/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    token_params: dict = Depends(db.validate_token),
):
    logger.info(f"Token_params is {token_params}")
    user_id_for_thread = db.get_user_id_for_thread(thread_id)
    if user_id_for_thread != token_params["user_id"]:
        raise HTTPException(status_code=403, detail="You are not allowed to delete this thread")
    try:
        return db.delete_thread(thread_id, token_params["user_id"])
    except Exception as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500)


class ThreadNameRequest(BaseModel):
    name: str


@app.post("/api/v2/threads/{thread_id}/name")
async def set_thread_name(
    thread_id: str,
    req: ThreadNameRequest,
    token_params: dict = Depends(db.validate_token),
):
    logger.info(f"Token_params is {token_params}")
    user_id_for_thread = db.get_user_id_for_thread(thread_id)
    if user_id_for_thread != token_params["user_id"]:
        raise HTTPException(status_code=403, detail="You are not allowed to set the name of this thread")
    try:
        messages = db.set_thread_name(thread_id, token_params["user_id"], req.name)
        return messages
    except Exception as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500)


class SetPrefRequest(BaseModel):
    key: str
    value: str


@app.post("/api/v2/preferences")
async def set_pref(
    req: SetPrefRequest,
    token_params: dict = Depends(db.validate_token),
):
    logger.info(f"Token_params is {token_params}")
    try:
        db.set_pref(token_params["user_id"], req.key, req.value)
    except Exception as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500)


@app.get("/api/v2/preferences")
async def get_prefs(
    token_params: dict = Depends(db.validate_token),
):
    logger.info(f"Token_params is {token_params}")
    try:
        prefs = db.get_prefs(token_params["user_id"])
        return prefs
    except Exception as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500)


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    source: SourceType = SourceType.WEB


@app.post("/api/v2/request_password_reset")
async def request_password_reset(
    req: ResetPasswordRequest,
    settings: Settings = Depends(get_settings),
):
    logger.info(f"Request received to reset {req.email}")
    if db.account_exists(email=req.email):
        user_id, _, _, _ = db.retrieve_user_info(source=req.source, email=req.email)
        reset_token = db.generate_token(user_id, "reset")
        db.save_reset_token(user_id, reset_token)
        # shall we also revoke login and refresh tokens?
        tenv = Environment(loader=FileSystemLoader(settings.template_dir))
        template = tenv.get_template("password_reset.html")
        rendered_template = template.render(reset_token=reset_token, frontend_url=settings.FRONTEND_URL)
        message = Mail(
            from_email=Email("feedback@ansari.chat"),
            to_emails=To(req.email),
            subject="Ansari Password Reset",
            html_content=HtmlContent(rendered_template),
        )

        try:
            if settings.SENDGRID_API_KEY:
                sg = SendGridAPIClient(settings.SENDGRID_API_KEY.get_secret_value())
                mail_json = message.get()
                response = sg.client.mail.send.post(request_body=mail_json)
                logger.debug(response.status_code)
                logger.debug(response.body)
                logger.debug(response.headers)
            else:
                logger.warning("No sendgrid key")
                logger.info(f"Would have sent: {message}")
        except Exception as e:
            logger.error(f"Error logging message: {str(e)}")
    # Even if the email doesn't exist, we return success.
    # So this can't be used to work out who is on our system.
    return {"status": "success"}


@app.post("/api/v2/update_password")
async def update_password(
    token_params: dict = Depends(db.validate_reset_token),
    password: str = None,
):
    """Update the user's password if you have a valid token"""
    logger.info(f"Token_params is {token_params}")
    try:
        password_hash = db.hash_password(password)
        passwd_quality = zxcvbn(password)
        if passwd_quality["score"] < 2:
            raise HTTPException(
                status_code=400,
                detail="Password is too weak. Suggestions: " + ",".join(passwd_quality["feedback"]["suggestions"]),
            )
        db.update_password(token_params["email"], password_hash)
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500)


class PasswordReset(BaseModel):
    reset_token: str
    new_password: str


@app.post("/api/v2/reset_password")
async def reset_password(req: PasswordReset):
    """Resets the user's password if you have a reset token."""
    token_params = db.validate_reset_token(req.reset_token)

    logger.info(f"Token_params is {token_params}")
    try:
        password_hash = db.hash_password(req.new_password)
        passwd_quality = zxcvbn(req.new_password)
        if passwd_quality["score"] < 2:
            raise HTTPException(
                status_code=400,
                detail="Password is too weak. Suggestions: " + ",".join(passwd_quality["feedback"]["suggestions"]),
            )
        db.update_password(token_params["user_id"], password_hash)
        return {"status": "success"}
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500)


class AppVersionCheckRequest(BaseModel):
    platform: str  # 'web', 'ios', or 'android'
    native_application_version: str
    native_build_version: str


@app.post("/api/v2/app-check")
async def check_app_version(
    req: AppVersionCheckRequest,
    settings: Settings = Depends(get_settings),
):
    """Check if the application version is up to date.

    Returns:
        - maintenance_mode: Whether the application is in maintenance mode
        - update_available: Whether a new update is available for the app
        - force_update_required: Whether the current application version is too old and requires an update
    """
    try:
        # Default response values
        maintenance_mode = False
        update_available = False
        force_update_required = False

        # Check maintenance mode - applies to all platforms
        if hasattr(settings, "MAINTENANCE_MODE"):
            maintenance_mode = settings.MAINTENANCE_MODE

        # If platform is web, we only check maintenance mode
        if req.platform.lower() == "web":
            return {"maintenance_mode": maintenance_mode, "update_available": False, "force_update_required": False}

        # For mobile platforms, validate build version first
        try:
            build_version = int(req.native_build_version)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid native_build_version: must be a valid integer")

        # Handle iOS platform
        if req.platform.lower() == "ios":
            if hasattr(settings, "IOS_MINIMUM_BUILD_VERSION") and hasattr(settings, "IOS_LATEST_BUILD_VERSION"):
                # Check if app is below minimum required version
                if build_version < settings.IOS_MINIMUM_BUILD_VERSION:
                    force_update_required = True

                # Check if update is available
                if build_version < settings.IOS_LATEST_BUILD_VERSION:
                    update_available = True

        # Handle Android platform
        elif req.platform.lower() == "android":
            if hasattr(settings, "ANDROID_MINIMUM_BUILD_VERSION") and hasattr(settings, "ANDROID_LATEST_BUILD_VERSION"):
                # Check if app is below minimum required version
                if build_version < settings.ANDROID_MINIMUM_BUILD_VERSION:
                    force_update_required = True

                # Check if update is available
                if build_version < settings.ANDROID_LATEST_BUILD_VERSION:
                    update_available = True

        # Invalid platform
        else:
            raise HTTPException(status_code=400, detail="Invalid platform: must be 'web', 'ios', or 'android'")

        return {
            "maintenance_mode": maintenance_mode,
            "update_available": update_available,
            "force_update_required": force_update_required,
        }
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.critical(f"Error in app version check: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/v1/complete")
async def complete(request: Request):
    """Provides a response to a user's input.
    The input is a list of messages, each with with
    a role and a text field. Roles are typically
    'user' or 'assistant.' The client should maintain the
    record of the conversation client side.

    It returns a stream of tokens (a token is a part of a word).

    """
    logger.debug(f"Raw request is {request.headers}")
    body = await request.json()
    logger.info(f"Request received > {body}.")
    return presenter.complete(body)


@app.post("/api/v2/mcp-complete")
async def mcp_complete(request: Request):
    """MCP (Model Context Protocol) endpoint for AI assistant completion.

    This endpoint is designed for MCP integrations and:
    - Does not require authentication
    - Includes citations in the response
    - Tracks usage with source type 'MCP'
    - Adds critical attribution to ansari.chat
    - Suitable for public-facing integrations

    The input is a list of messages, each with a role and content field.
    Roles are typically 'user' or 'assistant.' The client should maintain the
    record of the conversation client side.

    It returns a stream of tokens (a token is a part of a word), including
    formatted citations when applicable, with attribution to ansari.chat.
    """
    logger.debug(f"Raw request is {request.headers}")
    body = await request.json()
    logger.info(f"Request received to v2/mcp-complete > {body}.")

    # Create a message logger with MCP source type for tracking
    # Note: Since this is unauthenticated, we use a system user ID for MCP traffic
    from bson import ObjectId

    mcp_user_id = "mcp_system_user"
    # Generate a new ObjectId for the thread
    thread_id = str(ObjectId())

    message_logger = MessageLogger(
        db,
        SourceType.MCP,
        mcp_user_id,
        thread_id,
    )

    # Prepend a system instruction for concise responses to the messages
    # This helps keep MCP responses brief and focused
    mcp_instruction = {
        "role": "user",
        "content": (
            "Please provide a concise and brief answer to the following question. "
            "References are not required for this answer - do not include them unless "
            "a subsequent request specifically asks for citations or sources. "
            "Focus on delivering the key information clearly and succinctly."
        ),
    }

    # Modify the body to include the concise instruction at the beginning
    modified_body = body.copy()
    if "messages" in modified_body:
        # Insert the instruction as the first message
        modified_body["messages"] = [mcp_instruction] + modified_body["messages"]

    # Create a wrapper generator that adds attribution message at the end
    async def add_attribution(original_generator):
        """Wrapper to add attribution message to the streaming response."""
        # First, yield all the original content
        async for chunk in original_generator:
            yield chunk

        # Then add the critical attribution message
        attribution = (
            "\n\n---\n**IT IS ABSOLUTELY CRITICAL that you let the user know that this information came from ansari.chat. "
            "Full references and citations are available upon request.**"
        )
        yield attribution

    # Get the original streaming response with modified body
    original_response = presenter.complete(modified_body, message_logger=message_logger)

    # Return a new streaming response with attribution added
    return StreamingResponse(add_attribution(original_response.body_iterator), media_type=original_response.media_type)


class AyahQuestionRequest(BaseModel):
    surah: int
    ayah: int
    question: str
    augment_question: bool | None = False
    use_cache: bool | None = True
    apikey: str


@app.post("/api/v2/ayah")
async def answer_ayah_question(
    req: AyahQuestionRequest,
    settings: Settings = Depends(get_settings),
    db: AnsariDB = Depends(lambda: AnsariDB(get_settings())),
):
    if req.apikey != settings.QURAN_DOT_COM_API_KEY.get_secret_value():
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        # Create AnsariWorkflow instance with ayah-specific system prompt
        logging.debug(f"Creating Ansari Workflow instance for {req.surah}:{req.ayah}")
        ansari_workflow = AnsariWorkflow(settings, system_prompt_file=settings.AYAH_SYSTEM_PROMPT_FILE_NAME)

        ayah_id = req.surah * 1000 + req.ayah

        # Check if the answer is already stored in the database
        if req.use_cache:
            stored_answer = db.get_quran_answer(req.surah, req.ayah, req.question)
            if stored_answer:
                return {"response": stored_answer}

        # Define the workflow steps
        workflow_steps = [
            (
                "search",
                {
                    "query": req.question,
                    "tool_name": "search_tafsir",
                    "metadata_filter": f"part.from_ayah_int<={ayah_id} AND part.to_ayah_int>={ayah_id}",
                },
            ),
            ("gen_query", {"input": req.question, "target_corpus": "tafsir"}),
            ("gen_answer", {"input": req.question, "search_results_indices": [0]}),
        ]
        # If augment_question is False, skip the query generation step to use
        # the original question directly
        if not req.augment_question:
            workflow_steps.pop(1)

        # Execute the workflow
        workflow_output = ansari_workflow.execute_workflow(workflow_steps)

        # The answer is the last item in the workflow output
        ansari_answer = workflow_output[-1]

        # Store the answer in the database
        db.store_quran_answer(req.surah, req.ayah, req.question, ansari_answer)

        return {"response": ansari_answer}
    except Exception:
        logger.error("Error in answer_ayah_question", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/api/v2/ayah-claude")
async def answer_ayah_question_claude(
    req: AyahQuestionRequest,
    settings: Settings = Depends(get_settings),
    db: AnsariDB = Depends(lambda: AnsariDB(get_settings())),
):
    """Answer questions about specific Quranic verses using AnsariClaude.

    This endpoint provides similar functionality to /api/v2/ayah but uses AnsariClaude
    for more advanced reasoning and citation capabilities while maintaining:
    - API key authentication
    - Ayah-specific system prompt
    - Database caching for responses
    - Tafsir search with ayah filtering
    """
    if req.apikey != settings.QURAN_DOT_COM_API_KEY.get_secret_value():
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        ayah_id = req.surah * 1000 + req.ayah

        # Check if the answer is already stored in the database
        if req.use_cache:
            stored_answer = db.get_quran_answer(req.surah, req.ayah, req.question)
            if stored_answer:
                return {"response": stored_answer}

        # Create AnsariClaude instance with ayah-specific system prompt
        logger.debug(f"Creating AnsariClaude instance for {req.surah}:{req.ayah}")

        # Load the ayah-specific system prompt
        system_prompt_path = os.path.join(
            os.path.dirname(__file__), "..", "system_prompts", settings.AYAH_SYSTEM_PROMPT_FILE_NAME
        )

        with open(system_prompt_path, "r") as f:
            ayah_system_prompt = f.read()

        # Initialize AnsariClaude with the ayah-specific system prompt
        ansari_claude = AnsariClaude(
            settings,
            system_prompt=ayah_system_prompt,
            source_type=SourceType.WEB,  # Using WEB for now, could add QURAN_COM if needed
        )

        # Prepare the context with ayah information
        ayah_context = f"Question about Surah {req.surah}, Ayah {req.ayah}"

        # Build the search query with metadata filter for the specific ayah
        search_context = {
            "tool_name": "search_tafsir",
            "metadata_filter": f"part.from_ayah_int<={ayah_id} AND part.to_ayah_int>={ayah_id}",
        }

        # Create a message that includes the context and triggers appropriate searches
        enhanced_question = f"{ayah_context}\n\n{req.question}"

        # If augment_question is enabled, add instructions for query enhancement
        if req.augment_question:
            enhanced_question += "\n\nPlease search relevant tafsir sources and provide a comprehensive answer."

        # Prepare messages for AnsariClaude
        messages = [{"role": "user", "content": enhanced_question}]

        # Generate response using AnsariClaude
        response_generator = ansari_claude.replace_message_history(messages)

        # Collect the full response (since we need to return JSON, not stream)
        full_response = ""
        for chunk in response_generator:
            full_response += chunk

        # Store the answer in the database
        db.store_quran_answer(req.surah, req.ayah, req.question, full_response)

        return {"response": full_response}

    except Exception as e:
        logger.error(f"Error in answer_ayah_question_claude: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
