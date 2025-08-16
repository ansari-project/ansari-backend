from bson import ObjectId
import pymongo
from bson import json_util

from ansari.ansari_db_sql import AnsariSQLDB
from ansari.ansari_logger import get_logger
from ansari.config import get_settings

logger = get_logger(__name__)


def migrate_database():
    try:
        settings = get_settings()
        sql_db = AnsariSQLDB(settings)
        db_url = settings.MONGO_URL
        db_name = settings.MONGO_DB_NAME
        mongo_connection = pymongo.MongoClient(db_url)
        mongo_db = mongo_connection[db_name]

        users_collection = mongo_db["users"]
        threads_collection = mongo_db["threads"]
        messages_collection = mongo_db["messages"]
        feedback_collection = mongo_db["feedback"]

        # Step 1: Process feedback
        logger.info("Step 1: Process feedback documents")
        logger.info(f"Estimated document count: {feedback_collection.estimated_document_count()}")

        while True:
            feedbacks = list(feedback_collection.find({"migrated": {"$exists": False}}).limit(1000))
            if len(feedbacks) == 0:
                break

            feedback_operations = []
            message_operations = []
            for i, feedback in enumerate(feedbacks, 1):
                logger.info(f"{i} Processing Feedback: {str(feedback['_id'])}")
                message_id = feedback.get("original_message_id")
                if message_id:
                    message = messages_collection.find_one({"original_id": message_id})
                    if message:
                        feedback_operations.append(pymongo.UpdateOne(
                            {"_id": feedback["_id"]},
                            {"$set": {"migrated": True}}
                        ))

                        message_operations.append(pymongo.UpdateOne(
                            {"original_id": message_id},
                            {"$set": {"feedback": {
                                "class": feedback.get("class"),
                                "comment": feedback.get("comment"),
                                "created_at": feedback.get("created_at"),
                                "updated_at": feedback.get("updated_at")
                            }}}
                        ))

            logger.info("Saving changes...")
            feedback_results = feedback_collection.bulk_write(feedback_operations)
            logger.info(f"Feedback results: {feedback_results}")

            message_results = messages_collection.bulk_write(message_operations)
            logger.info(f"Message results: {message_results}")

        logger.info("Step 1: Process feedback documents - Done\n\n")

        # Step 2: Process messages
        logger.info("Step 2: Process message documents")
        logger.info(f"Estimated document count: {messages_collection.estimated_document_count()}")
        while True:
            messages = list(messages_collection.find({"migrated": {"$exists": False}}).limit(1000))
            if len(messages) == 0:
                break

            operations = []
            for i, message in enumerate(messages, 1):
                logger.info(f"{i} Processing Message: {str(message['_id'])}")
                query = {"_id": message["_id"]}

                original_message = (
                    message.get("original_id"),
                    message.get("role"),
                    message.get("content"),
                    message.get("tool_name"),
                    message.get("tool_details"),
                    message.get("ref_list"),
                )
                converted_message = sql_db.convert_message_llm(original_message)[0]

                updated_message = {
                    "role": converted_message["role"],
                    "content": converted_message["content"],
                    "id": str(ObjectId()),
                    "source": message["source"],
                    "created_at": message["created_at"],
                    "original_id": message["original_id"],
                    "original_thread_id": message["original_thread_id"],
                    "original_message": json_util.dumps(message),
                    "migrated": True,
                }

                operations.append(pymongo.ReplaceOne(query, updated_message))

            logger.info("Saving changes...")
            results = messages_collection.bulk_write(operations)
            logger.info(f"Message results: {results}")

        logger.info("Step 2: Process message documents - Done\n\n")

        # Step 3: Embed messages in threads
        logger.info("Step 3: Process thread documents")
        logger.info(f"Estimated document count: {threads_collection.estimated_document_count()}")

        while True:
            threads = list(threads_collection.find({"migrated": {"$exists": False}}).limit(1000))
            if len(threads) == 0:
                break

            operations = []
            for i, thread in enumerate(threads, 1):
                logger.info(f"{i} Migrating: {str(thread['_id'])}")
                query = {"_id": thread["_id"]}

                if thread.get("original_user_id") is None:
                    logger.warning(f"Thread {str(thread['_id'])} does not have an original user ID.")
                    continue

                user = users_collection.find_one({"original_id": thread["original_user_id"]})
                messages = list(messages_collection.find({"original_thread_id": thread["original_id"]})
                                .sort("created_at", pymongo.ASCENDING))

                thread_messages = []
                for message in messages:
                    if message.get("role") == "tool" or message.get("role") == "function":
                        continue

                    content = message.get("content")
                    if isinstance(content, list) and any(block.get("type") == "tool_use" for block in content):
                        continue

                    if isinstance(content, list) and any(block.get("type") == "tool_result" for block in content):
                        continue

                    del message["_id"]
                    del message["original_id"]
                    del message["original_thread_id"]
                    del message["migrated"]

                    thread_messages.append(message)

                set_values = {
                    "migrated": True,
                    "user_id": user["_id"],
                    "messages": thread_messages
                }

                operations.append(pymongo.UpdateOne(query, {"$set": set_values}))

            logger.info("Saving changes...")
            results = threads_collection.bulk_write(operations)
            logger.info(f"Thread results: {results}")

        logger.info("Step 3: Process thread documents - Done\n\n")

    except (Exception) as error:
        logger.error(f"Error: {error}")
    finally:
        if mongo_connection is not None:
            mongo_connection.close()


migrate_database()
