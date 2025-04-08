from datetime import datetime, timezone
from bson import CodecOptions
import pymongo

from ansari.ansari_logger import get_logger
from ansari.config import get_settings

logger = get_logger(__name__)


def update_database():
    try:
        settings = get_settings()
        db_url = settings.MONGO_URL
        db_name = settings.MONGO_DB_NAME
        bson_codec_options = CodecOptions(tz_aware = True)
        mongo_connection = pymongo.MongoClient(db_url)
        mongo_db = mongo_connection[db_name]

        threads_collection = mongo_db.get_collection("threads", codec_options=bson_codec_options)

        impacted_threads = threads_collection.find({"messages.content":
                                                          {"$elemMatch": {"text": ""}}}).sort("updated_at", -1)
        for impacted_thread in impacted_threads:
            logger.info(f"""Empty content message found: {str(impacted_thread["_id"])},
                        last updated: {impacted_thread["updated_at"]}""")

            for message in impacted_thread["messages"]:
                if not isinstance(message["content"], list):
                    continue

                for content in message["content"]:
                    if "text" in content and content["text"] == "":
                        content["text"] = "I'm processing your request."

            update_result = threads_collection.update_one(
                {"_id": impacted_thread["_id"]},
                {"$set": {
                    "messages": impacted_thread["messages"],
                    "updated_at": datetime.now(timezone.utc),
                    "empty_content_block": True
                }}
            )
            logger.info(f"Update result: {update_result.matched_count} matched, {update_result.modified_count} modified.")


    except (Exception) as error:
        logger.error(f"Error: {error}")
    finally:
        if mongo_connection is not None:
            mongo_connection.close()


if __name__ == "__main__":
    update_database()
