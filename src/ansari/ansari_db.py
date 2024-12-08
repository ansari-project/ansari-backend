import inspect
import json
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional, Union

import bcrypt
import jwt
import psycopg2
import psycopg2.pool
from fastapi import HTTPException, Request
from jwt import ExpiredSignatureError, InvalidTokenError

from ansari.ansari_logger import get_logger
from ansari.config import Settings, get_settings

logger = get_logger()


class MessageLogger:
    """A simplified interface to AnsariDB so that we can log messages
    without having to share details about the user_id and the thread_id
    """

    def __init__(self, db, user_id: int, thread_id: int, trace_id: int) -> None:
        self.user_id = user_id
        self.thread_id = thread_id
        self.trace_id = trace_id
        logger.debug(f"DB is {db}")
        self.db = db

    def log(self, role, content, tool_name=None):
        self.db.append_message(self.user_id, self.thread_id, role, content, tool_name)


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
            "user_id": user_id,
            "type": token_type,
            "exp": datetime.now(timezone.utc) + timedelta(hours=expiry_hours),
        }
        return jwt.encode(payload, self.token_secret_key, algorithm=self.ALGORITHM)

    def decode_token(self, token: str) -> dict[str, str]:
        try:
            return jwt.decode(token, self.token_secret_key, algorithms=[self.ALGORITHM])
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
    ) -> Union[tuple, Optional[list[tuple]], list[Optional[list[tuple]]]]:
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
            Union[Optional[List], List[Optional[List]]]:
                - If a single query is executed:
                    - Returns a single result if which_fetch is "one"
                    - Returns a single list of rows if which_fetch is "all".
                    - Else, returns None.
                - If multiple queries are executed:
                    - Returns a list of results, where each result is:
                        - A single result if which_fetch is "one".
                        - A list of rows if which_fetch is "all".
                        - Else, returns None.

            Note: the "single result" here could be a tuple if more than 1 column is selected in the query.

        Raises:
            ValueError: If an invalid fetch type is provided.
        """
        # If query is a single string, we assume that params and which_fetch are also non-list values
        if isinstance(query, str):
            requested_single_query = True
            query = [query]
            params = [params]
            which_fetch = [which_fetch]
        # else, we assume that params and which_fetch are lists of the same length,
        # but will still check which_fetch
        else:
            requested_single_query = False
            if not isinstance(which_fetch, list):
                which_fetch = [""] * len(query)

        caller_function_name = inspect.stack()[1].function
        logger.debug(f"Function {caller_function_name}() \nis running queries: \n{query} \nwith params: \n{params}")

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

                    if not q.lower().startswith("select") and commit_after.lower() == "each":
                        conn.commit()

                    results.append(result)

                if commit_after.lower() == "all":
                    conn.commit()

        # If only 1 query was to be executed, return it (or None if it was a non-fetch query)
        if requested_single_query:
            return results[0]
        # Else, multiple queries were executed, so return all results
        return results

    def _validate_token_in_db(self, user_id: str, token: str, table: str) -> bool:
        try:
            select_cmd = f"SELECT user_id FROM {table} WHERE user_id = %s AND token = %s;"
            result = self._execute_query(select_cmd, (user_id, token), "one")
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
            insert_cmd = """INSERT INTO users (email, password_hash, first_name, last_name) values (%s, %s, %s, %s);"""
            self._execute_query(insert_cmd, (email, password_hash, first_name, last_name))
            return {"status": "success"}
        except Exception as e:
            logger.warning(f"Error is {e}")
            return {"status": "failure", "error": str(e)}

    def account_exists(self, email: str, phone_num: str = ""):
        try:
            select_cmd = """SELECT id FROM users WHERE email = %s;"""
            result = self._execute_query(select_cmd, (email,), "one")
            return result is not None
        except Exception as e:
            logger.warning(f"Error is {e}")
            return False

    def save_access_token(self, user_id, token):
        try:
            insert_cmd = "INSERT INTO access_tokens (user_id, token) VALUES (%s, %s) RETURNING id;"
            result = self._execute_query(insert_cmd, (user_id, token), "one")
            inserted_id = result[0] if result else None
            return {
                "status": "success",
                "token": token,
                "token_db_id": inserted_id,
            }
        except Exception as e:
            logger.warning(f"Error is {e}")
            return {"status": "failure", "error": str(e)}

    def save_refresh_token(self, user_id, token, access_token_id):
        try:
            insert_cmd = "INSERT INTO refresh_tokens (user_id, token, access_token_id) VALUES (%s, %s, %s);"
            self._execute_query(insert_cmd, (user_id, token, access_token_id))
            return {"status": "success", "token": token}
        except Exception as e:
            logger.warning(f"Error is {e}")
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
            logger.warning(f"Error is {e}")
            return {"status": "failure", "error": str(e)}

    def retrieve_user_info(self, email):
        try:
            select_cmd = "SELECT id, password_hash, first_name, last_name FROM users WHERE email = %s;"
            result = self._execute_query(select_cmd, (email,), "one")
            if result:
                user_id, existing_hash, first_name, last_name = result
                return user_id, existing_hash, first_name, last_name
            return None, None, None, None
        except Exception as e:
            logger.warning(f"Error is {e}")
            return None, None, None, None

    def add_feedback(self, user_id, thread_id, message_id, feedback_class, comment):
        try:
            insert_cmd = (
                "INSERT INTO feedback (user_id, thread_id, message_id, class, comment)" + " VALUES (%s, %s, %s, %s, %s);"
            )
            self._execute_query(insert_cmd, (user_id, thread_id, message_id, feedback_class, comment))
            return {"status": "success"}
        except Exception as e:
            logger.warning(f"Error is {e}")
            return {"status": "failure", "error": str(e)}

    def create_thread(self, user_id):
        try:
            insert_cmd = """INSERT INTO threads (user_id) values (%s) RETURNING id;"""
            result = self._execute_query(insert_cmd, (user_id,), "one")
            inserted_id = result[0] if result else None
            return {"status": "success", "thread_id": inserted_id}
        except Exception as e:
            logger.warning(f"Error is {e}")
            return {"status": "failure", "error": str(e)}

    def get_all_threads(self, user_id):
        try:
            select_cmd = """SELECT id, name, updated_at FROM threads WHERE user_id = %s;"""
            result = self._execute_query(select_cmd, (user_id,), "all")
            return [{"thread_id": x[0], "thread_name": x[1], "updated_at": x[2]} for x in result] if result else []
        except Exception as e:
            logger.warning(f"Error is {e}")
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
            logger.warning(f"Error is {e}")
            return {"status": "failure", "error": str(e)}

    def append_message(self, user_id, thread_id, role, content, tool_name=None):
        try:
            # TODO (odyash): check if "function" can be renamed to
            # "tool" like the rest of the codebase or not
            insert_cmd = (
                "INSERT INTO messages (thread_id, user_id, role, content, function_name) " + "VALUES (%s, %s, %s, %s, %s);"
            )
            params_1 = (thread_id, user_id, role, content, tool_name)

            # Appending a message should update the thread's updated_at field.
            update_cmd = "UPDATE threads SET updated_at = now() WHERE id = %s AND user_id = %s;"
            params_2 = (thread_id, user_id)

            self._execute_query([insert_cmd, update_cmd], [params_1, params_2], commit_after="all")

            return {"status": "success"}
        except Exception as e:
            logger.warning(f"Error is {e}")
            return {"status": "failure", "error": str(e)}

    def get_thread(self, thread_id, user_id):
        """Get all messages in a thread.
        This version is designed to be used by humans. In particular,
        tool messages are not included.
        """
        try:
            select_cmd_1 = (
                "SELECT id, role, content FROM messages " + "WHERE thread_id = %s AND user_id = %s ORDER BY updated_at;"
            )
            select_cmd_2 = "SELECT name FROM threads WHERE id = %s AND user_id = %s;"
            params = (thread_id, user_id)

            result, thread_name_result = self._execute_query([select_cmd_1, select_cmd_2], [params, params], ["all", "one"])

            if not thread_name_result:
                raise HTTPException(
                    status_code=401,
                    detail="Incorrect user_id or thread_id.",
                )
            thread_name = thread_name_result[0]
            # TODO (odyash): check if "function" can be renamed to "tool"
            retval = {
                "thread_name": thread_name,
                "messages": [self.convert_message(x) for x in result if x[1] != "function"],
            }
            return retval
        except Exception as e:
            logger.warning(f"Error is {e}")
            return {}

    def get_thread_llm(self, thread_id, user_id):
        """Retrieve all the messages in a thread. This
        is designed for feeding to an LLM, since it includes tool return values.
        """
        try:
            # We need to check user_id to make sure that the user has access to the thread.
            # TODO (odyash): check if "function" can be renamed to "tool" like the rest of the codebase or not
            select_cmd_1 = (
                "SELECT role, content, function_name FROM messages "
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
            thread_name = thread_name_result[0]
            # Now convert into the standard format
            retval = {
                "thread_name": thread_name,
                "messages": [self.convert_message_llm(x) for x in result],
            }
            return retval
        except Exception as e:
            logger.warning(f"Error is {e}")
            return {}

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
            result = self._execute_query(insert_cmd, (thread_as_json,), "one")
            logger.info(f"Result is {result}")
            return result[0] if result else None
        except Exception as e:
            logger.warning(f"Error is {e}")
            return {"status": "failure", "error": str(e)}

    def get_snapshot(self, share_uuid):
        """Retrieve a snapshot of a thread."""
        try:
            select_cmd = """SELECT content FROM share WHERE id = %s;"""
            result = self._execute_query(select_cmd, (share_uuid,), "one")
            if result:
                # Deserialize json string
                return json.loads(result[0])
            return {}
        except Exception as e:
            logger.warning(f"Error is {e}")
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
            logger.warning(f"Error is {e}")
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
            result = self._execute_query(select_cmd, (refresh_token,), "one")
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
            logger.warning(f"Error is {e}")
            return {"status": "failure", "error": str(e)}

    def logout(self, user_id, token):
        try:
            for db_table in ["access_tokens", "refresh_tokens"]:
                delete_cmd = f"""DELETE FROM {db_table} WHERE user_id = %s AND token = %s;"""
                self._execute_query(delete_cmd, (user_id, token))
            return {"status": "success"}
        except Exception as e:
            logger.warning(f"Error is {e}")
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
        result = self._execute_query(select_cmd, (user_id,), "all")
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
            logger.warning(f"Error is {e}")
            return {"status": "failure", "error": str(e)}

    def convert_message(self, msg):
        return {"id": msg[0], "role": msg[1], "content": msg[2]}

    def convert_message_llm(self, msg):
        if msg[2]:
            return {"role": msg[0], "content": msg[1], "name": msg[2]}
        return {"role": msg[0], "content": msg[1]}

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
            result = self._execute_query(select_cmd, (surah, ayah, question), "one")
            if result:
                return result[0]
            return None
        except Exception as e:
            logger.error(f"Error retrieving Quran answer: {e!s}")
            return None
