# TODO NOW: ask vscode copilot question when pulling MessageRecorder

import inspect
import json
import logging
import re
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterable, Literal, Optional, Tuple, Union
import uuid

import bcrypt
import jwt
import psycopg2
import psycopg2.pool
from fastapi import HTTPException, Request
from jwt import ExpiredSignatureError, InvalidTokenError

from ansari.ansari_logger import get_logger
from ansari.config import Settings, get_settings

logger = get_logger("DEBUG")


class MessageLogger:
    """A simplified interface to AnsariDB so that we can log messages
    without having to share details about the user_id and the thread_id
    """

    def __init__(self, db: "AnsariDB", user_id: int, thread_id: int, to_whatsapp: bool = False) -> None:
        self.user_id = user_id
        self.thread_id = thread_id
        self.to_whatsapp = to_whatsapp
        logger.debug(f"DB is {db}")
        self.db = db

    def log(self, role: str, content: str, tool_name: str = None, tool_details: dict[str, dict] = None, ref_list: list = None) -> None:
        if not self.to_whatsapp:
            self.db.append_message(self.user_id, self.thread_id, role, content, tool_name, tool_details, ref_list)
        else:
            self.db.append_message_whatsapp(
                self.user_id,
                self.thread_id,
                {"role": role, "content": content, "tool_name": tool_name, "tool_details": tool_details, "ref_list": ref_list}
            )


class AnsariDB:
    """Handles all database interactions."""

    def __init__(self, settings: Settings) -> None:
        self.db_url = str(settings.DATABASE_URL)
        self.token_secret_key = settings.SECRET_KEY.get_secret_value()
        self.ALGORITHM = settings.ALGORITHM
        self.ENCODING = settings.ENCODING
        self.db_connection_pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=str(settings.DATABASE_URL),
        )

    @contextmanager
    def get_connection(self):
        conn = self.db_connection_pool.getconn()
        try:
            yield conn
        finally:
            self.db_connection_pool.putconn(conn)

    def hash_password(self, password):
        # Hash a password with a randomly-generated salt
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())

        # Return the hashed password
        return hashed.decode(self.ENCODING)

    def check_password(self, password, hashed):
        # Check if the provided password matches the hash
        return bcrypt.checkpw(password.encode(), hashed.encode(self.ENCODING))

    def generate_token(self, user_id, token_type="access", expiry_hours=1):
        """Generate a new token for the user. There are three types of tokens:
        - access: This is a token that is used to authenticate the user.
        - refresh: This is a token that is used to extend the user session when the access token expires.
        - reset: This is a token that is used to reset the user's password.
        """
        if token_type not in ["access", "reset", "refresh"]:
            raise ValueError("Invalid token type")
        payload = {
            "user_id": str(user_id),
            "type": token_type,
            "exp": datetime.now(timezone.utc) + timedelta(hours=expiry_hours),
        }
        return jwt.encode(payload, self.token_secret_key, algorithm=self.ALGORITHM)

    def decode_token(self, token: str) -> dict[str, str]:
        try:
            payload = jwt.decode(token, self.token_secret_key, algorithms=[self.ALGORITHM])

            # Convert user_id to a UUID, throw ValueError otherwise
            payload["user_id"] = uuid.UUID(payload["user_id"], version=4)

            return payload
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid token")
        except ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired")
        except InvalidTokenError as e:
            raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
        except Exception:
            logger.exception("Unexpected error during token decoding")
            raise HTTPException(
                status_code=401,
                detail="Could not validate credentials",
            )

    def _get_token_from_request(self, request: Request) -> str:
        try:
            auth_header = request.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                raise HTTPException(
                    status_code=401,
                    detail="Invalid authorization header format",
                )
            return auth_header.split(" ")[1]
        except IndexError:
            raise HTTPException(
                status_code=401,
                detail="Authorization header is malformed",
            )

    def _execute_query(
        self,
        query: Union[str, list[str]],
        params: Union[tuple, list[tuple]],
        which_fetch: Union[Literal["one", "all"], list[Literal["one", "all"]]] = "",
        commit_after: Literal["each", "all"] = "each",
    ) -> list[Optional[any]]:
        """
        Executes one or more SQL queries with the provided parameters and fetch types.

        Args:
            query (Union[str, List[str]]): A single SQL query string or a list of SQL query strings.
            params (Union[tuple, List[tuple]]): A single tuple of parameters or a list of tuples of parameters.
            which_fetch (Union[Literal["one", "all"], List[Literal["one", "all"]]]):
                A single fetch type or a list of fetch types. Each fetch type can be:
                - "one": Fetch one row.
                - "all": Fetch all rows.
                - Any other value: Do not fetch any rows.
            commit_after (Literal["each", "all"]): Whether to commit the transaction after each query is executed,
                or only after all of them are executed.

        Returns:
            List[Optional[Any]]:
                - When single or multiple queries are executed:
                    - Returns a list of results, where each "result" is:
                        - A single result if which_fetch is "one".
                        - A list of results if which_fetch is "all".
                        - Else, returns None.

            Note: the word "result" means a row in the DB,
                which could be a tuple if more than 1 column is selected in the query.

        Raises:
            ValueError: If an invalid fetch type is provided.
        """
        # If query is a single string, we assume that params and which_fetch are also non-list values
        if isinstance(query, str):
            query = [query]
            params = [params]
            which_fetch = [which_fetch]
        # else, we assume that params and which_fetch are lists of the same length
        # and do a list-conversion just in case they are strings
        else:
            if isinstance(params, str):
                params = [params] * len(query)
            if isinstance(which_fetch, str):
                which_fetch = [which_fetch] * len(query)

        caller_function_name = inspect.stack()[1].function
        logger.debug(f"Running DB function: {caller_function_name}()")

        results = []
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                for q, p, wf in zip(query, params, which_fetch):
                    cur.execute(q, p)
                    result = None
                    if wf.lower() == "one":
                        result = cur.fetchone()
                    elif wf.lower() == "all":
                        result = cur.fetchall()

                    # Remove possible SQL comments at the start of the q variable
                    q = re.sub(r"^\s*--.*\n|^\s*---.*\n", "", q, flags=re.MULTILINE)

                    if not q.strip().lower().startswith("select") and commit_after.lower() == "each":
                        conn.commit()

                    results.append(result)

                if commit_after.lower() == "all":
                    conn.commit()

        # Return a list when 1 or more queries are executed \
        # (or a list of a single None if it was a non-fetch query)
        return results

    def _validate_token_in_db(self, user_id: str, token: str, table: str) -> bool:
        try:
            select_cmd = f"SELECT user_id FROM {table} WHERE user_id = %s AND token = %s;"
            # Note: the "[0]" is added here because `select_cmd` is not a list
            result = self._execute_query(select_cmd, (user_id, token), "one")[0]
            return result is not None
        except Exception:
            logger.exception("Database error during token validation")
            raise HTTPException(status_code=500, detail="Internal server error")

    def validate_token(self, request: Request) -> dict[str, str]:
        token = self._get_token_from_request(request)
        logger.info(f"Token is {token}")
        payload = self.decode_token(token)
        logger.info(f"Payload is {payload}")

        token_type = payload.get("type")
        if token_type not in ["access", "refresh"]:
            raise HTTPException(status_code=401, detail="Invalid token type")

        table_map = {
            "access": "access_tokens",
            "refresh": "refresh_tokens",
        }
        db_table = table_map[token_type]

        if not self._validate_token_in_db(payload["user_id"], token, db_table):
            logger.warning("Could not find token in database.")
            raise HTTPException(
                status_code=401,
                detail="Could not validate credentials",
            )

        return payload

    def validate_reset_token(self, token: str) -> dict[str, str]:
        logger.info(f"Token is {token}")
        payload = self.decode_token(token)

        if payload.get("type") != "reset":
            raise HTTPException(status_code=401, detail="Token is not a reset token")

        if not self._validate_token_in_db(payload["user_id"], token, "reset_tokens"):
            raise HTTPException(status_code=401, detail="Unknown user or token")

        logger.info(f"Payload is {payload}")
        return payload

    def register(self, email, first_name, last_name, password_hash):
        try:
            normalized_email = email.strip().lower()
            insert_cmd = """INSERT INTO users (email, password_hash, first_name, last_name) values (%s, %s, %s, %s);"""
            self._execute_query(insert_cmd, (normalized_email, password_hash, first_name, last_name))
            return {"status": "success"}
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {"status": "failure", "error": str(e)}

    def register_whatsapp(self, phone_num: str, db_cols_to_vals: dict) -> dict:
        """
        Registers a WhatsApp user in the users_whatsapp table.

        Args:
            phone_num (str): The phone number of the user.
            db_cols_to_vals (dict): A dictionary where keys are column names of the users_whatsapp table
                                    and values are the corresponding values to be inserted.
                                    Column names can be checked from the users_whatsapp DB table.

        Returns:
            dict: A dictionary with the status of the operation.

        Raises:
            ValueError: If no fields are provided to insert.
        """
        try:
            # Add phone_num to the dictionary
            db_cols_to_vals["phone_num"] = phone_num

            # Construct the SQL INSERT statement dynamically based on the provided dictionary
            columns = ", ".join(db_cols_to_vals.keys())
            placeholders = ", ".join(["%s"] * len(db_cols_to_vals))
            insert_cmd = f"INSERT INTO users_whatsapp ({columns}) VALUES ({placeholders});"

            self._execute_query(insert_cmd, tuple(db_cols_to_vals.values()))

            return {"status": "success"}
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {"status": "failure", "error": str(e)}

    def account_exists(self, email):
        try:
            normalized_email = email.strip().lower()
            select_cmd = """SELECT id FROM users WHERE email = %s;"""
            result = self._execute_query(select_cmd, (normalized_email,), "one")[0]
            return result is not None
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return False

    def account_exists_whatsapp(self, phone_num):
        try:
            select_cmd = """SELECT id FROM users_whatsapp WHERE phone_num = %s;"""
            result = self._execute_query(select_cmd, (phone_num,), "one")[0]
            return result is not None
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return False

    def save_access_token(self, user_id, token):
        try:
            insert_cmd = "INSERT INTO access_tokens (user_id, token) VALUES (%s, %s) RETURNING id;"
            result = self._execute_query(insert_cmd, (user_id, token), "one")[0]
            inserted_id = result[0] if result else None
            return {
                "status": "success",
                "token": token,
                "token_db_id": inserted_id,
            }
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {"status": "failure", "error": str(e)}

    def save_refresh_token(self, user_id, token, access_token_id):
        try:
            insert_cmd = "INSERT INTO refresh_tokens (user_id, token, access_token_id) VALUES (%s, %s, %s);"
            logger.info(f"Insert command: {insert_cmd}, params: ({user_id}, {token}, {access_token_id})")   
            self._execute_query(insert_cmd, (user_id, token, access_token_id))
            return {"status": "success", "token": token}
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {"status": "failure", "error": str(e)}

    def save_reset_token(self, user_id, token):
        try:
            insert_cmd = (
                "INSERT INTO reset_tokens (user_id, token) "
                + "VALUES (%s, %s) ON CONFLICT (user_id) DO UPDATE SET token = %s;"
            )
            self._execute_query(insert_cmd, (user_id, token, token))
            return {"status": "success", "token": token}
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {"status": "failure", "error": str(e)}

    def retrieve_user_info(self, email):
        try:
            normalized_email = email.strip().lower()
            select_cmd = "SELECT id, password_hash, first_name, last_name FROM users WHERE email = %s;"
            result = self._execute_query(select_cmd, (normalized_email,), "one")[0]
            if result:
                user_id, existing_hash, first_name, last_name = result
                return user_id, existing_hash, first_name, last_name
            return None, None, None, None
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return None, None, None, None

    def retrieve_user_info_by_user_id(self, id):
        try:
            select_cmd = "SELECT id, email, first_name, last_name FROM users WHERE id = %s;"
            result = self._execute_query(select_cmd, (id,), "one")[0]
            if result:
                user_id, email, first_name, last_name = result
                return user_id, email, first_name, last_name
            return None, None, None, None
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return None, None, None, None

    def retrieve_user_info_whatsapp(self, phone_num: str, db_cols: Union[list, str]) -> Optional[Tuple]:
        """
        Retrieves user information from the users_whatsapp table.

        Args:
            phone_num (str): The phone number of the user.
            db_cols (Union[list, str]): A (list of) column name(s) to be retrieved from the users_whatsapp table.
                        Column names can be checked from the users_whatsapp DB table.

        Returns:
            Optional[Union[Tuple, Any]]: A tuple containing the requested fields if
                        multiple columns are requested (i.e., len(db_cols) >= 2),
                        or a single value if only one column is requested,
                        or None if no user is found.

        Raises:
            ValueError: If 'phone_num' is not included in db_cols.
            Exception: If an error occurs during the database query.
        """
        if isinstance(db_cols, str):
            db_cols = [db_cols]

        if not db_cols:
            raise ValueError("At least one field must be provided to retrieve.")

        try:
            # Construct the SELECT statement based on the provided list of columns
            select_cmd = f"SELECT {', '.join(db_cols)} FROM users_whatsapp WHERE phone_num = %s;"
            result = self._execute_query(select_cmd, (phone_num,), "one")[0]
            if result:
                return result
            return None
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return None

    def add_feedback(self, user_id, thread_id, message_id, feedback_class, comment):
        try:
            insert_cmd = (
                "INSERT INTO feedback (user_id, thread_id, message_id, class, comment)" + " VALUES (%s, %s, %s, %s, %s);"
            )
            self._execute_query(insert_cmd, (user_id, thread_id, message_id, feedback_class, comment))
            return {"status": "success"}
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {"status": "failure", "error": str(e)}

    def create_thread(self, user_id):
        try:
            insert_cmd = """INSERT INTO threads (user_id) values (%s) RETURNING id;"""
            result = self._execute_query(insert_cmd, (user_id,), "one")[0]
            inserted_id = result[0] if result else None
            return {"status": "success", "thread_id": inserted_id}
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {"status": "failure", "error": str(e)}

    def create_thread_whatsapp(self, user_id_whatsapp: int, thread_name: str) -> str:
        """
        Creates a new thread for a given WhatsApp user ID.

        Args:
            user_id_whatsapp (int): The ID of the WhatsApp user.
            thread_name (str): The name of the thread.

        Returns:
            str: The UUID of the newly created thread.
        """
        try:
            insert_cmd = """
            INSERT INTO threads_whatsapp (user_id_whatsapp, name)
            VALUES (%s, %s)
            RETURNING id;
            """
            result = self._execute_query(insert_cmd, (user_id_whatsapp, thread_name), "one")[0]
            return result[0] if result else None
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return None

    def get_all_threads(self, user_id):
        try:
            select_cmd = """SELECT id, name, updated_at FROM threads WHERE user_id = %s;"""
            result = self._execute_query(select_cmd, (user_id,), "all")[0]
            return [{"thread_id": x[0], "thread_name": x[1], "updated_at": x[2]} for x in result] if result else []
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return []

    def set_thread_name(self, thread_id, user_id, thread_name):
        try:
            insert_cmd = (
                "INSERT INTO threads (id, user_id, name) " + "VALUES (%s, %s, %s) ON CONFLICT (id) DO UPDATE SET name = %s;"
            )
            self._execute_query(
                insert_cmd,
                (
                    thread_id,
                    user_id,
                    thread_name[: get_settings().MAX_THREAD_NAME_LENGTH],
                    thread_name[: get_settings().MAX_THREAD_NAME_LENGTH],
                ),
            )
            return {"status": "success"}
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {"status": "failure", "error": str(e)}

    def append_message(
        self, 
        user_id: int, 
        thread_id: int, 
        role: str, 
        content: str | list | dict, 
        tool_name: str = None, 
        tool_details: dict[str, dict] = None,
        ref_list: list = None
    ) -> None:
        """Append a message to the given thread.
        
        This method standardizes the message format before storage to ensure
        consistency when messages are retrieved later. Complex structures
        like lists and dictionaries are properly serialized.
        
        Args:
            user_id: The user ID
            thread_id: The thread ID
            role: The role of the message sender (e.g., "user" or "assistant")
            content: The message content, can be string, list, or dict
            tool_name: Optional name of tool used
            tool_details: Optional details of tool call
            ref_list: Optional list of reference documents
        """
        try:
            # Standardize content format based on message type
            if role == "assistant" and not isinstance(content, list):
                # Convert simple assistant messages to expected format
                content = [{"type": "text", "text": content}]
                
            # Ensure proper serialization of complex structures
            serialized_content = (
                json.dumps(content) 
                if isinstance(content, (dict, list)) 
                else content
            )
            
            # Properly serialize tool details and reference list
            serialized_tool_details = (
                json.dumps(tool_details) 
                if tool_details is not None 
                else None
            )
            
            serialized_ref_list = (
                json.dumps(ref_list) 
                if ref_list is not None 
                else None
            )
            
            # Insert into database
            query = """
                INSERT INTO messages (user_id, thread_id, role, content, tool_name, tool_details, ref_list)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            params = (
                user_id,
                thread_id,
                role,
                serialized_content,
                tool_name,
                serialized_tool_details,
                serialized_ref_list
            )
            
            self._execute_query(query, params, "")
            
        except Exception as e:
            logger.warning(f"Error appending message to database: {e}")
            raise

    def append_message_whatsapp(
        self,
        user_id: int,
        thread_id: int,
        message: dict[str, str | dict[str, dict]],
    ) -> None:
        """Append a message to the given whatsapp thread."""
        try:
            query = """
                INSERT INTO messages_whatsapp (user_id_whatsapp, thread_id, role, content, tool_name, tool_details, ref_list)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            params = (
                user_id,
                thread_id,
                message["role"],
                message["content"],
                message.get("tool_name"),
                json.dumps(message.get("tool_details")) if message.get("tool_details") else None,
                json.dumps(message.get("ref_list")) if message.get("ref_list") else None
            )
            self._execute_query(query, params, "")
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            raise

    def get_thread(self, thread_id, user_id):
        """Get all messages in a thread.
        This version is designed to be used by humans. In particular,
        tool messages are not included.
        """
        try:
            # We need to check user_id to make sure that the user has access to the thread.
            select_cmd_1 = (
                "SELECT role, content, tool_name, tool_details, ref_list FROM messages "
                + "WHERE thread_id = %s AND user_id = %s ORDER BY timestamp;"
            )
            select_cmd_2 = "SELECT name FROM threads WHERE id = %s AND user_id = %s;"
            params = (thread_id, user_id)

            # Note: we don't add "[0]" here since the first arg. below is a list
            result, thread_name_result = self._execute_query([select_cmd_1, select_cmd_2], [params, params], ["all", "one"])

            if not thread_name_result:
                raise HTTPException(
                    status_code=401,
                    detail="Incorrect user_id or thread_id.",
                )
            thread_name = thread_name_result[0]
            retval = {
                "thread_name": thread_name,
                "messages": [self.convert_message(x) for x in result if x[1] != "tool"],
            }
            return retval
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {}

    def get_thread_llm(self, thread_id, user_id):
        """Retrieve all the messages in a thread. This
        is designed for feeding to an LLM, since it includes tool return values.
        """
        try:
            # We need to check user_id to make sure that the user has access to the thread.
            select_cmd_1 = (
                "SELECT role, content, tool_name, tool_details, ref_list FROM messages "
                + "WHERE thread_id = %s AND user_id = %s ORDER BY timestamp;"
            )
            select_cmd_2 = """SELECT name FROM threads WHERE id = %s AND user_id = %s;"""
            params = (thread_id, user_id)

            result, thread_name_result = self._execute_query([select_cmd_1, select_cmd_2], [params, params], ["all", "one"])

            if not thread_name_result:
                raise HTTPException(
                    status_code=401,
                    detail="Incorrect user_id or thread_id.",
                )

            # Now convert the messages to be in the format that the LLM expects
            thread_name = thread_name_result[0]
            msgs = []
            for db_row in result:
                msgs.extend(self.convert_message_llm(db_row))
                
            # Wrap the messages in a history object bundled with its thread name
            history = {
                "thread_name": thread_name,
                "messages": msgs,
            }

            return history

        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {}

    def get_thread_llm_whatsapp(self, thread_id: str, user_id_whatsapp: int) -> list[dict]:
        """
        Retrieves the message history for a given WhatsApp thread.
        This is designed for feeding to an LLM, since it includes tool return values.

        Args:
            thread_id (str): The UUID of the thread.
            user_id_whatsapp (int): The ID of the WhatsApp user.

        Returns:
            list[dict]: A list of dictionaries representing the message history.
        """
        try:
            select_cmd = """
            SELECT role, content, tool_name, tool_details, ref_list
            FROM messages_whatsapp
            WHERE thread_id = %s AND user_id_whatsapp = %s
            ORDER BY updated_at;
            """
            result = self._execute_query(select_cmd, (thread_id, user_id_whatsapp), "all")[0]
            messages = []
            for msg in result:
                messages.extend(self.convert_message_llm(msg))
            return messages
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return []

    def get_last_message_time_whatsapp(self, user_id_whatsapp: int) -> tuple[Optional[str], Optional[datetime]]:
        """
        Retrieves the thread ID and the last message time for the latest updated thread of a WhatsApp user.

        Args:
            user_id_whatsapp (int): The ID of the WhatsApp user.

        Returns:
            tuple[Optional[str], Optional[datetime]]: A tuple containing the thread ID and the last message time.
                                                    Returns (None, None) if no threads are found.
        """
        try:
            select_cmd = """
            SELECT id, updated_at
            FROM threads_whatsapp
            WHERE user_id_whatsapp = %s
            ORDER BY updated_at DESC
            LIMIT 1;
            """
            result = self._execute_query(select_cmd, (user_id_whatsapp,), "one")[0]
            if result:
                return result[0], result[1]
            return None, None
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return None, None

    def snapshot_thread(self, thread_id, user_id):
        """Snapshot a thread at the current time and make it
        shareable with another user.
        Returns: a uuid representing the thread.
        """
        try:
            # First we retrieve the thread.
            thread = self.get_thread(thread_id, user_id)
            logger.info(f"Thread is {json.dumps(thread)}")
            # Now we create a new thread
            insert_cmd = """INSERT INTO share (content) values (%s) RETURNING id;"""
            thread_as_json = json.dumps(thread)
            result = self._execute_query(insert_cmd, (thread_as_json,), "one")[0]
            logger.info(f"Result is {result}")
            return result[0] if result else None
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {"status": "failure", "error": str(e)}

    def get_snapshot(self, share_uuid):
        """Retrieve a snapshot of a thread."""
        try:
            select_cmd = """SELECT content FROM share WHERE id = %s;"""
            result = self._execute_query(select_cmd, (share_uuid,), "one")[0]
            if result:
                # Deserialize json string
                return json.loads(result[0])
            return {}
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {}

    def delete_thread(self, thread_id, user_id):
        try:
            # We need to ensure that the user_id has access to the thread.
            # We must delete the messages associated with the thread first.
            delete_cmd_1 = """DELETE FROM messages WHERE thread_id = %s and user_id = %s;"""
            delete_cmd_2 = """DELETE FROM threads WHERE id = %s AND user_id = %s;"""
            params = (thread_id, user_id)
            self._execute_query([delete_cmd_1, delete_cmd_2], [params, params])
            return {"status": "success"}
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {"status": "failure", "error": str(e)}

    def delete_access_refresh_tokens_pair(self, refresh_token):
        """Deletes the access and refresh token pair associated with the given refresh token.

        Args:
            refresh_token (str): The refresh token to delete.

        Raises:
            HTTPException:
                - 401 if the refresh token is incorrect or doesn't exist.
                - 500 if there is an internal server error during the deletion process.

        """
        try:
            # Retrieve the associated access_token_id
            select_cmd = """SELECT access_token_id FROM refresh_tokens WHERE token = %s;"""
            result = self._execute_query(select_cmd, (refresh_token,), "one")[0]
            if result is None:
                raise HTTPException(
                    status_code=401,
                    detail="Couldn't find refresh_token in the database.",
                )
            access_token_id = result[0]

            # Delete the access token; the refresh token will auto-delete via its foreign key constraint.
            delete_cmd = """DELETE FROM access_tokens WHERE id = %s;"""
            self._execute_query(delete_cmd, (access_token_id,))
            return {"status": "success"}
        except psycopg2.Error as e:
            logging.critical(f"Error: {e}")
            raise HTTPException(status_code=500, detail="Database error")

    def delete_access_token(self, user_id, token):
        try:
            delete_cmd = """DELETE FROM access_tokens WHERE user_id = %s AND token = %s;"""
            self._execute_query(delete_cmd, (user_id, token))
            return {"status": "success"}
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {"status": "failure", "error": str(e)}

    def delete_user(self, user_id):
        try:
            for db_table in [
                "preferences",
                "feedback",
                "messages",
                "threads",
                "users_whatsapp",
                "refresh_tokens",
                "access_tokens",
                "reset_tokens",
            ]:
                delete_cmd = f"""DELETE FROM {db_table} WHERE user_id = %s;"""
                self._execute_query(delete_cmd, (user_id,))

            delete_cmd = "DELETE FROM users WHERE id = %s;"
            self._execute_query(delete_cmd, (user_id,))

            return {"status": "success"}
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {"status": "failure", "error": str(e)}

    def logout(self, user_id, token):
        try:
            for db_table in ["access_tokens", "refresh_tokens"]:
                delete_cmd = f"""DELETE FROM {db_table} WHERE user_id = %s AND token = %s;"""
                self._execute_query(delete_cmd, (user_id, token))
            return {"status": "success"}
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {"status": "failure", "error": str(e)}

    def set_pref(self, user_id, key, value):
        insert_cmd = (
            "INSERT INTO preferences (user_id, pref_key, pref_value) "
            + "VALUES (%s, %s, %s) ON CONFLICT (user_id, pref_key) DO UPDATE SET pref_value = %s;"
        )
        self._execute_query(insert_cmd, (user_id, key, value, value))
        return {"status": "success"}

    def get_prefs(self, user_id):
        select_cmd = """SELECT pref_key, pref_value FROM preferences WHERE user_id = %s;"""
        result = self._execute_query(select_cmd, (user_id,), "all")[0]
        retval = {}
        for x in result:
            retval[x[0]] = x[1]
        return retval

    def update_password(self, user_id, new_password_hash):
        try:
            update_cmd = """UPDATE users SET password_hash = %s WHERE id = %s;"""
            self._execute_query(update_cmd, (new_password_hash, user_id))
            return {"status": "success"}
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {"status": "failure", "error": str(e)}

    def update_user_whatsapp(self, phone_num: str, db_cols_to_vals: dict) -> dict:
        """
        Updates user information in the users_whatsapp table.

        Args:
            phone_num (str): The phone number of the user to identify the record to update.
            db_cols_to_vals (dict): A dictionary where keys are column names of the users_whatsapp table
                                    and values are the corresponding values to be updated.
                                    Column names can be checked from the users_whatsapp DB table.

        Returns:
            dict: A dictionary with the status of the operation.

        Raises:
            ValueError: If no fields are provided to update.
        """
        try:
            # Construct the SQL UPDATE statement dynamically based on the provided dictionary
            fields = list(db_cols_to_vals.keys())
            if not fields:
                raise ValueError("At least one field must be provided to update.")
            set_clause = ", ".join([f"{key} = %s" for key in fields])
            update_cmd = f"UPDATE users_whatsapp SET {set_clause} WHERE phone_num = %s;"

            # Execute the query with the values and the original phone_num
            self._execute_query(update_cmd, (*db_cols_to_vals.values(), phone_num))

            return {"status": "success"}
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {"status": "failure", "error": str(e)}

    def convert_message(self, msg: Iterable[str]) -> dict:
        """Convert a message from database format to API format."""
        role, content, _, _, _ = msg  # Ignore tool_name, tool_details, ref_list
        
        return {"role": role, "content": content}

    def convert_message_llm(self, msg: Iterable[str]) -> list[dict]:
        """Convert a message from database format to LLM format.
        
        This method ensures that the database-stored messages are reconstructed
        into the proper format expected by the LLM interface, preserving all
        necessary structure and relationships between content, tool data, and references.
        """
        role, content, tool_name, tool_details, ref_list = msg
        
        # Parse JSON content if needed
        if isinstance(content, str) and (content.startswith('[') or content.startswith('{')):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                # Keep as string if not valid JSON
                pass
                
        # Handle tool result messages (typically user messages with tool response)
        if tool_name and role == "user":
            # Parse the reference list if it exists
            ref_list_data = json.loads(ref_list) if ref_list else []
            
            # Parse tool details
            tool_use_id = None
            if tool_details:
                try:
                    tool_details_dict = json.loads(tool_details)
                    tool_use_id = tool_details_dict.get("id")
                except json.JSONDecodeError:
                    pass
            
            # Create a properly structured tool result message
            result_content = []
            
            # Add the tool result block
            if isinstance(content, list) and any(block.get("type") == "tool_result" for block in content):
                # Content already has tool_result structure
                result_content = content
            else:
                # Need to create tool_result structure
                result_content = [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": content
                    }
                ]
            
            # Add reference list data
            if ref_list_data:
                result_content.extend(ref_list_data)
                
            return [{
                "role": role,
                "content": result_content
            }]
            
        # Handle assistant messages with tool use
        elif role == "assistant" and tool_name:
            # Create a properly structured assistant message with tool use
            result = []
            
            # First add the regular content message
            if content:
                if isinstance(content, list):
                    result.append({
                        "role": role,
                        "content": content
                    })
                else:
                    result.append({
                        "role": role,
                        "content": [
                            {
                                "type": "text",
                                "text": content
                            }
                        ]
                    })
            
            # Parse tool details
            if tool_details:
                try:
                    tool_details_dict = json.loads(tool_details)
                    tool_id = tool_details_dict.get("id")
                    tool_input = tool_details_dict.get("input")
                    
                    # If we have a message already, append the tool_use to its content
                    if result:
                        if isinstance(result[0]["content"], list):
                            result[0]["content"].append({
                                "type": "tool_use",
                                "id": tool_id,
                                "name": tool_name,
                                "input": tool_input
                            })
                    # Otherwise create a new message
                    else:
                        result.append({
                            "role": role,
                            "content": [
                                {
                                    "type": "tool_use",
                                    "id": tool_id,
                                    "name": tool_name,
                                    "input": tool_input
                                }
                            ]
                        })
                except json.JSONDecodeError:
                    pass
                    
            return result
            
        # Handle regular messages (no tool use)
        else:
            # For text messages from assistant, ensure they have the proper structure
            if role == "assistant":
                if isinstance(content, list):
                    # Already in the right format
                    return [{"role": role, "content": content}]
                else:
                    # Convert to the expected format with type: text
                    return [{
                        "role": role,
                        "content": [
                            {
                                "type": "text",
                                "text": content
                            }
                        ]
                    }]
            # For user messages, keep the format simple unless already complex
            else:
                return [{"role": role, "content": content}]

    def store_quran_answer(
        self,
        surah: int,
        ayah: int,
        question: str,
        ansari_answer: str,
    ):
        insert_cmd = """
        INSERT INTO quran_answers (surah, ayah, question, ansari_answer, review_result, final_answer)
        VALUES (%s, %s, %s, %s, 'pending', NULL)
        """
        self._execute_query(insert_cmd, (surah, ayah, question, ansari_answer))

    def get_quran_answer(
        self,
        surah: int,
        ayah: int,
        question: str,
    ) -> str | None:
        """Retrieve the stored answer for a given surah, ayah, and question.

        Args:
            surah (int): The surah number.
            ayah (int): The ayah number.
            question (str): The question asked.

        Returns:
            str: The stored answer, or None if not found.

        """
        try:
            select_cmd = """
            SELECT ansari_answer
            FROM quran_answers
            WHERE surah = %s AND ayah = %s AND question = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1;
            """
            result = self._execute_query(select_cmd, (surah, ayah, question), "one")[0]
            if result:
                return result[0]
            return None
        except Exception as e:
            logger.error(f"Error retrieving Quran answer: {e!s}")
            return None
