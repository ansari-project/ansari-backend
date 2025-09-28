# WhatsApp API Router for ansari-backend
"""FastAPI router containing WhatsApp-specific API endpoints for the ansari-whatsapp microservice."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ansari.ansari_db import SourceType, MessageLogger
from ansari.ansari_logger import get_logger

logger = get_logger(__name__)

# Initialize the router
router = APIRouter()

# Get database connection
from ansari.app.main_api import db, presenter


# Pydantic models for WhatsApp API requests
class WhatsAppUserRegisterRequest(BaseModel):
    phone_num: str
    preferred_language: str


class WhatsAppLocationRequest(BaseModel):
    phone_num: str
    latitude: float
    longitude: float


class WhatsAppThreadRequest(BaseModel):
    phone_num: str
    title: str


class WhatsAppMessageRequest(BaseModel):
    phone_num: str
    thread_id: str
    message: str


@router.post("/api/v2/whatsapp/users/register")
async def register_whatsapp_user(req: WhatsAppUserRegisterRequest):
    """Register a new WhatsApp user with the Ansari backend.

    Args:
        req: WhatsApp user registration request containing phone_num and preferred_language

    Returns:
        dict: Registration result with user details
    """
    try:
        logger.info(f"Registering WhatsApp user with phone: {req.phone_num}")

        result = db.register(
            source=SourceType.WHATSAPP,
            email=None,
            password_hash=None,
            first_name=None,
            last_name=None,
            phone_num=req.phone_num,
            preferred_language=req.preferred_language
        )

        logger.info(f"Successfully registered WhatsApp user: {req.phone_num}")
        return {"status": "success", "user_id": result}

    except Exception as e:
        logger.error(f"Error registering WhatsApp user {req.phone_num}: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Registration failed: {str(e)}")


@router.get("/api/v2/whatsapp/users/exists")
async def check_whatsapp_user_exists(phone_num: str):
    """Check if a WhatsApp user exists in the Ansari backend.

    Args:
        phone_num: User's WhatsApp phone number

    Returns:
        dict: Contains 'exists' boolean indicating if user exists
    """
    try:
        logger.info(f"Checking existence for WhatsApp user: {phone_num}")

        exists = db.account_exists(phone_num=phone_num)

        logger.info(f"WhatsApp user {phone_num} exists: {exists}")
        return {"exists": exists}

    except Exception as e:
        logger.error(f"Error checking WhatsApp user existence {phone_num}: {str(e)}")
        raise HTTPException(status_code=400, detail=f"User existence check failed: {str(e)}")


@router.put("/api/v2/whatsapp/users/location")
async def update_whatsapp_user_location(req: WhatsAppLocationRequest):
    """Update a WhatsApp user's location in the Ansari backend.

    Args:
        req: Location update request containing phone_num, latitude, and longitude

    Returns:
        dict: Update result status
    """
    try:
        logger.info(f"Updating location for WhatsApp user: {req.phone_num}")

        result = db.update_user_by_phone_num(
            phone_num=req.phone_num,
            db_cols_to_vals={
                "latitude": req.latitude,
                "longitude": req.longitude
            }
        )

        logger.info(f"Successfully updated location for WhatsApp user: {req.phone_num}")
        return result

    except Exception as e:
        logger.error(f"Error updating location for WhatsApp user {req.phone_num}: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Location update failed: {str(e)}")


@router.post("/api/v2/whatsapp/threads")
async def create_whatsapp_thread(req: WhatsAppThreadRequest):
    """Create a new thread for a WhatsApp user in the Ansari backend.

    Args:
        req: Thread creation request containing phone_num and title

    Returns:
        dict: Creation result with thread_id
    """
    try:
        logger.info(f"Creating thread for WhatsApp user: {req.phone_num}")

        # Get the user ID for the WhatsApp user
        user_id = db.retrieve_user_info(
            source=SourceType.WHATSAPP,
            phone_num=req.phone_num,
            db_cols=["id"] if hasattr(db, '_execute_query') else None  # SQL vs MongoDB compatibility
        )

        if not user_id:
            raise HTTPException(status_code=404, detail="WhatsApp user not found")

        # Extract user_id from result (handle both SQL tuple and MongoDB string returns)
        if isinstance(user_id, tuple):
            user_id = user_id[0]

        result = db.create_thread(source=SourceType.WHATSAPP, user_id=user_id, thread_name=req.title)
        thread_id = result.get("thread_id") or result.get("_id")

        logger.info(f"Successfully created thread {thread_id} for WhatsApp user: {req.phone_num}")
        return {"thread_id": str(thread_id)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating thread for WhatsApp user {req.phone_num}: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Thread creation failed: {str(e)}")


@router.get("/api/v2/whatsapp/threads/last")
async def get_last_whatsapp_thread(phone_num: str):
    """Get information about the last active thread for a WhatsApp user.

    Args:
        phone_num: User's WhatsApp phone number

    Returns:
        dict: Thread info with thread_id and last_message_time
    """
    try:
        logger.info(f"Getting last thread info for WhatsApp user: {phone_num}")

        # Get the user ID for the WhatsApp user
        user_id = db.retrieve_user_info(
            source=SourceType.WHATSAPP,
            phone_num=phone_num,
            db_cols=["id"] if hasattr(db, '_execute_query') else None
        )

        if not user_id:
            raise HTTPException(status_code=404, detail="WhatsApp user not found")

        # Extract user_id from result
        if isinstance(user_id, tuple):
            user_id = user_id[0]

        thread_id, last_message_time = db.get_last_message_time_whatsapp(user_id)

        result = {
            "thread_id": str(thread_id) if thread_id else None,
            "last_message_time": last_message_time.isoformat() if last_message_time else None
        }

        logger.info(f"Last thread info for WhatsApp user {phone_num}: {result}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting last thread info for WhatsApp user {phone_num}: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to get last thread info: {str(e)}")


@router.get("/api/v2/whatsapp/threads/{thread_id}/history")
async def get_whatsapp_thread_history(thread_id: str, phone_num: str):
    """Get the message history for a WhatsApp user's thread from the Ansari backend.

    Args:
        thread_id: ID of the thread
        phone_num: User's WhatsApp phone number

    Returns:
        dict: Thread history with messages
    """
    try:
        logger.info(f"Getting thread history for WhatsApp user {phone_num}, thread {thread_id}")

        # Verify the user exists and has access to this thread
        user_id = db.retrieve_user_info(
            source=SourceType.WHATSAPP,
            phone_num=phone_num,
            db_cols=["id"] if hasattr(db, '_execute_query') else None
        )

        if not user_id:
            raise HTTPException(status_code=404, detail="WhatsApp user not found")

        # Extract user_id from result
        if isinstance(user_id, tuple):
            user_id = user_id[0]

        # Get the thread and verify ownership
        thread_data = db.get_thread(thread_id=thread_id, user_id=user_id)

        if not thread_data:
            raise HTTPException(status_code=404, detail="Thread not found or access denied")

        logger.info(f"Successfully retrieved thread history for WhatsApp user {phone_num}")
        return thread_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting thread history for WhatsApp user {phone_num}: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to get thread history: {str(e)}")


@router.post("/api/v2/whatsapp/messages/process")
def process_whatsapp_message(req: WhatsAppMessageRequest) -> StreamingResponse:
    """Process a message from a WhatsApp user with streaming response.

    Args:
        req: Message processing request containing phone_num, thread_id, and message

    Returns:
        StreamingResponse: Streamed AI response
    """
    try:
        logger.info(f"Processing message for WhatsApp user {req.phone_num}, thread {req.thread_id}")

        # Verify the user exists and get user_id
        user_id = db.retrieve_user_info(
            source=SourceType.WHATSAPP,
            phone_num=req.phone_num,
            db_cols=["id"] if hasattr(db, '_execute_query') else None
        )

        if not user_id:
            raise HTTPException(status_code=404, detail="WhatsApp user not found")

        # Extract user_id from result
        if isinstance(user_id, tuple):
            user_id = user_id[0]

        # Get the thread history
        history = db.get_thread(req.thread_id, user_id)

        if not history:
            raise HTTPException(status_code=404, detail="Thread not found")

        # Append the user's message to the history retrieved from the DB
        user_msg = {"role": "user", "content": [{"type": "text", "text": req.message}]}
        history["messages"].append(user_msg)

        # Use the presenter to process the message with streaming response
        logger.info(f"Starting streaming response for WhatsApp user {req.phone_num}")
        return presenter.complete(
            history,
            message_logger=MessageLogger(
                db,
                SourceType.WHATSAPP,
                user_id,
                req.thread_id,
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing message for WhatsApp user {req.phone_num}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Message processing failed: {str(e)}")