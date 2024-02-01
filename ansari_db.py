import os
import bcrypt
from typing import Any, Dict, List
import jwt
from jwt import PyJWTError
import psycopg2
from datetime import datetime, timedelta
from fastapi import Depends, FastAPI, Request, HTTPException

class MessageLogger:
    """A simplified interface to AnsariDB so that we can log messages 
    without having to share details about the user_id and the thread_id
    """
    def __init__(self, db, user_id: int, thread_id: int) -> None:
        self.user_id = user_id
        self.thread_id = thread_id
        self.db = db

    def log(self, role, content, function_name = None):
        #print(f'Self db is {self.db}')
        self.db.append_message(self.user_id, self.thread_id, role, content, function_name)

class AnsariDB:
    """ Handles all database interactions. 
    """
    db_url = os.getenv('DATABASE_URL', 'postgresql://mwk@localhost:5432/mwk')
    token_secret_key = os.getenv('SECRET_KEY', 'secret')
    ALGORITHM = "HS256"
    ENCODING = "utf-8"

    def __init__(self) -> None:
        self.conn = psycopg2.connect(self.db_url)

    def hash_password(self, password):
        # Hash a password with a randomly-generated salt
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())

        # Return the hashed password
        return hashed.decode(self.ENCODING)

    def check_password(self, password, hashed):
        # Check if the provided password matches the hash
        return bcrypt.checkpw(password.encode(), hashed.encode(self.ENCODING))

    def generate_token(self, user_id):
        payload = {
            "user_id": user_id,
            "exp": datetime.utcnow() + timedelta(days=1)
        }
        return jwt.encode(payload, self.token_secret_key, algorithm=self.ALGORITHM)

    def validate_token(self, request: Request) -> Dict[str, str]:
        try:
            # Extract token from the authorization header (expected format: "Bearer <token>")
            token = request.headers.get('Authorization', '').split(' ')[1]
            print('Token is ', token)
            payload = jwt.decode(token, self.token_secret_key, algorithms=[self.ALGORITHM])
            # Check that the token is in our database. 
            cur = self.conn.cursor()
            select_cmd = '''SELECT user_id FROM user_tokens WHERE user_id = %s AND token = %s;'''
            cur.execute(select_cmd, (payload['user_id'], token) )
            result = cur.fetchone()
            cur.close()
            if result is None:
                raise HTTPException(status_code=403, detail="Could not validate credentials")
            else: 
                return payload
            print('Payload is ', payload)
            return payload
        except PyJWTError:
            raise HTTPException(status_code=403, detail="Could not validate credentials")
        
    def register(self, email, first_name, last_name, password_hash):
        cur = self.conn.cursor()
        try: 

            insert_cmd = '''INSERT INTO users (email, password_hash, first_name, last_name) values (%s, %s, %s, %s);'''
            cur.execute(insert_cmd, (email, password_hash, first_name, last_name) )
            self.conn.commit()
            return {"status": "success"}
        finally: 
            if cur: 
                cur.close() 

    def account_exists(self, email):
        cur = self.conn.cursor()
        select_cmd = '''SELECT id FROM users WHERE email = %s;'''
        cur.execute(select_cmd, (email, ) )
        result = cur.fetchone()
        cur.close()
        return result is not None
 
    
    def save_token(self, user_id, token):
        cur = self.conn.cursor()
        insert_cmd = "INSERT INTO user_tokens (user_id, token) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET token = %s"
        cur.execute(insert_cmd, (user_id, token, token))
        self.conn.commit()
        cur.close()
        return {"status": "success", "token": token}
    
    def check_user_exists(self, email):
        cur = self.conn.cursor()
        select_cmd = '''SELECT id FROM users WHERE email = %s;'''
        cur.execute(select_cmd, (email, ) )
        result = cur.fetchone()
        if result:
            return True
        else: 
            return False
        cur.close()
        
    
    def retrieve_password(self, email):
        cur = self.conn.cursor()
        select_cmd = '''SELECT id, password_hash, first_name, last_name FROM users WHERE email = %s;'''
        cur.execute(select_cmd, (email, ) )
        result = cur.fetchone()
        user_id = result[0] 
        existing_hash = result[1]
        first_name = result[2]
        last_name = result[3]
        cur.close()
        return user_id, existing_hash, first_name, last_name
    
    def create_thread(self, user_id):
        cur = self.conn.cursor()
        insert_cmd = '''INSERT INTO threads (user_id) values (%s) RETURNING id;'''
        cur.execute(insert_cmd, (user_id,) )
        inserted_id = cur.fetchone()[0]
        self.conn.commit()
        cur.close()
        return {"status": "success", "thread_id": inserted_id}
    
    def get_all_threads(self, user_id):
        cur = self.conn.cursor()
        select_cmd = '''SELECT id, name, created_at FROM threads WHERE user_id = %s;'''
        cur.execute(select_cmd, (user_id,) )
        result = cur.fetchall()
        cur.close()
        return [{"thread_id": x[0], "thread_name": x[1], "created_at": x[2]} for x in result]

    def set_thread_name(self, thread_id, user_id, thread_name):
        cur = self.conn.cursor()
        insert_cmd = '''INSERT INTO threads (id, user_id, name) values (%s, %s, %s) ON CONFLICT (id) DO UPDATE SET name = %s;'''
        cur.execute(insert_cmd, (thread_id, user_id, thread_name, thread_name) )
        self.conn.commit()
        cur.close()
        return {"status": "success"}
    
    def append_message(self, user_id, thread_id, role, content, function_name = None): 
        cur = self.conn.cursor()
        insert_cmd = '''INSERT INTO messages (thread_id, user_id, role, content, function_name) values (%s, %s, %s, %s, %s);'''
        cur.execute(insert_cmd, (thread_id, user_id, role, content, function_name) )
        self.conn.commit()
        cur.close()
        return {"status": "success"}
    
    def get_thread(self, thread_id):
        cur = self.conn.cursor()
        select_cmd = '''SELECT role, content, function_name FROM messages WHERE thread_id = %s ORDER BY timestamp;'''
        cur.execute(select_cmd, (thread_id, ) )
        result = cur.fetchall()
        select_cmd = '''SELECT name FROM threads WHERE id = %s;'''
        cur.execute(select_cmd, (thread_id, ) )
        thread_name = cur.fetchone()[0]
        # Now convert into the standard format
        retval = {'thread_name': thread_name, 
                  'messages': [self.convert_message(x) for x in result]}
        cur.close()
        return retval
    
    def delete_thread(self, thread_id):
        # We must delete the messages associated with the thread first. 
        cur = self.conn.cursor()
        delete_cmd = '''DELETE FROM messages WHERE thread_id = %s;'''
        cur.execute(delete_cmd, (thread_id, ) )
        self.conn.commit()
        delete_cmd = '''DELETE FROM threads WHERE id = %s;'''
        cur.execute(delete_cmd, (thread_id, ) )
        self.conn.commit()
        cur.close()
        return {"status": "success"}
    
    def logout(self, user_id):
        cur = self.conn.cursor()
        delete_cmd = '''DELETE FROM user_tokens WHERE user_id = %s;'''
        cur.execute(delete_cmd, (user_id, ) )
        self.conn.commit()
        cur.close()
        return {"status": "success"}
    
    def set_pref(self, user_id, key, value):
        cur = self.conn.cursor()
        insert_cmd = '''INSERT INTO preferences (user_id, pref_key, pref_value) values (%s, %s, %s) ON CONFLICT (user_id, pref_key) DO UPDATE SET pref_value = %s;'''
        cur.execute(insert_cmd, (user_id, key, value, value) )
        self.conn.commit()
        cur.close()
        return {"status": "success"}
    
    def get_prefs(self, user_id):
        cur = self.conn.cursor()
        select_cmd = '''SELECT pref_key, pref_value FROM preferences WHERE user_id = %s'''
        cur.execute(select_cmd, (user_id,) )
        result = cur.fetchall() 
        cur.close()
        retval = {}
        for x in result:
            retval[x[0]] = x[1]
        return retval
    
    def convert_message(self, msg):
        if msg[2]: 
            return {'role': msg[0], 'content': msg[1], 'function_name': msg[2]}
        else:
            return {'role': msg[0], 'content': msg[1]}