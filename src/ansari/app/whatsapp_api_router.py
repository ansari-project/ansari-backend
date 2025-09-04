# WhatsApp API router for ansari-backend
"""API router for handling requests from the WhatsApp service."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ansari.ansari_logger import get_logger
from ansari.ansari_db import AnsariDB, MessageLogger, SourceType
from ansari.config import get_settings
from ansari.agents import Ansari, AnsariClaude

logger = get_logger(__name__)
db = AnsariDB(get_settings())

# Initialize the Ansari agent
settings = get_settings()
agent_type = settings.AGENT

if agent_type == "Ansari":
    ansari = Ansari(settings)
elif agent_type == "AnsariClaude":
    ansari = AnsariClaude(settings)
else:
    raise ValueError(f"Unknown agent type: {agent_type}. Must be one of: Ansari, AnsariClaude")

# Create a router for WhatsApp API endpoints
whatsapp_api_router = APIRouter(prefix="/api/v2/whatsapp", tags=["whatsapp"])

# ----- Models -----


class WhatsAppUserRegistration(BaseModel):
    """Model for WhatsApp user registration."""

    phone_num: str
    preferred_language: str = "en"


class WhatsAppUserLocation(BaseModel):
    """Model for updating WhatsApp user location."""

    phone_num: str
    latitude: float
    longitude: float


class ThreadCreation(BaseModel):
    """Model for thread creation."""

    phone_num: str
    title: str


class MessageProcessing(BaseModel):
    """Model for message processing."""

    phone_num: str
    thread_id: str
    message: str


# ----- Endpoints -----


@whatsapp_api_router.post("/users/register")
async def register_whatsapp_user(request: WhatsAppUserRegistration):
    """Register a new WhatsApp user."""
    try:
        # Check if user already exists
        if db.account_exists(phone_num=request.phone_num):
            return {"status": "success", "message": "User already exists"}

        # Register the user
        result = db.register(
            source=SourceType.WHATSAPP, phone_num=request.phone_num, preferred_language=request.preferred_language
        )

        if result["status"] == "success":
            return {"status": "success", "user_id": result.get("user_id")}
        else:
            raise HTTPException(status_code=500, detail="Failed to register user")
    except Exception as e:
        logger.error(f"Error registering WhatsApp user: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@whatsapp_api_router.get("/users/exists")
async def check_whatsapp_user_exists(phone_num: str):
    """Check if a WhatsApp user exists."""
    try:
        exists = db.account_exists(phone_num=phone_num)
        return {"exists": exists}
    except Exception as e:
        logger.error(f"Error checking if WhatsApp user exists: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@whatsapp_api_router.put("/users/location")
async def update_whatsapp_user_location(request: WhatsAppUserLocation):
    """Update a WhatsApp user's location."""
    try:
        # Check if user exists
        if not db.account_exists(phone_num=request.phone_num):
            raise HTTPException(status_code=404, detail="User not found")

        # Update the user's location
        db.update_user_by_phone_num(request.phone_num, {"loc_lat": request.latitude, "loc_long": request.longitude})

        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error updating WhatsApp user location: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@whatsapp_api_router.post("/threads")
async def create_thread(request: ThreadCreation):
    """Create a new thread for a WhatsApp user."""
    try:
        # Check if user exists
        if not db.account_exists(phone_num=request.phone_num):
            raise HTTPException(status_code=404, detail="User not found")

        # Get user ID
        user_id = db.retrieve_user_info(source=SourceType.WHATSAPP, phone_num=request.phone_num)

        # Create the thread
        result = db.create_thread(SourceType.WHATSAPP, user_id, request.title)

        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        return {"thread_id": result["thread_id"]}
    except Exception as e:
        logger.error(f"Error creating WhatsApp thread: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@whatsapp_api_router.get("/threads/last")
async def get_last_thread_info(phone_num: str):
    """Get the last active thread for a WhatsApp user."""
    try:
        # Check if user exists
        if not db.account_exists(phone_num=phone_num):
            return {"thread_id": None, "last_message_time": None}

        # Get user ID
        user_id = db.retrieve_user_info(source=SourceType.WHATSAPP, phone_num=phone_num)

        # Get the last thread
        thread_id, last_msg_time = db.get_last_message_time_whatsapp(user_id)

        return {"thread_id": thread_id, "last_message_time": last_msg_time.isoformat() if last_msg_time else None}
    except Exception as e:
        logger.error(f"Error getting last thread info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@whatsapp_api_router.get("/threads/{thread_id}/history")
async def get_thread_history(thread_id: str, phone_num: str):
    """Get message history for a thread."""
    try:
        # Check if user exists
        if not db.account_exists(phone_num=phone_num):
            raise HTTPException(status_code=404, detail="User not found")

        # Get user ID
        user_id = db.retrieve_user_info(source=SourceType.WHATSAPP, phone_num=phone_num)

        # Get the thread history
        thread_history = db.get_thread(thread_id, user_id)

        if not thread_history:
            raise HTTPException(status_code=404, detail="Thread not found")

        return thread_history
    except Exception as e:
        logger.error(f"Error getting thread history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@whatsapp_api_router.post("/messages/process")
async def process_message(request: MessageProcessing):
    """Process a message from a WhatsApp user and return a streaming response."""
    try:
        # Check if user exists
        if not db.account_exists(phone_num=request.phone_num):
            raise HTTPException(status_code=404, detail="User not found")

        # Get user ID
        user_id = db.retrieve_user_info(source=SourceType.WHATSAPP, phone_num=request.phone_num)

        # Get thread history
        thread_history = db.get_thread_llm(request.thread_id, user_id)
        if "messages" not in thread_history:
            raise HTTPException(status_code=500, detail="Error retrieving thread history")

        # Prepare message history
        msg_history = thread_history["messages"]

        # Add user message to history
        user_msg = {"role": "user", "content": [{"type": "text", "text": request.message}]}
        msg_history.append(user_msg)

        # Create message logger
        message_logger = MessageLogger(db, SourceType.WHATSAPP, user_id, request.thread_id)

        # Process the message using the appropriate agent
        if agent_type == "Ansari":
            agent_instance = Ansari(settings=settings, message_logger=message_logger)
        elif agent_type == "AnsariClaude":
            agent_instance = AnsariClaude(settings=settings, message_logger=message_logger)

        return StreamingResponse(agent_instance.replace_message_history(msg_history), media_type="text/plain")

    except Exception as e:
        logger.error(f"Error processing message: {e}")
        raise HTTPException(status_code=500, detail=str(e))
