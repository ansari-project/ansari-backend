import json
import logging
from bson import ObjectId
from pymongo import MongoClient

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Iterable, Optional
from uuid import UUID

import bcrypt
import jwt
import psycopg2
import psycopg2.pool
from fastapi import HTTPException, Request
from jwt import ExpiredSignatureError, InvalidTokenError

from ansari.ansari_logger import get_logger
from ansari.config import Settings, get_settings

logger = get_logger("DEBUG")


class SourceType(str, Enum):
    ANDROID = "android"
    IOS = "ios"
    WEB = "web"
    WHATSAPP = "whatsapp"


class MessageLogger:
    """A simplified interface to AnsariDB so that we can log messages
    without having to share details about the user_id and the thread_id
    """

    def __init__(self, db: "AnsariDB", source: SourceType, user_id: ObjectId, thread_id: ObjectId) -> None:
        self.db = db
        self.source = source
        self.user_id = user_id
        self.thread_id = thread_id

        logger.debug(f"DB is {db}")

    def log(
        self,
        role: str,
        content: str | list | dict,
        tool_name: str = None,
        tool_details: dict[str, dict] = None,
        ref_list: list = None,
    ) -> None:
        self.db.append_message(self.source, self.user_id, self.thread_id, role, content, tool_name, tool_details, ref_list)


class AnsariDB:
    """Handles all database interactions."""

    def __init__(self, settings: Settings) -> None:
        self.db_url = settings.MONGO_URL
        self.db_name = settings.MONGO_DB_NAME
        self.token_secret_key = settings.SECRET_KEY.get_secret_value()
        self.ALGORITHM = settings.ALGORITHM
        self.ENCODING = settings.ENCODING
        # MongoClient is thread-safe with connection pooling built-in
        self.mongo_connection = MongoClient(self.db_url)
        self.mongo_db = self.mongo_connection[self.db_name]
        if settings.DEV_MODE:
            logger.debug(f"DB URL is {self.db_url}")

    def close(self):
        self.mongo_connection.close()

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

            if isinstance(payload["user_id"], int) or isinstance(payload["user_id"], UUID):
                raise ValueError("Invalid identifier")
            payload["user_id"] = ObjectId(payload["user_id"])

            return payload
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid token identifier")
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

    def _validate_token_in_db(self, user_id: ObjectId, token: str, collection_name: str) -> bool:
        try:
            result = self.mongo_db[collection_name].find_one({"user_id": user_id, "token": token})
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

        collection_map = {
            "access": "access_tokens",
            "refresh": "refresh_tokens",
        }
        collection_name = collection_map[token_type]

        if not self._validate_token_in_db(payload["user_id"], token, collection_name):
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

    def register(
        self,
        source: SourceType,
        email=None,
        first_name=None,
        last_name=None,
        password_hash=None,
        phone_num=None,
        preferred_language=None,
    ):
        """
        Register a new user in the database.
        This method creates a new user record in the users collection with the provided information.
        All parameters are optional except for the source.
        Args:
            email (str, optional): User's email address. Will be stored in lowercase if provided.
            first_name (str, optional): User's first name.
            last_name (str, optional): User's last name.
            password_hash (str, optional): Hashed version of user's password.
            phone_num (str, optional): User's phone number.
            preferred_language (str, optional): User's preferred language.
            source (SourceType): Source of user registration. Required.
        Returns:
            dict: A dictionary containing the registration status.
                - If successful: {"status": "success"}
                - If failed: {"status": "failure", "error": <error_message>}
        Raises:
            Exception: Any database or execution errors will be caught and returned as failure status.
        """
        try:
            new_user = {
                "email": email.strip().lower() if isinstance(email, str) else email,
                "first_name": first_name,
                "last_name": last_name,
                "password_hash": password_hash,
                "phone_num": phone_num,
                "preferred_language": preferred_language,
                "source": source,
            }

            self.mongo_db["users"].insert_one(new_user)

            return {"status": "success"}
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {"status": "failure", "error": str(e)}

    def account_exists(self, email=None, phone_num=None):
        """
        Check if a user account exists either by email or phone number.

        Args:
            email (str, optional): User's email address to check.
            phone_num (str, optional): User's phone number to check.

        Returns:
            bool: True if the account exists, False otherwise.

        Raises:
            ValueError: If neither email nor phone_num is provided.
        """
        try:
            if not (email or phone_num):
                raise ValueError("Either email or phone_num must be provided")

            col_name = "email" if email else "phone_num"
            param = email.strip().lower() if email else phone_num
            result = self.mongo_db["users"].find_one({col_name: param})
            return result is not None
        except Exception as e:
            logger.debuge(f"Warning (possible error): {e}")
            return False

    def save_access_token(self, user_id, token):
        try:
            result = self.mongo_db["access_tokens"].insert_one({"user_id": user_id, "token": token})
            logger.info(f"Result is {result}")
            return {
                "status": "success",
                "token": token,
                "token_db_id": result.inserted_id,
            }
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {"status": "failure", "error": str(e)}

    def save_refresh_token(self, user_id, token, access_token_id):
        try:
            self.mongo_db["refresh_tokens"].insert_one({"user_id": user_id, "token": token, "access_token_id": access_token_id})
            return {"status": "success", "token": token}
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {"status": "failure", "error": str(e)}

    def save_reset_token(self, user_id, token):
        try:
            self.mongo_db["reset_tokens"].insert_one({"user_id": user_id, "token": token})
            return {"status": "success", "token": token}
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {"status": "failure", "error": str(e)}

    def retrieve_user_info(self, source: SourceType, email=None, phone_num=None, db_cols=None):
        """
        Retrieves user information from the users collection by email or phone number.

        Args:
            source (SourceType): Source type (WEB, WHATSAPP, etc).
            email (str, optional): The user's email address.
            phone_num (str, optional): The user's phone number.
            db_cols (Union[list, str], optional): Specific column(s) to retrieve.

        Returns:
            Optional[Tuple]: A tuple containing the requested fields or None values if no user is found.

        Raises:
            ValueError: If required identifier is missing for the specified source.
        """
        try:
            if source == SourceType.WHATSAPP:
                result = self.mongo_db["users"].find_one({"phone_num": phone_num, "source": source.value})
                if result is None:
                    return None
                return result["_id"]
            else:
                result = self.mongo_db["users"].find_one({"email": email.strip().lower()})
                if result is None:
                    return None, None, None, None
                return result["_id"], result["password_hash"], result["first_name"], result["last_name"]


        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {"status": "failure", "error": str(e)}

    def retrieve_user_info_by_user_id(self, id):
        try:
            result = self.mongo_db["users"].find_one({"_id": ObjectId(id)})

            if result:
                return result["_id"], result["email"], result["first_name"], result["last_name"]

            return None, None, None, None
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return None, None, None, None

    def add_feedback(self, user_id, thread_id, message_id, feedback_class, comment):
        try:
            self.mongo_db["feedback"].insert_one(
                {
                    "user_id": user_id,
                    "thread_id": thread_id,
                    "message_id": message_id,
                    "class": feedback_class,
                    "comment": comment,
                }
            )
            return {"status": "success"}
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {"status": "failure", "error": str(e)}

    def create_thread(self, source: SourceType, user_id: ObjectId, thread_name=None) -> dict:
        """
        Creates a new thread with appropriate source.

        Args:
            user_id (ObjectId): The user's ID.
            thread_name (str, optional): The name of the thread.

        Returns:
            dict: Dictionary with thread_id and status
        """
        try:
            # Use the unified threads table with the initial_source field
            name = thread_name if thread_name else None
            result = self.mongo_db["threads"].insert_one({"user_id": user_id, "name": name, "initial_source": source})
            return {"status": "success", "thread_id": result.inserted_id}

        except Exception as e:
            logger.warning(f"Thread creation error: {e}")
            return {"status": "failure", "error": str(e)}

    def get_all_threads(self, user_id):
        try:
            result = self.mongo_db["threads"].find({"user_id": user_id})
            return [{"thread_id": x["_id"], "thread_name": x["name"], "updated_at": x["updated_at"]} for x in result] if result else []
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return []

    def set_thread_name(self, thread_id, user_id, thread_name):
        try:
            truncated_thread_name = thread_name[: get_settings().MAX_THREAD_NAME_LENGTH]
            self.mongo_db["threads"].update_one({"_id": thread_id}, {"$set": {"name": truncated_thread_name}})

            return {"status": "success"}
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {"status": "failure", "error": str(e)}

    def append_message(
        self,
        source: SourceType,
        user_id: ObjectId,
        thread_id: ObjectId,
        role: str,
        content: str | list | dict,
        tool_name: str = None,
        tool_details: dict[str, dict] = None,
        ref_list: list = None,
    ) -> None:
        """Append a message to the given thread.

        This method standardizes the message format before storage to ensure
        consistency when messages are retrieved later. Complex structures
        like lists and dictionaries are properly serialized.

        Args:
            user_id: The user ID (ObjectId)
            thread_id: The thread ID (ObjectId)
            role: The role of the message sender (e.g., "user" or "assistant")
            content: The message content, can be string (if non-claude Ansari is used), list, or dict
            tool_name: Optional name of tool used
            tool_details: Optional details of tool call
            ref_list: Optional list of reference documents
        """
        try:
            if source != SourceType.WHATSAPP:
                # Standardize content format based on message type
                if role == "assistant" and not isinstance(content, list):
                    # Convert simple assistant messages to expected format
                    content = [{"type": "text", "text": content}]
                content = json.dumps(content) if isinstance(content, (dict, list)) else content

            params = {
                "user_id": user_id,
                "thread_id": thread_id,
                "role": role,
                "content": content,
                "tool_name": tool_name,
                "tool_details": json.dumps(tool_details) if tool_details is not None else None,
                "ref_list": json.dumps(ref_list) if ref_list is not None else None,
                "source": source.value if source else None,
            }

            self.mongo_db["messages"].insert_one(params)

        except Exception as e:
            logger.warning(f"Error appending message to database: {e}")
            raise

    def get_thread(self, thread_id, user_id):
        """Get all messages in a thread.
        This version is designed to be used by humans. In particular,
        tool messages are not included.
        """
        try:
            # We need to check user_id to make sure that the user has access to the thread.
            thread = self.mongo_db["threads"].find_one({"_id": thread_id, "user_id": user_id})

            result = self.mongo_db["messages"].find({"thread_id": thread_id, "user_id": user_id}).sort("timestamp", 1)

            if not thread:
                raise HTTPException(
                    status_code=401,
                    detail="Incorrect user_id or thread_id.",
                )

            thread_name = thread["name"]
            retval = {
                "thread_name": thread_name,
                "messages": [self.convert_message(x) for x in result],
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
            thread = self.mongo_db["threads"].find_one({"_id": thread_id, "user_id": user_id})

            result = self.mongo_db["messages"].find({"thread_id": thread_id, "user_id": user_id}).sort("timestamp", 1)

            if not thread:
                raise HTTPException(
                    status_code=401,
                    detail="Incorrect user_id or thread_id.",
                )

            # Now convert the messages to be in the format that the LLM expects
            thread_name = thread["name"]
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

    def get_last_message_time_whatsapp(self, user_id: ObjectId) -> tuple[Optional[ObjectId], Optional[datetime]]:
        """
        Retrieves the thread ID and the last message time for the latest updated thread of a WhatsApp user.

        Args:
            user_id (ObjectId): The ID of the WhatsApp user.

        Returns:
            tuple[Optional[ObjectId], Optional[datetime]]: A tuple containing the thread ID and the last message time.
                                                    Returns (None, None) if no threads are found.
        """
        try:
            result = self.mongo_db["threads"].find_one({"user_id": user_id}, sort=[('updated_at', -1)])
            if result:
                return result["_id"], result["updated_at"]
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
            result = self.mongo_db["share"].insert_one({"content": thread})
            logger.info(f"Result is {result}")
            return result.inserted_id if result else None
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {"status": "failure", "error": str(e)}

    def get_snapshot(self, share_uuid):
        """Retrieve a snapshot of a thread."""
        try:
            result = self.mongo_db["share"].find_one({"_id": share_uuid})
            if result:
                # Deserialize json string
                return json.loads(result)
            return {}
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {}

    def delete_thread(self, thread_id, user_id):
        try:
            # We need to ensure that the user_id has access to the thread.
            # We must delete the messages associated with the thread first.
            self.mongo_db["messages"].delete_many({"thread_id": thread_id, "user_id": user_id})
            self.mongo_db["threads"].delete_one({"_id": thread_id})
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
            result = self.mongo_db["refresh_tokens"].find_one({"token": refresh_token})
            if result is None:
                raise HTTPException(
                    status_code=401,
                    detail="Couldn't find refresh_token in the database.",
                )

            self.mongo_db["refresh_tokens"].delete_one({"_id": result["_id"]})
            self.mongo_db["access_tokens"].delete_one({"_id": result["access_token_id"]})
            return {"status": "success"}
        except psycopg2.Error as e:
            logging.critical(f"Error: {e}")
            raise HTTPException(status_code=500, detail="Database error")

    def delete_access_token(self, user_id, token):
        try:
            self.mongo_db["access_tokens"].delete_one({"user_id": user_id, "token": token})
            return {"status": "success"}
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {"status": "failure", "error": str(e)}

    def delete_user(self, user_id):
        try:
            for collection_name in [
                "preferences",
                "feedback",
                "messages",
                "threads",
                "refresh_tokens",
                "access_tokens",
                "reset_tokens",
            ]:
                self.mongo_db[collection_name].delete_many({"user_id": user_id})

            self.mongo_db["users"].delete_one({"_id": user_id})

            return {"status": "success"}
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {"status": "failure", "error": str(e)}

    def logout(self, user_id, token):
        try:
            for collection_name in ["refresh_tokens", "access_tokens"]:
                self.mongo_db[collection_name].delete_one({"user_id": user_id, "token": token})
            return {"status": "success"}
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {"status": "failure", "error": str(e)}

    def set_pref(self, user_id, key, value):
        self.mongo_db["preferences"].update_one({"user_id": user_id, "pref_key": key}, {"$set": {"pref_value": value}, "upsert": True})
        return {"status": "success"}

    def get_prefs(self, user_id):
        result = self.mongo_db["preferences"].find({"user_id": user_id})
        return result

    def update_password(self, user_id, new_password_hash):
        try:
            self.mongo_db["users"].update_one({"_id": user_id}, {"$set": {"password_hash": new_password_hash}})
            return {"status": "success"}
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {"status": "failure", "error": str(e)}

    def update_user_by_phone_num(self, phone_num: str, db_cols_to_vals: dict) -> dict:
        """
        Updates a user's information in the users collection.

        Args:
            phone_num (str): The phone number of the user to identify the record to update.
            db_cols_to_vals (dict): A dictionary where keys are column names of the users collection
                                    and values are the corresponding values to be updated.

        Returns:
            dict: A dictionary with the status of the operation.

        Raises:
            ValueError: If no fields are provided to update.
        """
        try:
            self.mongo_db["users"].update_one({"phone_num": phone_num}, {"$set": db_cols_to_vals})

            return {"status": "success"}
        except Exception as e:
            logger.warning(f"Warning (possible error): {e}")
            return {"status": "failure", "error": str(e)}

    def convert_message(self, msg: Iterable[str]) -> dict:
        """Convert a message from database format to a displayable format.
        This means stripping things like tool usage."""
        # Check if message has ID (from database) or not (from in-memory)
        if len(msg) == 6:
            # Message from database query with ID
            msg_id, role, content, _, _, _ = msg  # Unpack id, role, content; ignore tool_name, tool_details, ref_list
        else:
            # Message from in-memory (no ID yet)
            role, content, _, _, _ = msg  # Ignore tool_name, tool_details, ref_list
            msg_id = None
        logger.info(f"Content is {content}")

        # If content is a string that looks like JSON, try to parse it
        if isinstance(content, str) and (content.startswith("[") or content.startswith("{")):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                # Keep as string if not valid JSON
                pass

        # If content is a list, find the first element with type "text"
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    content = item.get("text", "")
                    break

        return {"id": msg_id, "role": role, "content": content}

    def convert_message_llm(self, msg: Iterable[str]) -> list[dict]:
        """Convert a message from database format to LLM format.

        This method ensures that the database-stored messages are reconstructed
        into the proper format expected by the LLM interface, preserving all
        necessary structure and relationships between content, tool data, and references.
        """
        # Check if message has ID (from database) or not (from in-memory)
        if len(msg) == 6:
            # Message from database query with ID
            msg_id, role, content, tool_name, tool_details, ref_list = msg
        else:
            # Message from in-memory (no ID yet)
            role, content, tool_name, tool_details, ref_list = msg
            msg_id = None

        # Parse JSON content if needed
        if isinstance(content, str) and (content.startswith("[") or content.startswith("{")):
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
                result_content = [{"type": "tool_result", "tool_use_id": tool_use_id, "content": content}]

            # Add reference list data
            if ref_list_data:
                result_content.extend(ref_list_data)

            return [{"id": msg_id, "role": role, "content": result_content}]

        # Handle all assistant messages (with or without tool use)
        elif role == "assistant":
            # For assistant messages, always use block format
            content_blocks = []

            # Add text block
            if isinstance(content, str):
                content_blocks.append({"type": "text", "text": content})
            elif isinstance(content, list) and all(isinstance(block, dict) and "type" in block for block in content):
                # Content is already in block format
                content_blocks = content
            else:
                # Convert to text block
                content_blocks.append({"type": "text", "text": str(content)})

            # If there's tool info, add tool use block
            if tool_name and tool_details:
                try:
                    tool_details_dict = json.loads(tool_details)
                    tool_id = tool_details_dict.get("id")
                    tool_input = tool_details_dict.get("args")
                    # Add tool use block only if we have valid information
                    if tool_id and tool_name:
                        content_blocks.append({"type": "tool_use", "id": tool_id, "name": tool_name, "input": tool_input})
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse tool details JSON: {tool_details}")

            return [{"id": msg_id, "role": role, "content": content_blocks}]

        # Handle regular user messages without tool use
        else:
            # For simple user messages, use simple format
            if isinstance(content, str):
                # Simple text content
                return [{"id": msg_id, "role": role, "content": content}]
            else:
                # Content is already structured (list or dict)
                return [{"id": msg_id, "role": role, "content": content}]

    def store_quran_answer(
        self,
        surah: int,
        ayah: int,
        question: str,
        ansari_answer: str,
    ):
        self.mongo_db["quran_answers"].insert_one({"surah": surah, "ayah": ayah, "question": question, "ansari_answer": ansari_answer})

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
            result = self.mongo_db["quran_answers"].find_one({"surah": surah, "ayah": ayah, "question": question}).order_by(
                [("created_at", -1), ("_id", -1)])
            if result:
                return result["ansari_answer"]
            return None
        except Exception as e:
            logger.error(f"Error retrieving Quran answer: {e!s}")
            return None

    def get_user_id_for_thread(self, thread_id: ObjectId) -> Optional[ObjectId]:
        """
        Retrieves the user ID associated with a given thread ID.

        Args:
            thread_id (ObjectId): The ID of the thread.

        Returns:
            Optional[ObjectId]: The user ID associated with the thread, or None if the thread doesn't exist.
        """
        try:
            result = self.mongo_db["threads"].find_one({"_id": thread_id})
            return result["user_id"] if result else None
        except Exception as e:
            logger.warning(f"Error retrieving user ID for thread: {e}")
            return None
