import time
import logging
import uuid

import pytest
from fastapi.testclient import TestClient

from main_api import app

client = TestClient(app)

# Test data
valid_email_base = "test@example.com"
valid_password = "StrongPassword123!"
weak_password = "qwerty"
first_name = "John"
last_name = "Doe"


@pytest.fixture
def register_user():
    # Generate a unique email for each test
    base, domain = valid_email_base.split("@")
    email = f"{base}+{uuid.uuid4()}@{domain}"

    # Register a user before each test that requires a valid token
    response = client.post(
        "/api/v2/users/register",
        headers={"x-mobile-ansari": "ANSARI"},
        json={
            "email": email,
            "password": valid_password,
            "first_name": first_name,
            "last_name": last_name,
        },
    )
    assert response.status_code == 200
    json_response = {**response.json(), "email": email}
    return json_response


@pytest.fixture
def register_another_user():
    # Generate a unique email for each test
    base, domain = valid_email_base.split("@")
    email = f"{base}+{uuid.uuid4()}@{domain}"

    # Register a user before each test that requires a valid token
    response = client.post(
        "/api/v2/users/register",
        headers={"x-mobile-ansari": "ANSARI"},
        json={
            "email": email,
            "password": valid_password,
            "first_name": first_name,
            "last_name": last_name,
        },
    )
    assert response.status_code == 200
    json_response = {**response.json(), "email": email}
    return json_response


@pytest.fixture
def login_user(register_user):
    # Log in the user before each test that requires a valid token
    response = client.post(
        "/api/v2/users/login",
        json={
            "email": register_user["email"],
            "password": valid_password,
        },
    )
    assert response.status_code == 200
    return response.json()


@pytest.fixture
def login_another_user(register_another_user):
    # Log in the user before each test that requires a valid token
    response = client.post(
        "/api/v2/users/login",
        json={
            "email": register_another_user["email"],
            "password": valid_password,
        },
    )
    assert response.status_code == 200
    return response.json()["access_token"]


@pytest.fixture
def create_thread(login_user):
    # Create a thread before each test that requires a thread
    response = client.post(
        "/api/v2/threads",
        headers={
            "Authorization": f"Bearer {login_user['access_token']}",
            "x-mobile-ansari": "ANSARI",
        },
    )
    assert response.status_code == 200
    return response.json()["thread_id"]


@pytest.mark.asyncio
async def test_register_new_user():
    # Test registering a new user with valid credentials
    base, domain = valid_email_base.split("@")
    email = f"{base}+{uuid.uuid4()}@{domain}"
    response = client.post(
        "/api/v2/users/register",
        headers={"x-mobile-ansari": "ANSARI"},
        json={
            "email": email,
            "password": valid_password,
            "first_name": "Jane",
            "last_name": "Doe",
        },
    )
    assert response.status_code == 200


# TODO: implement the email validation logic, then uncomment this test
# This test will fail, because the email is not validated
# @pytest.mark.asyncio
# async def test_register_invalid_email():
#     # Test registering a new user with an invalid email
#     response = client.post(
#         "/api/v2/users/register",
#         headers={"x-mobile-ansari": "ANSARI"},
#         json={
#             "email": "invalid_email",
#             "password": valid_password,
#             "first_name": "Jane",
#             "last_name": "Doe",
#         },
#     )
#     assert response.status_code == 400
#     assert response.json()["detail"] == "Invalid email"

# This will give an error because zxcvbn raises an IndexError when an empty password is given.
# See this issue https://github.com/dwolfhub/zxcvbn-python/issues/64
# @pytest.mark.asyncio
# async def test_register_blank_password():
#     # Test registering a new user with a blank password
#     base, domain = valid_email_base.split("@")
#     email = f"{base}+{uuid.uuid4()}@{domain}"
#     response = client.post(
#         "/api/v2/users/register",
#         headers={"x-mobile-ansari": "ANSARI"},
#         json={
#             "email": email,
#             "password": "",
#             "first_name": "Jane",
#             "last_name": "Doe",
#         },
#     )
#     assert response.status_code == 400
#     assert response.json()["detail"] == "Password is required"


@pytest.mark.asyncio
async def test_login_valid_credentials(register_user):
    # Test logging in with valid credentials
    response = client.post(
        "/api/v2/users/login",
        json={
            "email": register_user["email"],
            "password": valid_password,
        },
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert "refresh_token" in response.json()


@pytest.mark.asyncio
async def test_login_invalid_credentials():
    # Test logging in with invalid credentials
    response = client.post(
        "/api/v2/users/login",
        json={
            "email": "invalid@example.com",
            "password": "wrongpassword",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid username or password"

@pytest.mark.asyncio
async def test_login_from_several_devices(register_user, login_user):
    # Create another session, i.e. another access/refresh tokens pair
    time.sleep(1)
    response = client.post(
        "/api/v2/users/login",
        json={
            "email": register_user["email"],
            "password": valid_password,
        },
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert "refresh_token" in response.json()
    assert response.json()["access_token"]!= login_user["access_token"]
    assert response.json()["refresh_token"]!= login_user["refresh_token"]
    # Create two new threads, one using the new access token, 
    # the other using the old one
    test_create_thread(response.json())
    test_create_thread(login_user)

    # Create a new thread using the old access token..
    # ..after logging out from the new device
    response = client.post(
        "/api/v2/users/logout",
        headers={
            "Authorization": f"Bearer {response.json()['access_token']}",
            "x-mobile-ansari": "ANSARI",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    test_create_thread(login_user)

@pytest.mark.asyncio
async def test_logout(login_user, create_thread):
    # Test logging out with a valid token
    response = client.post(
        "/api/v2/users/logout",
        headers={
            "Authorization": f"Bearer {login_user['access_token']}",
            "x-mobile-ansari": "ANSARI",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    # Try to access the thread after logout
    response = client.get(
        f"/api/v2/threads/{create_thread}",
        headers={
            "Authorization": f"Bearer {login_user['access_token']}",
            "x-mobile-ansari": "ANSARI",
        },
    )
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_refresh_token_request(login_user):
    # Test logging in with valid credentials
    # The JWT library in Python does not encode the timestamp with microsecond precision. 
    # It only considers the number of seconds since the epoch. 
    # Therefore, we need to wait for at least a second to get different tokens.
    time.sleep(1)
    response = client.post(
        "/api/v2/users/refresh_token",
         headers={
            "Authorization": f"Bearer {login_user['refresh_token']}",
            "x-mobile-ansari": "ANSARI",
        },
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert "refresh_token" in response.json()
    # Test logging out with the old access_token
    response = client.post(
        "/api/v2/users/logout",
        headers={
            "Authorization": f"Bearer {login_user['access_token']}",
            "x-mobile-ansari": "ANSARI",
        },
    )
    assert response.status_code == 401
    # Test refresh_token with the old refresh_token
    response = client.post(
        "/api/v2/users/refresh_token",
        headers={
            "Authorization": f"Bearer {login_user['refresh_token']}",
            "x-mobile-ansari": "ANSARI",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_thread(login_user):
    # Test creating a thread with a valid token
    response = client.post(
        "/api/v2/threads",
        headers={
            "Authorization": f"Bearer {login_user['access_token']}",
            "x-mobile-ansari": "ANSARI",
        },
    )
    assert response.status_code == 200
    assert "thread_id" in response.json()


@pytest.mark.asyncio
async def test_delete_thread(login_user, create_thread):
    # Test deleting a thread with a valid token
    response = client.delete(
        f"/api/v2/threads/{create_thread}",
        headers={
            "Authorization": f"Bearer {login_user['access_token']}",
            "x-mobile-ansari": "ANSARI",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    # Try to access the deleted thread
    response = client.get(
        f"/api/v2/threads/{create_thread}",
        headers={
            "Authorization": f"Bearer {login_user['access_token']}",
            "x-mobile-ansari": "ANSARI",
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Thread not found"


@pytest.mark.asyncio
async def test_share_thread(login_user, create_thread):
    # Test deleting a thread with a valid token
    response = client.post(
        f"/api/v2/share/{create_thread}",
        headers={
            "Authorization": f"Bearer {login_user['access_token']}",
            "x-mobile-ansari": "ANSARI",
        },
    )
    logging.info(f"Response is {response}")
    json = response.json()
    logging.info(f"JSON is {json}")
    share_uuid = json["share_uuid"]
    logging.info(f"Share UUID is {share_uuid}")
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    # Now check that this worked.
    response = client.get(
        f"api/v2/share/{share_uuid}",
        headers={
            # NOTE: We do not need to pass the Authorization header here
            # Accessing a shared thread does not require authentication
            "x-mobile-ansari": "ANSARI",
        },
    )
    assert response.status_code == 200
    assert response.json()["content"] == '{"thread_name": null, "messages": []}'
    assert response.json()["status"] == "success"


@pytest.mark.asyncio
async def test_thread_access(
    login_user, create_thread, login_another_user
):
    # Try to access the first user's thread with the second user's token
    response = client.get(
        f"/api/v2/threads/{create_thread}",
        headers={
            "Authorization": f"Bearer {login_another_user}",
            "x-mobile-ansari": "ANSARI",
        },
    )
    assert response.status_code == 404

    # Try to access the first user's thread with the first user's token
    response = client.get(
        f"/api/v2/threads/{create_thread}",
        headers={
            "Authorization": f"Bearer {login_user['access_token']}",
            "x-mobile-ansari": "ANSARI",
        },
    )
    # This should return a 200 OK response
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_cors():
    # Test CORS
    allowed_origin = "https://beta.ansari.chat"
    disallowed_origin = "https://disallowed.com"

    # Test with allowed origin
    base, domain = valid_email_base.split("@")
    email = f"{base}+{uuid.uuid4()}@{domain}"
    response = client.post(
        "/api/v2/users/register",
        headers={"Origin": allowed_origin, "x-mobile-ansari": "ANSARI"},
        json={
            "email": email,
            "password": valid_password,
            "first_name": "Jane",
            "last_name": "Doe",
        },
    )
    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" in response.headers
    assert response.headers["Access-Control-Allow-Origin"] == allowed_origin

    # Test with disallowed origin
    base, domain = valid_email_base.split("@")
    email = f"{base}+{uuid.uuid4()}@{domain}"
    response = client.post(
        "/api/v2/users/register",
        headers={"Origin": disallowed_origin, "x-mobile-ansari": "ANSARI"},
        json={
            "email": email,
            "password": valid_password,
            "first_name": "Jane",
            "last_name": "Doe",
        },
    )
    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" not in response.headers