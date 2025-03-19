import logging
import uuid

import pytest
from fastapi.testclient import TestClient

from ansari.app.main_api import app

logger = logging.getLogger(__name__)

client = TestClient(app)

# Test data
valid_email = f"test_{uuid.uuid4()}@example.com"
valid_password = "StrongPassword123!"
first_name = "John"
last_name = "Doe"


@pytest.fixture
def register_and_login_user():
    # Register a user
    register_response = client.post(
        "/api/v2/users/register",
        json={
            "email": valid_email,
            "password": valid_password,
            "first_name": first_name,
            "last_name": last_name,
        },
    )
    assert register_response.status_code == 200

    # Login with the registered user
    login_response = client.post(
        "/api/v2/users/login",
        json={
            "email": valid_email,
            "password": valid_password,
        },
    )
    assert login_response.status_code == 200
    return login_response.json()


@pytest.mark.asyncio
async def test_message_id_in_thread_response(register_and_login_user):
    """Test that message IDs are included in thread responses."""
    access_token = register_and_login_user["access_token"]

    # Create a new thread
    thread_response = client.post(
        "/api/v2/threads",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert thread_response.status_code == 200
    thread_id = thread_response.json()["thread_id"]

    # Add a message to the thread
    message_data = {"role": "user", "content": "Test message with ID"}
    client.post(
        f"/api/v2/threads/{thread_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        json=message_data,
    )

    # Get the thread and verify it contains message IDs
    thread_get_response = client.get(
        f"/api/v2/threads/{thread_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert thread_get_response.status_code == 200

    # Check that the thread contains messages with IDs
    thread_data = thread_get_response.json()
    assert "messages" in thread_data
    assert len(thread_data["messages"]) > 0

    # Verify each message has an ID field
    for message in thread_data["messages"]:
        assert "id" in message, f"Message does not contain ID field: {message}"
        assert isinstance(message["id"], int), f"Message ID is not an integer: {message['id']}"
        assert message["id"] > 0, f"Message ID is not positive: {message['id']}"
