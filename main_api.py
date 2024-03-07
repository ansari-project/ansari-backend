import os
from typing import Dict, List
from fastapi import Depends, FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse
import psycopg2
from pydantic import BaseModel
from presenters.api_presenter import ApiPresenter
from agents.ansari import Ansari
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
import bcrypt
import jwt
from jwt import PyJWTError
from ansari_db import AnsariDB, MessageLogger
from zxcvbn import zxcvbn
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from jinja2 import Environment, FileSystemLoader



origins = [
    "https://beta.ansari.chat",
    "http://beta.ansari.chat",
    "https://ansari.chat",
    "http://ansari.chat",
    "https://client2.endeavorpal.com", 
    "http://client2.endeavorpal.com",
    "https://hajiansari.ai",
    "http://hajiansari.ai",
]

port = int(os.getenv('API_SERVER_PORT',8000))
db_url = os.getenv('DATABASE_URL', 'postgresql://mwk@localhost:5432/mwk')
token_secret_key = os.getenv('SECRET_KEY', 'secret')
ALGORITHM = "HS256"
ENCODING = "utf-8"
template_dir = 'resources/templates'




app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
db = AnsariDB()
ansari = Ansari()

presenter = ApiPresenter(app, ansari)
presenter.present()

def validate_cors(request: Request) -> bool:
    try:
        print(f'Raw request is {request.headers}')
        origin = request.headers.get('origin','')
        mobile = request.headers.get('x-mobile-ansari', '')
        if origin in origins or mobile == 'ANSARI': 
            print('CORS OK')
            return True
    except PyJWTError:
        raise HTTPException(status_code=403, detail="Could not validate credentials")

class RegisterRequest(BaseModel): 
    email: str
    password: str
    first_name: str
    last_name: str

@app.post("/api/v2/users/register")
async def register_user(req: RegisterRequest,
                        cors_ok: bool =  Depends(validate_cors)):
    """ Register a new user. 
        If the user exists, returns 403.
        Returns 200 on success. 
        Returns 400 if the password is too weak. Will include suggestions for a stronger password.
    """
    
    password_hash = db.hash_password(req.password)
    print(f'Received request to create account: {req.email} {password_hash} {req.first_name} {req.last_name}')
    try: 
        # Check if account exists
        if db.account_exists(req.email):
            raise HTTPException(status_code=403, detail="Account already exists")
        passwd_quality = zxcvbn(req.password)
        if passwd_quality['score'] < 2: 
            raise HTTPException(status_code=400, 
                                detail=f"Password is too weak. Suggestions: " 
                                + ','.join(passwd_quality['feedback']['suggestions']))
        return db.register(req.email, req.first_name, req.last_name, password_hash)
    except psycopg2.Error as e:
        print(f'Error: {e}')
        raise HTTPException(status_code=500, detail="Database error")

class LoginRequest(BaseModel): 
    email: str
    password: str

@app.post("/api/v2/users/login")
async def login_user(req: LoginRequest, 
                     cors_ok: bool =  Depends(validate_cors)):     
    """ Logs the user in. 
        Returns a token on success.
        Returns 403 if the password is incorrect or the user doesn't exist. 
    """
    if db.account_exists(req.email): 
        user_id, existing_hash, first_name, last_name = db.retrieve_user_info(req.email)
        if db.check_password(req.password, existing_hash):
            # Generate a token and return it
            try:
                token = db.generate_token(user_id)
                db.save_token(user_id, token)
                return {'status': 'success', 
                        'token': token,
                        'first_name': first_name,
                        'last_name': last_name}
            except psycopg2.Error as e:
                print(f'Error: {e}')
                raise HTTPException(status_code=500, detail="Database error")
        else: 
            raise HTTPException(status_code=403, detail = "Invalid username or password")
    else: 
        raise HTTPException(status_code=403, detail = "Invalid username or password")
    
@app.get("/api/v2/users/refresh_token")
async def refresh_token(request: Request, 
                    cors_ok: bool =  Depends(validate_cors),
                    token_params: dict = Depends(db.validate_token)):     
    """ Refreshes the token. 
        Returns a new token on success.
        Returns 403 if the password is incorrect or the user doesn't exist. 
    """
    if cors_ok and token_params: 
        try:
            token = db.generate_token(token_params['user_id'])
            db.save_token(token_params['user_id'], token)
            return {'status': 'success', 
                    'token': token}
        except psycopg2.Error as e:
            print(f'Error: {e}')
            raise HTTPException(status_code=500, detail="Database error")
    else: 
        raise HTTPException(status_code=403, detail = "Invalid username or password")
    
@app.post("/api/v2/users/logout")
async def logout_user(request: Request, 
                    cors_ok: bool =  Depends(validate_cors),
                    token_params: dict = Depends(db.validate_token)):     
    """ Logs the user out. 
        Deletes all tokens.
        Returns 403 if the password is incorrect or the user doesn't exist. 
    """
    if cors_ok and token_params: 
         
        try:
            db.logout(token_params['user_id'])
            return {'status': 'success'}
        except psycopg2.Error as e:
            print(f'Error: {e}')
            raise HTTPException(status_code=500, detail="Database error")
        else: 
            raise HTTPException(status_code=403, detail = "Invalid username or password")
    else: 
       raise HTTPException(status_code=403, detail = "Invalid username or password")
    

class FeedbackRequest(BaseModel): 
    thread_id: int
    message_id: int
    feedback_class: str
    comment: str

@app.post("/api/v2/feedback")
async def add_feedback(req: FeedbackRequest,
                        cors_ok: bool =  Depends(validate_cors), 
                        token_params: dict = Depends(db.validate_token)):
    if cors_ok and token_params: 
        print(f'Token_params is {token_params}')
        # Now create a thread and return the thread_id
        try:
            db.add_feedback(token_params['user_id'], 
                             req.thread_id, 
                             req.message_id, 
                             req.feedback_class, 
                             req.comment)
            return {'status': 'success'}
        except psycopg2.Error as e:
            print(f'Error: {e}')
            raise HTTPException(status_code=500, detail="Database error")
    else: 
        raise HTTPException(status_code=403, detail="CORS not permitted")

@app.post("/api/v2/threads")
async def create_thread(request: Request, 
                        cors_ok: bool =  Depends(validate_cors), 
                        token_params: dict = Depends(db.validate_token)):
    if cors_ok and token_params: 
        print(f'Token_params is {token_params}')
        # Now create a thread and return the thread_id
        try:
            thread_id = db.create_thread(token_params['user_id'])
            return thread_id
        except psycopg2.Error as e:
            print(f'Error: {e}')
            raise HTTPException(status_code=500, detail="Database error")
    else: 
        raise HTTPException(status_code=403, detail="CORS not permitted")
    
@app.get("/api/v2/threads")
async def get_all_threads(request: Request, 
                        cors_ok: bool =  Depends(validate_cors), 
                        token_params: dict = Depends(db.validate_token)):
    """ Retrieve all threads for the user whose id is included in the token. 
    """
    if cors_ok and token_params: 
        print(f'Token_params is {token_params}')
        # Now create a thread and return the thread_id
        try:
            threads = db.get_all_threads(token_params['user_id'])
            return threads
        except psycopg2.Error as e:
            print(f'Error: {e}')
            raise HTTPException(status_code=500, detail="Database error")
    else: 
        raise HTTPException(status_code=403, detail="CORS not permitted")

class AddMessageRequest(BaseModel): 
    role: str
    content: str

@app.post("/api/v2/threads/{thread_id}")
def add_message(thread_id: int, 
                      req: AddMessageRequest,
                      cors_ok: bool =  Depends(validate_cors), 
                      token_params: dict = Depends(db.validate_token)) -> StreamingResponse:
    """ Adds a message to a thread. If the message is the first message in the thread,
        we set the name of the thread to the content of the message.
    """
    if cors_ok and token_params: 
        print(f'Token_params is {token_params}')
        # TODO(mwk): check that the user_id in the token matches the 
        # user_id associated with the thread_id. 
        try:
            db.append_message(token_params['user_id'], 
                              thread_id, 
                              req.role, 
                              req.content)
            # Now actually use Ansari. 
            history = db.get_thread_llm(thread_id, token_params['user_id'])
            if history['thread_name'] == None and len(history['messages']) > 1: 
                db.set_thread_name(thread_id, token_params['user_id'], history['messages'][0]['content'])
            return presenter.complete(history, 
                                      message_logger=MessageLogger(db, token_params['user_id'], thread_id))
        except psycopg2.Error as e:
            print(f'Error: {e}')
            raise HTTPException(status_code=500, detail="Database error")
    else: 
        raise HTTPException(status_code=403, detail="CORS not permitted")
    
@app.get("/api/v2/threads/{thread_id}")
async def get_thread(thread_id: int, 
                      cors_ok: bool =  Depends(validate_cors), 
                      token_params: dict = Depends(db.validate_token)): 
    if cors_ok and token_params: 
        print(f'Token_params is {token_params}')
        # TODO(mwk): check that the user_id in the token matches the 
        # user_id associated with the thread_id. 
        try:
            messages  = db.get_thread(thread_id, token_params['user_id'])
            return messages
        except psycopg2.Error as e:
            print(f'Error: {e}')
            raise HTTPException(status_code=500, detail="Database error")
    else: 
        raise HTTPException(status_code=403, detail="CORS not permitted")
    
@app.delete("/api/v2/threads/{thread_id}")
async def delete_thread(thread_id: int, 
                      cors_ok: bool =  Depends(validate_cors), 
                      token_params: dict = Depends(db.validate_token)): 
    if cors_ok and token_params: 
        print(f'Token_params is {token_params}')
        # TODO(mwk): check that the user_id in the token matches the 
        # user_id associated with the thread_id. 
        try:
            db.delete_thread(thread_id, token_params['user_id'])
        except psycopg2.Error as e:
            print(f'Error: {e}')
            raise HTTPException(status_code=500, detail="Database error")
    else: 
        raise HTTPException(status_code=403, detail="CORS not permitted")
    

class ThreadNameRequest(BaseModel): 
    name: str

@app.post("/api/v2/threads/{thread_id}/name")
async def set_thread_name(thread_id: int, 
                     req: ThreadNameRequest,
                     cors_ok: bool =  Depends(validate_cors), 
                     token_params: dict = Depends(db.validate_token)): 
    if cors_ok and token_params: 
        print(f'Token_params is {token_params}')
        # TODO(mwk): check that the user_id in the token matches the 
        # user_id associated with the thread_id. 
        try:
            messages  = db.set_thread_name(thread_id, token_params['user_id'], req.name)
            return messages
        except psycopg2.Error as e:
            print(f'Error: {e}')
            raise HTTPException(status_code=500, detail="Database error")
    else: 
        raise HTTPException(status_code=403, detail="CORS not permitted")

class SetPrefRequest(BaseModel):
    key: str
    value: str

@app.post("/api/v2/preferences")
async def set_pref(req: SetPrefRequest, 
                   cors_ok: bool =  Depends(validate_cors), 
                   token_params: dict = Depends(db.validate_token)):
    if cors_ok and token_params: 
        print(f'Token_params is {token_params}')
        # Now create a thread and return the thread_id
        try:
            db.set_pref(token_params['user_id'], req.key, req.value)

        except psycopg2.Error as e:
            print(f'Error: {e}')
            raise HTTPException(status_code=500, detail="Database error")
    else: 
        raise HTTPException(status_code=403, detail="CORS not permitted")
    

@app.get("/api/v2/preferences")
async def get_prefs(cors_ok: bool =  Depends(validate_cors), 
                   token_params: dict = Depends(db.validate_token)):
    if cors_ok and token_params: 
        print(f'Token_params is {token_params}')
        # Now create a thread and return the thread_id
        try:
            prefs = db.get_prefs(token_params['user_id'])
            return prefs

        except psycopg2.Error as e:
            print(f'Error: {e}')
            raise HTTPException(status_code=500, detail="Database error")
    else: 
        raise HTTPException(status_code=403, detail="CORS not permitted")

    
class ResetPasswordRequest(BaseModel):
    email: str

@app.post("/api/v2/request_password_reset")
async def request_password_reset(req: ResetPasswordRequest,
                                 cors_ok: bool =  Depends(validate_cors),
                                ):
    if cors_ok: 
        print(f'Request received to reset {req.email}')
        if db.account_exists(req.email):
            user_id, _,_,_ = db.retrieve_user_info(req.email)
            reset_token = db.generate_token(user_id, 'reset')
            db.save_reset_token(user_id, reset_token)
            tenv = Environment(loader=FileSystemLoader(template_dir))
            template = tenv.get_template('password_reset.html')
            rendered_template = template.render(reset_token=reset_token)
            message = Mail(
                from_email='feedback@ansari.chat',
                to_emails=f'{req.email}',
                subject='Ansari Password Reset',
                html_content=rendered_template)
            
            try:
                if os.environ.get('SENDGRID_API_KEY'): 
                    sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
                    response = sg.send(message)
                    print(response.status_code)
                    print(response.body)
                    print(response.headers)
                else: 
                    print('WARNING: No sendgrid key')
                    print(f'Would have sent: {message}')
                return {'status': 'success'}
            except Exception as e:
                print(e.message)
        else: 
            # Even iuf the email doesn't exist, we return success.
            # So this can't be used to work out who is on our system. 
            return {'status': 'success'}
        
    else: 
        raise HTTPException(status_code=403, detail = "CORS note permitted.")

@app.post("/api/v2/update_password")
async def update_password(cors_ok: bool =  Depends(validate_cors),
                        token_params: dict = Depends(db.validate_reset_token), 
                        password: str = None):
    """ Update the user's password if you have a valid token
    """
    if cors_ok and token_params:
        print(f'Token_params is {token_params}')
        try:
            password_hash = db.hash_password(password)
            passwd_quality = zxcvbn(password)
            if passwd_quality['score'] < 2: 
                raise HTTPException(status_code=400, 
                                    detail=f"Password is too weak. Suggestions: " 
                                    + ','.join(passwd_quality['feedback']['suggestions']))
            db.update_password(token_params['email'], password_hash)
        except psycopg2.Error as e:
            print(f'Error: {e}')
            raise HTTPException(status_code=500, detail="Database error")
    else:
        raise HTTPException(status_code=403, detail = "Invalid username or password")
    
class PasswordReset(BaseModel):
    reset_token: str
    new_password: str

@app.post("/api/v2/reset_password")
async def reset_password(req: PasswordReset, 
                         cors_ok: bool =  Depends(validate_cors)):
    """ Resets the user's password if you have a reset token. 
    """
    token_params = db.validate_reset_token(req.reset_token) 
    if cors_ok:
        print(f'Token_params is {token_params}')
        try:
            password_hash = db.hash_password(req.new_password)
            passwd_quality = zxcvbn(req.new_password)
            if passwd_quality['score'] < 2: 
                raise HTTPException(status_code=400, 
                                    detail=f"Password is too weak. Suggestions: " 
                                    + ','.join(passwd_quality['feedback']['suggestions']))
            db.update_password(token_params['user_id'], password_hash)
            return {'status': 'success'}
        except psycopg2.Error as e:
            print(f'Error: {e}')
            raise HTTPException(status_code=500, detail="Database error")
    else:
        raise HTTPException(status_code=403, detail = "Invalid username or password")

@app.post("/api/v1/complete")
async def complete(request: Request):
    """
    Provides a response to a user's input.
    The input is a list of messages, each with with 
    a role and a text field. Roles are typically 
    'user' or 'assistant.' The client should maintain the 
    record of the conversation client side. 

    It returns a stream of tokens (a token is a part of a word). 

    """
    print(f'Raw request is {request.headers}')
    origin = request.headers.get('origin','')
    mobile = request.headers.get('x-mobile-ansari', '')
    if origin in origins or mobile == 'ANSARI': 
        body = await request.json()
        print(f'Request received > {body}.')
        #messages = [
        #    {"role:": "user", "text": "Hello, Ansari!"},
        #]
        return presenter.complete(body)
    else: 
        raise HTTPException(status_code=403, detail="CORS not permitted")
   