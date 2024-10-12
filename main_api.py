import logging
import uuid

import psycopg2
import psycopg2.extras
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from jinja2 import Environment, FileSystemLoader
from jwt import PyJWTError
from pydantic import BaseModel
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from zxcvbn import zxcvbn
from diskcache import FanoutCache, Lock

from agents.ansari import Ansari
from ansari_db import AnsariDB, MessageLogger
from presenters.api_presenter import ApiPresenter
from config import Settings, get_settings

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Register the UUID type globally
psycopg2.extras.register_uuid()


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = AnsariDB(get_settings())
ansari = Ansari(get_settings())

presenter = ApiPresenter(app, ansari)
presenter.present()

cache = FanoutCache(get_settings().diskcache_dir, shards=4, timeout=1)


def validate_cors(request: Request, settings: Settings = Depends(get_settings)) -> bool:
    try:
        logger.info(f"Raw request is {request.headers}")
        origin = request.headers.get("origin", "")
        mobile = request.headers.get("x-mobile-ansari", "")
        if origin and origin in settings.ORIGINS or mobile == "ANSARI":
            logger.debug("CORS OK")
            return True
        else:
            raise HTTPException(status_code=502, detail="Not Allowed Origin")
    except PyJWTError:
        raise HTTPException(status_code=403, detail="Could not validate credentials")


class RegisterRequest(BaseModel):
    email: str
    password: str
    first_name: str
    last_name: str


@app.post("/api/v2/users/register")
async def register_user(req: RegisterRequest, cors_ok: bool = Depends(validate_cors)):
    """Register a new user.
    If the user exists, returns 403.
    Returns 200 on success.
    Returns 400 if the password is too weak. Will include suggestions for a stronger password.
    """

    password_hash = db.hash_password(req.password)
    logger.info(
        f"Received request to create account: {req.email} {password_hash} {req.first_name} {req.last_name}"
    )
    try:
        # Check if account exists
        if db.account_exists(req.email):
            raise HTTPException(status_code=403, detail="Account already exists")
        passwd_quality = zxcvbn(req.password)
        if passwd_quality["score"] < 2:
            raise HTTPException(
                status_code=400,
                detail="Password is too weak. Suggestions: "
                + ",".join(passwd_quality["feedback"]["suggestions"]),
            )
        return db.register(req.email, req.first_name, req.last_name, password_hash)
    except psycopg2.Error as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Database error")


class LoginRequest(BaseModel):
    email: str
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
    if db.account_exists(req.email):
        user_id, existing_hash, first_name, last_name = db.retrieve_user_info(req.email)
        if db.check_password(req.password, existing_hash):
            # Generate a token and return it
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
                        status_code=500, detail="Couldn't save access token"
                    )
                refresh_token_insert_result = db.save_refresh_token(
                    user_id, refresh_token, access_token_insert_result["token_db_id"]
                )
                if refresh_token_insert_result["status"] != "success":
                    raise HTTPException(
                        status_code=500, detail="Couldn't save refresh token"
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
        else:
            raise HTTPException(status_code=403, detail="Invalid username or password")
    else:
        raise HTTPException(status_code=403, detail="Invalid username or password")


@app.post("/api/v2/users/refresh_token")
async def refresh_token(
    request: Request,
    cors_ok: bool = Depends(validate_cors),
    settings: Settings = Depends(get_settings),
):
    """
    Refresh both the access token and the refresh token.

    Returns:
        dict: A dictionary containing the new access and refresh tokens on success.

    Raises:
        HTTPException:
            - 403 if CORS validation fails or the token type is invalid.
            - 401 if the refresh token is invalid or has expired.
            - 500 if there is an internal server error during token generation or saving.
    """
    if cors_ok:
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
                    token_params["user_id"], new_access_token
                )
                if access_token_insert_result["status"] != "success":
                    raise HTTPException(
                        status_code=500, detail="Couldn't save access token"
                    )

                # Save the new refresh token to the database
                refresh_token_insert_result = db.save_refresh_token(
                    token_params["user_id"],
                    new_refresh_token,
                    access_token_insert_result["token_db_id"],
                )
                if refresh_token_insert_result["status"] != "success":
                    raise HTTPException(
                        status_code=500, detail="Couldn't save refresh token"
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
    else:
        raise HTTPException(status_code=403, detail="Invalid origins")


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
    if cors_ok and token_params:
        try:
            token = request.headers.get("Authorization", "").split(" ")[1]
            db.logout(token_params["user_id"], token)
            return {"status": "success"}
        except psycopg2.Error as e:
            logger.critical(f"Error: {e}")
            raise HTTPException(status_code=500, detail="Database error")
    raise HTTPException(status_code=403, detail="Invalid username or password")


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
    if cors_ok and token_params:
        logger.info(f"Token_params is {token_params}")
        # Now create a thread and return the thread_id
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
    else:
        raise HTTPException(status_code=403, detail="CORS not permitted")


@app.post("/api/v2/threads")
async def create_thread(
    request: Request,
    cors_ok: bool = Depends(validate_cors),
    token_params: dict = Depends(db.validate_token),
):
    if cors_ok and token_params:
        logger.info(f"Token_params is {token_params}")
        # Now create a thread and return the thread_id
        try:
            thread_id = db.create_thread(token_params["user_id"])
            return thread_id
        except psycopg2.Error as e:
            logger.critical(f"Error: {e}")
            raise HTTPException(status_code=500, detail="Database error")
    else:
        raise HTTPException(status_code=403, detail="CORS not permitted")


@app.get("/api/v2/threads")
async def get_all_threads(
    request: Request,
    cors_ok: bool = Depends(validate_cors),
    token_params: dict = Depends(db.validate_token),
):
    """Retrieve all threads for the user whose id is included in the token."""
    if cors_ok and token_params:
        logger.info(f"Token_params is {token_params}")
        # Now create a thread and return the thread_id
        try:
            threads = db.get_all_threads(token_params["user_id"])
            return threads
        except psycopg2.Error as e:
            logger.critical(f"Error: {e}")
            raise HTTPException(status_code=500, detail="Database error")
    else:
        raise HTTPException(status_code=403, detail="CORS not permitted")


class AddMessageRequest(BaseModel):
    role: str
    content: str


@app.post("/api/v2/threads/{thread_id}")
def add_message(
    thread_id: uuid.UUID,
    req: AddMessageRequest,
    cors_ok: bool = Depends(validate_cors),
    token_params: dict = Depends(db.validate_token),
) -> StreamingResponse:
    """Adds a message to a thread. If the message is the first message in the thread,
    we set the name of the thread to the content of the message.
    """
    if cors_ok and token_params:
        logger.info(f"Token_params is {token_params}")

        try:
            db.append_message(token_params["user_id"], thread_id, req.role, req.content)
            # Now actually use Ansari.
            history = db.get_thread_llm(thread_id, token_params["user_id"])
            if history["thread_name"] is None and len(history["messages"]) > 1:
                db.set_thread_name(
                    thread_id,
                    token_params["user_id"],
                    history["messages"][0]["content"],
                )
            return presenter.complete(
                history,
                message_logger=MessageLogger(db, token_params["user_id"], thread_id),
            )
        except psycopg2.Error as e:
            logger.critical(f"Error: {e}")
            raise HTTPException(status_code=500, detail="Database error")
    else:
        raise HTTPException(status_code=403, detail="CORS not permitted")


@app.post("/api/v2/share/{thread_id}")
def share_thread(
    thread_id: uuid.UUID,
    cors_ok: bool = Depends(validate_cors),
    token_params: dict = Depends(db.validate_token),
):
    """
    Take a snapshot of a thread at this time and make it shareable.

    """
    if cors_ok and token_params:
        logger.info(f"Token_params is {token_params}")
        # TODO(mwk): check that the user_id in the token matches the
        # user_id associated with the thread_id.
        try:
            share_uuid = db.snapshot_thread(thread_id, token_params["user_id"])
            return {"status": "success", "share_uuid": share_uuid}
        except psycopg2.Error as e:
            logger.critical(f"Error: {e}")
            raise HTTPException(status_code=500, detail="Database error")
    else:
        raise HTTPException(status_code=403, detail="CORS not permitted")


@app.get("/api/v2/share/{share_uuid_str}")
def get_snapshot(
    share_uuid_str: str,
    cors_ok: bool = Depends(validate_cors),
):
    """
    Take a snapshot of a thread at this time and make it shareable.

    """
    # Note that unlike the other endpoints, we don't need to check the token here.
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
    if cors_ok and token_params:
        logger.info(f"Token_params is {token_params}")
        # TODO(mwk): check that the user_id in the token matches the
        # user_id associated with the thread_id.
        try:
            messages = db.get_thread(thread_id, token_params["user_id"])
            if messages:  # return only if the thread exists. else raise 404
                return messages
            else:
                raise HTTPException(status_code=404, detail="Thread not found")
        except psycopg2.Error as e:
            logger.critical(f"Error: {e}")
            raise HTTPException(status_code=500, detail="Database error")
    else:
        raise HTTPException(status_code=403, detail="CORS not permitted")


@app.delete("/api/v2/threads/{thread_id}")
async def delete_thread(
    thread_id: uuid.UUID,
    cors_ok: bool = Depends(validate_cors),
    token_params: dict = Depends(db.validate_token),
):
    if cors_ok and token_params:
        logger.info(f"Token_params is {token_params}")
        # TODO(mwk): check that the user_id in the token matches the
        # user_id associated with the thread_id.
        try:
            return db.delete_thread(thread_id, token_params["user_id"])
        except psycopg2.Error as e:
            logger.critical(f"Error: {e}")
            raise HTTPException(status_code=500, detail="Database error")
    else:
        raise HTTPException(status_code=403, detail="CORS not permitted")


class ThreadNameRequest(BaseModel):
    name: str


@app.post("/api/v2/threads/{thread_id}/name")
async def set_thread_name(
    thread_id: uuid.UUID,
    req: ThreadNameRequest,
    cors_ok: bool = Depends(validate_cors),
    token_params: dict = Depends(db.validate_token),
):
    if cors_ok and token_params:
        logger.info(f"Token_params is {token_params}")
        # TODO(mwk): check that the user_id in the token matches the
        # user_id associated with the thread_id.
        try:
            messages = db.set_thread_name(thread_id, token_params["user_id"], req.name)
            return messages
        except psycopg2.Error as e:
            logger.critical(f"Error: {e}")
            raise HTTPException(status_code=500, detail="Database error")
    else:
        raise HTTPException(status_code=403, detail="CORS not permitted")


class SetPrefRequest(BaseModel):
    key: str
    value: str


@app.post("/api/v2/preferences")
async def set_pref(
    req: SetPrefRequest,
    cors_ok: bool = Depends(validate_cors),
    token_params: dict = Depends(db.validate_token),
):
    if cors_ok and token_params:
        logger.info(f"Token_params is {token_params}")
        # Now create a thread and return the thread_id
        try:
            db.set_pref(token_params["user_id"], req.key, req.value)

        except psycopg2.Error as e:
            logger.critical(f"Error: {e}")
            raise HTTPException(status_code=500, detail="Database error")
    else:
        raise HTTPException(status_code=403, detail="CORS not permitted")


@app.get("/api/v2/preferences")
async def get_prefs(
    cors_ok: bool = Depends(validate_cors),
    token_params: dict = Depends(db.validate_token),
):
    if cors_ok and token_params:
        logger.info(f"Token_params is {token_params}")
        # Now create a thread and return the thread_id
        try:
            prefs = db.get_prefs(token_params["user_id"])
            return prefs

        except psycopg2.Error as e:
            logger.critical(f"Error: {e}")
            raise HTTPException(status_code=500, detail="Database error")
    else:
        raise HTTPException(status_code=403, detail="CORS not permitted")


class ResetPasswordRequest(BaseModel):
    email: str


@app.post("/api/v2/request_password_reset")
async def request_password_reset(
    req: ResetPasswordRequest,
    cors_ok: bool = Depends(validate_cors),
    settings: Settings = Depends(get_settings),
):
    if cors_ok:
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

    else:
        raise HTTPException(status_code=403, detail="CORS note permitted.")


@app.post("/api/v2/update_password")
async def update_password(
    cors_ok: bool = Depends(validate_cors),
    token_params: dict = Depends(db.validate_reset_token),
    password: str = None,
):
    """Update the user's password if you have a valid token"""
    if cors_ok and token_params:
        logger.info(f"Token_params is {token_params}")
        try:
            password_hash = db.hash_password(password)
            passwd_quality = zxcvbn(password)
            if passwd_quality["score"] < 2:
                raise HTTPException(
                    status_code=400,
                    detail="Password is too weak. Suggestions: "
                    + ",".join(passwd_quality["feedback"]["suggestions"]),
                )
            db.update_password(token_params["email"], password_hash)
        except psycopg2.Error as e:
            logger.critical(f"Error: {e}")
            raise HTTPException(status_code=500, detail="Database error")
    else:
        raise HTTPException(status_code=403, detail="Invalid username or password")


class PasswordReset(BaseModel):
    reset_token: str
    new_password: str


@app.post("/api/v2/reset_password")
async def reset_password(req: PasswordReset, cors_ok: bool = Depends(validate_cors)):
    """Resets the user's password if you have a reset token."""
    token_params = db.validate_reset_token(req.reset_token)
    if cors_ok:
        logger.info(f"Token_params is {token_params}")
        try:
            password_hash = db.hash_password(req.new_password)
            passwd_quality = zxcvbn(req.new_password)
            if passwd_quality["score"] < 2:
                raise HTTPException(
                    status_code=400,
                    detail="Password is too weak. Suggestions: "
                    + ",".join(passwd_quality["feedback"]["suggestions"]),
                )
            db.update_password(token_params["user_id"], password_hash)
            return {"status": "success"}
        except psycopg2.Error as e:
            logger.critical(f"Error: {e}")
            raise HTTPException(status_code=500, detail="Database error")
    else:
        raise HTTPException(status_code=403, detail="Invalid username or password")


@app.post("/api/v1/complete")
async def complete(request: Request, cors_ok: bool = Depends(validate_cors)):
    """
    Provides a response to a user's input.
    The input is a list of messages, each with with
    a role and a text field. Roles are typically
    'user' or 'assistant.' The client should maintain the
    record of the conversation client side.

    It returns a stream of tokens (a token is a part of a word).

    """
    logger.info(f"Raw request is {request.headers}")
    if cors_ok:
        body = await request.json()
        logger.info(f"Request received > {body}.")
        return presenter.complete(body)
    else:
        raise HTTPException(status_code=403, detail="CORS not permitted")
