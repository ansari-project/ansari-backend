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
import uuid

import psycopg2
import psycopg2.extras
from diskcache import FanoutCache, Lock
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel, EmailStr
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from starlette.exceptions import HTTPException as StarletteHTTPException
from zxcvbn import zxcvbn

from ansari.agents import Ansari, AnsariWorkflow
from ansari.ansari_db import AnsariDB, MessageLogger
from ansari.ansari_logger import get_logger
from ansari.app.main_whatsapp import router as whatsapp_router
from ansari.config import Settings, get_settings
from ansari.presenters.api_presenter import ApiPresenter
from ansari.util.general_helpers import get_extended_origins, validate_cors

logger = get_logger()

# Register the UUID type globally
# Details: Read the SO question then the answer referenced below:
#   https://stackoverflow.com/a/59268003/13626137
# More details (optional):
#   https://www.psycopg.org/docs/advanced.html#:~:text=because%20the%20object%20to%20adapt%20comes%20from%20a%20third%20party%20library
psycopg2.extras.register_uuid()

app = FastAPI()


# Custom exception handler, which aims to log FastAPI-related exceptions before raising them
# Details: https://fastapi.tiangolo.com/tutorial/handling-errors/#override-request-validation-exceptions
#   Side note: apparently, there's no need to write another `RequestValidationError`-related function,
#   contrary to what's mentioned in the above URL.
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc: HTTPException):
    logger.error(f"{exc}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


def add_app_middleware():
    # Get the origins from `.env` as well as extra origins
    #   based on current environment (e.g., local dev, CI/CD, etc.)
    origins = get_extended_origins()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


add_app_middleware()

db = AnsariDB(get_settings())
ansari = Ansari(get_settings())

presenter = ApiPresenter(app, ansari)
presenter.present()

cache = FanoutCache(get_settings().diskcache_dir, shards=4, timeout=1)

# Include the WhatsApp router
app.include_router(whatsapp_router)

if __name__ == "__main__" and get_settings().DEBUG_MODE:
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
async def register_user(req: RegisterRequest, cors_ok: bool = Depends(validate_cors)):
    """Register a new user.
    If the user exists, returns 403.
    Returns 200 on success.
    Returns 400 if the password is too weak. Will include suggestions for a stronger password.
    """
    if not cors_ok:
        raise HTTPException(status_code=403, detail="CORS not permitted")

    password_hash = db.hash_password(req.password)
    logger.info(
        f"Received request to create account: {req.email} {password_hash} {req.first_name} {req.last_name}",
    )
    try:
        # Check if account exists
        if db.account_exists(req.email):
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
        return db.register(req.email, req.first_name, req.last_name, password_hash)
    except psycopg2.Error as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Database error")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@app.post("/api/v2/users/login")
async def login_user(
    req: LoginRequest,
    cors_ok: bool = Depends(validate_cors),
    settings: Settings = Depends(get_settings),
):
    """Logs the user in.
    Returns a token on success.
    Returns 403 if the password is incorrect or the user doesn't exist.
    """
    if not cors_ok:
        raise HTTPException(status_code=403, detail="CORS not permitted")

    if not db.account_exists(req.email):
        raise HTTPException(status_code=403, detail="Invalid username or password")

    user_id, existing_hash, first_name, last_name = db.retrieve_user_info(req.email)

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
    except psycopg2.Error as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Database error")


@app.post("/api/v2/users/refresh_token")
async def refresh_token(
    request: Request,
    cors_ok: bool = Depends(validate_cors),
    settings: Settings = Depends(get_settings),
):
    """Refresh both the access token and the refresh token.

    Details: the function performs the following steps:
    1. Validates CORS settings.
    2. Extracts the old refresh token from the request headers.
    3. Decodes the old refresh token to extract token parameters.
    4. Uses a locking mechanism to prevent race conditions.
    5. Checks if the new tokens are already cached.
    6. Validates the old refresh token and deletes the old token pair from the database.
    7. Generates new access and refresh tokens.
    8. Saves the new tokens to the database.
    9. Caches the new tokens with a short expiry.
    10. Handles database errors and raises appropriate HTTP exceptions.

    TODO(anyone): Explain the theory behind locking/caching, and why steps 4-9 are necessary.

    Returns:
        dict: A dictionary containing the new access and refresh tokens on success.

    Raises:
        HTTPException:
            - 403 if CORS validation fails or the token type is invalid.
            - 401 if the refresh token is invalid or has expired.
            - 500 if there is an internal server error during token generation or saving.

    """
    if not cors_ok:
        raise HTTPException(status_code=403, detail="CORS not permitted")

    old_refresh_token = request.headers.get("Authorization", "").split(" ")[1]
    token_params = db.decode_token(old_refresh_token)

    lock_key = f"lock:{token_params['user_id']}"
    with Lock(cache, lock_key, expire=3):
        # Check cache for existing token pair
        cached_tokens = cache.get(old_refresh_token)
        if cached_tokens:
            return {"status": "success", **cached_tokens}

        # If no cached tokens, proceed to validate and generate new tokens
        try:
            # Validate the refresh token and delete the old token pair
            db.delete_access_refresh_tokens_pair(old_refresh_token)

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
            cache.set(old_refresh_token, new_tokens, expire=3)
            return {"status": "success", **new_tokens}
        except psycopg2.Error as e:
            logger.critical(f"Error: {e}")
            raise HTTPException(status_code=500, detail="Database error")


@app.post("/api/v2/users/logout")
async def logout_user(
    request: Request,
    cors_ok: bool = Depends(validate_cors),
    token_params: dict = Depends(db.validate_token),
):
    """Logs the user out.
    Deletes all tokens.
    Returns 403 if the password is incorrect or the user doesn't exist.
    """
    if not (cors_ok and token_params):
        raise HTTPException(status_code=403, detail="Invalid username or password")

    try:
        token = request.headers.get("Authorization", "").split(" ")[1]
        db.logout(token_params["user_id"], token)
        return {"status": "success"}
    except psycopg2.Error as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Database error")


class FeedbackRequest(BaseModel):
    thread_id: uuid.UUID
    message_id: int
    feedback_class: str
    comment: str


@app.post("/api/v2/feedback")
async def add_feedback(
    req: FeedbackRequest,
    cors_ok: bool = Depends(validate_cors),
    token_params: dict = Depends(db.validate_token),
):
    if not (cors_ok and token_params):
        raise HTTPException(status_code=403, detail="CORS not permitted")

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
    except psycopg2.Error as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Database error")


@app.post("/api/v2/threads")
async def create_thread(
    request: Request,
    cors_ok: bool = Depends(validate_cors),
    token_params: dict = Depends(db.validate_token),
):
    if not (cors_ok and token_params):
        raise HTTPException(status_code=403, detail="CORS not permitted")

    logger.info(f"Token_params is {token_params}")
    try:
        thread_id = db.create_thread(token_params["user_id"])
        logger.debug(f"Created thread {thread_id}")
        return thread_id
    except psycopg2.Error as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Database error")


@app.get("/api/v2/threads")
async def get_all_threads(
    request: Request,
    cors_ok: bool = Depends(validate_cors),
    token_params: dict = Depends(db.validate_token),
):
    """Retrieve all threads for the user whose id is included in the token."""
    if not (cors_ok and token_params):
        raise HTTPException(status_code=403, detail="CORS not permitted")

    logger.info(f"Token_params is {token_params}")
    try:
        threads = db.get_all_threads(token_params["user_id"])
        return threads
    except psycopg2.Error as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Database error")


class AddMessageRequest(BaseModel):
    role: str
    content: str


@app.post("/api/v2/threads/{thread_id}")
def add_message(
    thread_id: uuid.UUID,
    req: AddMessageRequest,
    cors_ok: bool = Depends(validate_cors),
    token_params: dict = Depends(db.validate_token),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    """Adds a message to a thread. If the message is the first message in the thread,
    we set the name of the thread to the content of the message.
    """
    if not (cors_ok and token_params):
        raise HTTPException(status_code=403, detail="CORS not permitted")

    logger.info(f"Token_params is {token_params}")

    try:
        # Get the thread history (excluding incoming user's message, as it will be logged later)
        history = db.get_thread_llm(thread_id, token_params["user_id"])

        # Create a new thread for the current user if not already created (i.e., history is empty)
        # NOTE: the name of this thread is set to the first message
        #   that the user sends in this new thread
        if history["thread_name"] is None:
            db.set_thread_name(
                thread_id,
                token_params["user_id"],
                req.content,
            )
            logger.info(f"Added thread {thread_id}")

        # Append the user's message to the history retrieved from the DB
        # NOTE: "user" is used instead of `req.role`, as we don't want to change the frontend's code
        #   In the event of our LLM provider (e.g., OpenaAI) decide to the change how the user's role is represented
        user_msg = db.convert_message_llm(["user", req.content])[0]
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
                token_params["user_id"],
                thread_id,
            ),
        )
    except psycopg2.Error as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Database error")


@app.post("/api/v2/share/{thread_id}")
def share_thread(
    thread_id: uuid.UUID,
    cors_ok: bool = Depends(validate_cors),
    token_params: dict = Depends(db.validate_token),
):
    """Take a snapshot of a thread at this time and make it shareable."""
    if not (cors_ok and token_params):
        raise HTTPException(status_code=403, detail="CORS not permitted")

    logger.info(f"Token_params is {token_params}")
    # TODO(mwk): check that the user_id in the token matches the
    # user_id associated with the thread_id.
    try:
        share_uuid = db.snapshot_thread(thread_id, token_params["user_id"])
        return {"status": "success", "share_uuid": share_uuid}
    except psycopg2.Error as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Database error")


@app.get("/api/v2/share/{share_uuid_str}")
def get_snapshot(
    share_uuid_str: str,
    cors_ok: bool = Depends(validate_cors),
):
    """Take a snapshot of a thread at this time and make it shareable."""
    if not cors_ok:
        raise HTTPException(status_code=403, detail="CORS not permitted")

    logger.info(f"Incoming share_uuid is {share_uuid_str}")
    share_uuid = uuid.UUID(share_uuid_str)
    try:
        content = db.get_snapshot(share_uuid)
        return {"status": "success", "content": content}
    except psycopg2.Error as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Database error")


@app.get("/api/v2/threads/{thread_id}")
async def get_thread(
    thread_id: uuid.UUID,
    cors_ok: bool = Depends(validate_cors),
    token_params: dict = Depends(db.validate_token),
):
    if not (cors_ok and token_params):
        raise HTTPException(status_code=403, detail="CORS not permitted")

    logger.info(f"Token_params is {token_params}")
    # TODO(mwk): check that the user_id in the token matches the
    # user_id associated with the thread_id.
    try:
        messages = db.get_thread(thread_id, token_params["user_id"])
        if messages:  # return only if the thread exists. else raise 404
            return messages
        raise HTTPException(status_code=404, detail="Thread not found")
    except psycopg2.Error as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Database error")


@app.delete("/api/v2/threads/{thread_id}")
async def delete_thread(
    thread_id: uuid.UUID,
    cors_ok: bool = Depends(validate_cors),
    token_params: dict = Depends(db.validate_token),
):
    if not (cors_ok and token_params):
        raise HTTPException(status_code=403, detail="CORS not permitted")

    logger.info(f"Token_params is {token_params}")
    # TODO(mwk): check that the user_id in the token matches the
    # user_id associated with the thread_id.
    try:
        return db.delete_thread(thread_id, token_params["user_id"])
    except psycopg2.Error as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Database error")


class ThreadNameRequest(BaseModel):
    name: str


@app.post("/api/v2/threads/{thread_id}/name")
async def set_thread_name(
    thread_id: uuid.UUID,
    req: ThreadNameRequest,
    cors_ok: bool = Depends(validate_cors),
    token_params: dict = Depends(db.validate_token),
):
    if not (cors_ok and token_params):
        raise HTTPException(status_code=403, detail="CORS not permitted")

    logger.info(f"Token_params is {token_params}")
    # TODO(mwk): check that the user_id in the token matches the
    # user_id associated with the thread_id.
    try:
        messages = db.set_thread_name(thread_id, token_params["user_id"], req.name)
        return messages
    except psycopg2.Error as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Database error")


class SetPrefRequest(BaseModel):
    key: str
    value: str


@app.post("/api/v2/preferences")
async def set_pref(
    req: SetPrefRequest,
    cors_ok: bool = Depends(validate_cors),
    token_params: dict = Depends(db.validate_token),
):
    if not (cors_ok and token_params):
        raise HTTPException(status_code=403, detail="CORS not permitted")

    logger.info(f"Token_params is {token_params}")
    try:
        db.set_pref(token_params["user_id"], req.key, req.value)
    except psycopg2.Error as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Database error")


@app.get("/api/v2/preferences")
async def get_prefs(
    cors_ok: bool = Depends(validate_cors),
    token_params: dict = Depends(db.validate_token),
):
    if not (cors_ok and token_params):
        raise HTTPException(status_code=403, detail="CORS not permitted")

    logger.info(f"Token_params is {token_params}")
    try:
        prefs = db.get_prefs(token_params["user_id"])
        return prefs
    except psycopg2.Error as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Database error")


class ResetPasswordRequest(BaseModel):
    email: EmailStr


@app.post("/api/v2/request_password_reset")
async def request_password_reset(
    req: ResetPasswordRequest,
    cors_ok: bool = Depends(validate_cors),
    settings: Settings = Depends(get_settings),
):
    if not cors_ok:
        raise HTTPException(status_code=403, detail="CORS not permitted")

    logger.info(f"Request received to reset {req.email}")
    if db.account_exists(req.email):
        user_id, _, _, _ = db.retrieve_user_info(req.email)
        reset_token = db.generate_token(user_id, "reset")
        db.save_reset_token(user_id, reset_token)
        # shall we also revoke login and refresh tokens?
        tenv = Environment(loader=FileSystemLoader(settings.template_dir))
        template = tenv.get_template("password_reset.html")
        rendered_template = template.render(reset_token=reset_token)
        message = Mail(
            from_email="feedback@ansari.chat",
            to_emails=f"{req.email}",
            subject="Ansari Password Reset",
            html_content=rendered_template,
        )

        try:
            if settings.SENDGRID_API_KEY:
                sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
                response = sg.send(message)
                logger.debug(response.status_code)
                logger.debug(response.body)
                logger.debug(response.headers)
            else:
                logger.warning("No sendgrid key")
                logger.info(f"Would have sent: {message}")
        except Exception as e:
            print(e.message)
    # Even if the email doesn't exist, we return success.
    # So this can't be used to work out who is on our system.
    return {"status": "success"}


@app.post("/api/v2/update_password")
async def update_password(
    cors_ok: bool = Depends(validate_cors),
    token_params: dict = Depends(db.validate_reset_token),
    password: str = None,
):
    """Update the user's password if you have a valid token"""
    if not (cors_ok and token_params):
        raise HTTPException(status_code=403, detail="Invalid username or password")

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
    except psycopg2.Error as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Database error")


class PasswordReset(BaseModel):
    reset_token: str
    new_password: str


@app.post("/api/v2/reset_password")
async def reset_password(req: PasswordReset, cors_ok: bool = Depends(validate_cors)):
    """Resets the user's password if you have a reset token."""
    token_params = db.validate_reset_token(req.reset_token)
    if not cors_ok:
        raise HTTPException(status_code=403, detail="Invalid username or password")

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
    except psycopg2.Error as e:
        logger.critical(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Database error")


@app.post("/api/v1/complete")
async def complete(request: Request, cors_ok: bool = Depends(validate_cors)):
    """Provides a response to a user's input.
    The input is a list of messages, each with with
    a role and a text field. Roles are typically
    'user' or 'assistant.' The client should maintain the
    record of the conversation client side.

    It returns a stream of tokens (a token is a part of a word).

    """
    if not cors_ok:
        raise HTTPException(status_code=403, detail="CORS not permitted")

    logger.debug(f"Raw request is {request.headers}")
    body = await request.json()
    logger.info(f"Request received > {body}.")
    return presenter.complete(body)


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
    cors_ok: bool = Depends(validate_cors),
    settings: Settings = Depends(get_settings),
    db: AnsariDB = Depends(lambda: AnsariDB(get_settings())),
):
    if not cors_ok:
        raise HTTPException(status_code=403, detail="CORS not permitted")

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
