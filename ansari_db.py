import os
import bcrypt
from typing import Any, Dict, List
import jwt
from jwt import PyJWTError
import psycopg2
from datetime import datetime, timedelta
from fastapi import Depends, FastAPI, Request, HTTPException
import logging

MAX_THREAD_NAME_LENGTH = 100

class MessageLogger:
    """A simplified interface to AnsariDB so that we can log messages 
    without having to share details about the user_id and the thread_id
    """
    def __init__(self, db, user_id: int, thread_id: int) -> None:
        self.user_id = user_id
        self.thread_id = thread_id
        self.db = db

    def log(self, role, content, function_name = None):
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

    def generate_token(self, user_id, token_type = "login"):
        """ Generate a new token for the user. There are two types of tokens:
        - login: This is a token that is used to authenticate the user.
        - reset: This is a token that is used to reset the user's password.
        """
        payload = {
            "user_id": user_id,
            "type": token_type,  
            "exp": datetime.utcnow() + timedelta(days=1)
        }
        return jwt.encode(payload, self.token_secret_key, algorithm=self.ALGORITHM)

    def validate_token(self, request: Request) -> Dict[str, str]:
        try:
            # Extract token from the authorization header (expected format: "Bearer <token>")
            token = request.headers.get('Authorization', '').split(' ')[1]
            logging.info(f'Token is {token}')
            payload = jwt.decode(token, self.token_secret_key, algorithms=[self.ALGORITHM])
            logging.info(f'Payload is {payload}')
            # Check that the token is in our database. 
            cur = self.conn.cursor()
            select_cmd = '''SELECT user_id FROM user_tokens WHERE user_id = %s AND token = %s;'''
            cur.execute(select_cmd, (payload['user_id'], token) )
            result = cur.fetchone()
            cur.close()
            if result is None:
                logging.warning('Could not find token in database.')
                raise HTTPException(status_code=403, detail="Could not validate credentials")
            elif datetime.utcfromtimestamp(payload['exp']) < datetime.utcnow():
                logging.warning('Token was expired.')
                raise HTTPException(status_code=403, detail="Token has expired")
            else: 
                logging.info(f'Payload is {payload}')
                return payload
        except PyJWTError:
            raise HTTPException(status_code=403, detail="Could not validate credentials")
        finally: 
            if cur: 
                cur.close()

    def validate_reset_token(self, token: str) -> Dict[str, str]:
        try:
            logging.info(f'Token is {token}')
            payload = jwt.decode(token, 
                                 self.token_secret_key, algorithms=[self.ALGORITHM])
            # Check that the token is in our database. 
            cur = self.conn.cursor()
            select_cmd = '''SELECT user_id FROM reset_tokens WHERE user_id = %s AND token = %s;'''
            cur.execute(select_cmd, (payload['user_id'], token) )
            result = cur.fetchone()
            cur.close()
            if result is None: 
                raise HTTPException(status_code=403, detail="Unknown user or token")
            elif payload['type'] != 'reset':
                raise HTTPException(status_code=403, detail="Token is not a reset token")
            elif datetime.utcfromtimestamp(payload['exp']) < datetime.utcnow():
                raise HTTPException(status_code=403, detail="Token has expired")
            else: 
                logging.info('Payload is ', payload)
                return payload
        except PyJWTError:
            raise HTTPException(status_code=403, detail="Could not validate credentials")
        finally: 
            if cur: 
                cur.close()

    def register(self, email, first_name, last_name, password_hash):
        try: 
            cur = self.conn.cursor()
            insert_cmd = '''INSERT INTO users (email, password_hash, first_name, last_name) values (%s, %s, %s, %s);'''
            cur.execute(insert_cmd, (email, password_hash, first_name, last_name) )
            self.conn.commit()
            return {"status": "success"}
        except Exception as e:
            logging.warning('Error is ', e)
            return {"status": "failure", "error": str(e)}
        finally: 
            if cur: 
                cur.close() 

    def account_exists(self, email):
        try: 
            cur = self.conn.cursor()
            select_cmd = '''SELECT id FROM users WHERE email = %s;'''
            cur.execute(select_cmd, (email, ) )
            result = cur.fetchone()
            return result is not None
        except Exception as e:
            logging.warning('Error is ', e)
            return False
        finally: 
            if cur: 
                cur.close()
 
    
    def save_token(self, user_id, token):
        try: 
            cur = self.conn.cursor()
            insert_cmd = "INSERT INTO user_tokens (user_id, token) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET token = %s"
            cur.execute(insert_cmd, (user_id, token, token))
            self.conn.commit()
            return {"status": "success", "token": token}
        except Exception as e:
            logging.warning('Error is ', e)
            return {"status": "failure", "error": str(e)}
        finally:
            if cur: 
                cur.close()

    def save_reset_token(self, user_id, token):
        try: 
            cur = self.conn.cursor()
            insert_cmd = "INSERT INTO reset_tokens (user_id, token) VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET token = %s"
            cur.execute(insert_cmd, (user_id, token, token))
            self.conn.commit()
            return {"status": "success", "token": token}
        except Exception as e:
            logging.warning('Error is ', e)
            return {"status": "failure", "error": str(e)}
        finally:
            if cur: 
                cur.close()    
    
    def retrieve_user_info(self, email):
        try: 
            cur = self.conn.cursor()
            select_cmd = '''SELECT id, password_hash, first_name, last_name FROM users WHERE email = %s;'''
            cur.execute(select_cmd, (email, ) )
            result = cur.fetchone()
            user_id = result[0] 
            existing_hash = result[1]
            first_name = result[2]
            last_name = result[3]
            return user_id, existing_hash, first_name, last_name
        except Exception as e:
            logging.warning('Error is ', e)
            return None, None, None, None
        finally: 
          if cur: 
              cur.close()


    def add_feedback(self, user_id, thread_id, message_id, feedback_class,  comment):
        try: 
            cur = self.conn.cursor()
            insert_cmd = '''INSERT INTO feedback (user_id, thread_id, message_id, class, comment) values (%s, %s, %s, %s, %s);'''
            cur.execute(insert_cmd, (user_id, thread_id, message_id, feedback_class, comment) )
            return {"status": "success"}
        except Exception as e:
            logging.warning('Error is ', e)
            return {"status": "failure", "error": str(e)}
        finally: 
            if cur: 
                cur.close()
    
    def create_thread(self, user_id):
        try: 
            cur = self.conn.cursor()
            insert_cmd = '''INSERT INTO threads (user_id) values (%s) RETURNING id;'''
            cur.execute(insert_cmd, (user_id,) )
            inserted_id = cur.fetchone()[0]
            self.conn.commit()
            return {"status": "success", "thread_id": inserted_id}
        
        except Exception as e:
            logging.warning('Error is ', e)
            return {"status": "failure", "error": str(e)}
        
        finally: 
            if cur: 
                cur.close()
    
    def get_all_threads(self, user_id):
        try: 
            cur = self.conn.cursor()
            select_cmd = '''SELECT id, name, updated_at FROM threads WHERE user_id = %s;'''
            cur.execute(select_cmd, (user_id,) )
            result = cur.fetchall()
            return [{"thread_id": x[0], "thread_name": x[1], "updated_at": x[2]} for x in result]
        except Exception as e:
            logging.warning('Error is ', e)
            return []
        finally:
            if cur: 
                cur.close()

    def set_thread_name(self, thread_id, user_id, thread_name):
        try: 
            cur = self.conn.cursor()
            insert_cmd = '''INSERT INTO threads (id, user_id, name) values (%s, %s, %s) ON CONFLICT (id) DO UPDATE SET name = %s;'''
            cur.execute(insert_cmd, (thread_id, user_id, thread_name[:MAX_THREAD_NAME_LENGTH], thread_name[:MAX_THREAD_NAME_LENGTH]) )
            self.conn.commit()
            return {"status": "success"}
        except Exception as e:
            logging.warning('Error is ', e)
            return {"status": "failure", "error": str(e)}   
        finally:
            if cur: 
                cur.close()
    
    def append_message(self, user_id, thread_id, role, content, function_name = None): 
        try: 
            cur = self.conn.cursor()
            insert_cmd = '''INSERT INTO messages (thread_id, user_id, role, content, function_name) values (%s, %s, %s, %s, %s);'''
            cur.execute(insert_cmd, (thread_id, user_id, role, content, function_name) )
            # Appending a message should update the thread's updated_at field.
            update_cmd = '''UPDATE threads SET updated_at = now() WHERE id = %s AND user_id = %s;'''
            cur.execute(update_cmd, (thread_id, user_id) )
            self.conn.commit()
            return {"status": "success"}
        except Exception as e:
            logging.warning('Error is ', e)
            return {"status": "failure", "error": str(e)}
        finally:
            if cur: 
                cur.close()
    
    def get_thread(self, thread_id, user_id):
        try: 
            # We need to check user_id to make sure that the user has access to the thread.
            cur = self.conn.cursor()
            select_cmd = '''SELECT id, role, content FROM messages WHERE thread_id = %s AND user_id = %s ORDER BY updated_at;'''
            cur.execute(select_cmd, (thread_id, user_id) )
            result = cur.fetchall()
            select_cmd = '''SELECT name FROM threads WHERE id = %s AND user_id = %s;'''
            cur.execute(select_cmd, (thread_id, user_id) )
            if cur.rowcount == 0:
                raise HTTPException(status_code=401, detail="Incorrect user_id or thread_id.")
            thread_name = cur.fetchone()[0]
            retval = {'thread_name': thread_name, 
                      'messages': [self.convert_message(x) for x in result if x[1] != 'function']}
            return retval
        except Exception as e:
            logging.warning(f'Error is {e}')
            return {}
        finally:
            if cur: 
                cur.close()
    
    def get_thread_llm(self, thread_id, user_id):
        try: 
            # We need to check user_id to make sure that the user has access to the thread.
            cur = self.conn.cursor()
            select_cmd = '''SELECT role, content, function_name FROM messages WHERE thread_id = %s AND user_id = %s ORDER BY timestamp;'''
            cur.execute(select_cmd, (thread_id, user_id) )
            result = cur.fetchall()
            select_cmd = '''SELECT name FROM threads WHERE id = %s AND user_id = %s;'''
            cur.execute(select_cmd, (thread_id, user_id) )
            if cur.rowcount == 0:
                raise HTTPException(status_code=401, detail="Incorrect user_id or thread_id.")
            thread_name = cur.fetchone()[0]
            # Now convert into the standard format
            retval = {'thread_name': thread_name, 
                      'messages': [self.convert_message_llm(x) for x in result]}
            return retval
        except Exception as e:
            logging.warning('Error is ', e)
            return {}
        finally:
            if cur: 
                cur.close()

    def delete_thread(self, thread_id, user_id):
        try: 
            # We need to ensure that the user_id has access to the thread.
            # We must delete the messages associated with the thread first. 
            cur = self.conn.cursor()
            delete_cmd = '''DELETE FROM messages WHERE thread_id = %s and user_id = %s;'''
            cur.execute(delete_cmd, (thread_id, user_id) )
            self.conn.commit()
            delete_cmd = '''DELETE FROM threads WHERE id = %s AND user_id = %s;'''
            cur.execute(delete_cmd, (thread_id, user_id ) )
            self.conn.commit()
            return {"status": "success"}
        except Exception as e:
            logging.warning('Error is ', e)
            return {"status": "failure", "error": str(e)}
        finally:
            if cur: 
                cur.close()
    
    def logout(self, user_id):
        try: 
            cur = self.conn.cursor()
            delete_cmd = '''DELETE FROM user_tokens WHERE user_id = %s;'''
            cur.execute(delete_cmd, (user_id, ) )
            self.conn.commit()
            return {"status": "success"}
        except Exception as e:
            logging.warning('Error is ', e)
            return {"status": "failure", "error": str(e)}
        finally:
            if cur: 
                cur.close()
    
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
    
    def update_password(self, user_id, new_password_hash):
        try: 
            cur = self.conn.cursor()
            update_cmd = '''UPDATE users SET password_hash = %s WHERE id = %s;'''
            cur.execute(update_cmd, (new_password_hash, user_id) )
            self.conn.commit()
            cur.close()
            return {"status": "success"}
        except Exception as e:
            logging.warning('Error is ', e)
            return {"status": "failure", "error": str(e)}
        finally:
            if cur: 
                cur.close()

    
    def convert_message(self, msg):
        return {'id': msg[0], 'role': msg[1], 'content': msg[2]}
        
    def convert_message_llm(self, msg):
        if msg[2]: 
            return {'role': msg[0], 'content': msg[1], 'function_name': msg[2]}
        else:
            return {'role': msg[0], 'content': msg[1]}