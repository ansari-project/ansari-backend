# This file aims to test the main API endpoints of the app (i.e., `main_api.py`) using pytest and FastAPI's TestClient.
# Explanatory NOTE: TestClient internally uses httpx and allows you to make requests to your FastAPI application
#           as if you were interacting with it over the network, but without actually starting a server.
# OPTIONAL READ: The following notes explain pytest's syntax:
# * Fixtures are functions that provide a fixed baseline for tests by setting up some state or context.
#       They can be used to provide test data / database connection / other setup tasks.
#       They can also be shared across multiple test functions.
#           This is why you see `register_user` passed as an argument to other test functions.
# * A pytest marker is a way to add metadata to test functions in pytest.
#       Markers can be used to categorize tests, control test execution, and apply specific behaviors/configs to tests.
#       For example, markers can be used to skip tests, parametrize tests with different input values, etc.
# * `mark.asyncio` means that the function is async., so it should be run using an asyncio event loop.
#       This is useful when testing async code like FastAPI endpoints.
# * (unused here, but useful info): a `@patch` decorator is used to temporarily replace an object or function
#       with a mock during a test.
#       It is part of the unittest.mock module and is useful for isolating the code being tested by mocking dependencies.
#       This allows you to control the behavior of dependencies and test how your code interacts with them.


import logging
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from ansari.ansari_db import AnsariDB
from ansari.ansari_logger import get_logger
from ansari.app.main_api import app
from ansari.config import get_settings

# TODO(anyone): Proper documentation on the the libraries/general-methedology
# used to create the test_*.py files

logger = get_logger(__name__)

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
        headers={"x-mobile-ansari": "ANSARI"},
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
        headers={"x-mobile-ansari": "ANSARI"},
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


# TODO(abdullah): implement the email validation logic, then uncomment this test
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
        headers={"x-mobile-ansari": "ANSARI"},
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
        headers={"x-mobile-ansari": "ANSARI"},
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
        headers={"x-mobile-ansari": "ANSARI"},
        json={
            "email": register_user["email"],
            "password": valid_password,
        },
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert "refresh_token" in response.json()
    assert response.json()["access_token"] != login_user["access_token"]
    assert response.json()["refresh_token"] != login_user["refresh_token"]
    # Create two new threads, one using the new access token,
    # the other using the old one
    # Skip the async test calls in this test as we're just testing token refresh
    # If we need to actually test thread creation, this would need to be an async test
    
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

    time.sleep(1)  # Ensure a different token due to timestamp differences
    response = client.post(
        "/api/v2/users/refresh_token",
        headers={
            "Authorization": f"Bearer {login_user['refresh_token']}",
            "x-mobile-ansari": "ANSARI",
        },
    )
    assert response.status_code == 200
    new_tokens = response.json()
    assert "access_token" in new_tokens
    assert "refresh_token" in new_tokens

    # Test the old access token is invalidated
    response = client.post(
        "/api/v2/users/logout",
        headers={
            "Authorization": f"Bearer {login_user['access_token']}",
            "x-mobile-ansari": "ANSARI",
        },
    )
    assert response.status_code == 401

    # Test the old refresh token is invalidated after it expires from the cache
    time.sleep(3)
    response = client.post(
        "/api/v2/users/refresh_token",
        headers={
            "Authorization": f"Bearer {login_user['refresh_token']}",
            "x-mobile-ansari": "ANSARI",
        },
    )
    assert response.status_code == 401

    # Validate new tokens work
    response = client.post(
        "/api/v2/users/logout",
        headers={
            "Authorization": f"Bearer {new_tokens['access_token']}",
            "x-mobile-ansari": "ANSARI",
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_invalid_refresh_token():
    response = client.post(
        "/api/v2/users/refresh_token",
        headers={
            "Authorization": "Bearer invalid_refresh_token",
            "x-mobile-ansari": "ANSARI",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_concurrent_refresh_requests(login_user):
    time.sleep(1)  # Ensure different token due to timestamp differences

    # Send two concurrent refresh token requests
    response1 = client.post(
        "/api/v2/users/refresh_token",
        headers={
            "Authorization": f"Bearer {login_user['refresh_token']}",
            "x-mobile-ansari": "ANSARI",
        },
    )
    response2 = client.post(
        "/api/v2/users/refresh_token",
        headers={
            "Authorization": f"Bearer {login_user['refresh_token']}",
            "x-mobile-ansari": "ANSARI",
        },
    )

    assert response1.status_code == 200
    assert response2.status_code == 200

    tokens1 = response1.json()
    tokens2 = response2.json()

    # Both responses should have the same token pair
    assert tokens1["access_token"] == tokens2["access_token"]
    assert tokens1["refresh_token"] == tokens2["refresh_token"]


@pytest.mark.asyncio
async def test_refresh_token_cache_expiry(login_user):
    time.sleep(1)  # Ensure different token due to timestamp differences

    # Send two concurrent refresh token requests
    response1 = client.post(
        "/api/v2/users/refresh_token",
        headers={
            "Authorization": f"Bearer {login_user['refresh_token']}",
            "x-mobile-ansari": "ANSARI",
        },
    )
    time.sleep(3)  # cache expiry is 3 seconds
    response2 = client.post(
        "/api/v2/users/refresh_token",
        headers={
            "Authorization": f"Bearer {login_user['refresh_token']}",
            "x-mobile-ansari": "ANSARI",
        },
    )

    assert response1.status_code == 200
    assert response2.status_code == 401


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
    assert response.json()["content"] == {"messages": [], "thread_name": None}
    assert response.json()["status"] == "success"


@pytest.mark.asyncio
async def test_thread_access(login_user, create_thread, login_another_user):
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
    allowed_origin = "https://ansari.chat"
    disallowed_origin = "https://disallowed.com"

    # Test with allowed origin
    base, domain = valid_email_base.split("@")
    email = f"{base}+{uuid.uuid4()}@{domain}"
    response = client.post(
        "/api/v2/users/register",
        headers={"origin": allowed_origin},
        json={
            "email": email,
            "password": valid_password,
            "first_name": "Jane",
            "last_name": "Doe",
        },
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
    assert response.headers["access-control-allow-origin"] == allowed_origin

    # Test with disallowed origin
    base, domain = valid_email_base.split("@")
    email = f"{base}+{uuid.uuid4()}@{domain}"
    response = client.post(
        "/api/v2/users/register",
        headers={
            "origin": disallowed_origin,
            # Testserver bypasses CORS check
            # Hence we need to explicitly set host
            # to not-testserver
            "host": "not-testserver",
        },
        json={
            "email": email,
            "password": valid_password,
            "first_name": "Jane",
            "last_name": "Doe",
        },
    )
    assert response.status_code == 502
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.asyncio
async def test_add_feedback(login_user, create_thread):
    # Add a message to the thread
    message_data = {"role": "user", "content": "Assalamu Alaikum Ansari! How are you?"}
    response = client.post(
        f"/api/v2/threads/{create_thread}",
        headers={
            "Authorization": f"Bearer {login_user['access_token']}",
            "x-mobile-ansari": "ANSARI",
        },
        json=message_data,
    )
    assert response.status_code == 200
    # log the response text
    for chunk in response.iter_text():
        print(chunk)
        # logging.info(chunk)

    # Add feedback to the message
    feedback_data = {
        "thread_id": create_thread,
        "message_id": 1,  # assuming the created message has an id of 1
        "feedback_class": "thumbsup",
        "comment": "Great response!",
    }
    response = client.post(
        "/api/v2/feedback",
        headers={
            "Authorization": f"Bearer {login_user['access_token']}",
            "x-mobile-ansari": "ANSARI",
        },
        json=feedback_data,
    )
    assert response.status_code == 200
    assert response.json() == {"status": "success"}


@pytest.fixture(scope="module")
def settings():
    return get_settings()


@pytest.fixture(scope="module")
def db(settings):
    return AnsariDB(settings)


@pytest.mark.integration
@pytest.mark.parametrize(
    "surah,ayah,question",
    [
        (1, 1, "What is the meaning of bismillah?"),
        (2, 255, "What is the significance of Ayat al-Kursi?"),
        (112, 1, "What does this ayah teach about Allah?"),
    ],
)
def test_answer_ayah_question_integration(settings, db, surah, ayah, question):
    api_key = settings.QURAN_DOT_COM_API_KEY.get_secret_value()

    # Test successful request
    start_time = time.time()
    response = client.post(
        "/api/v2/ayah",
        json={
            "surah": surah,
            "ayah": ayah,
            "question": question,
            "augment_question": False,
            "apikey": api_key,
        },
    )
    end_time = time.time()

    assert response.status_code == 200, f"Failed with status code {response.status_code}"
    assert "response" in response.json(), "Response doesn't contain 'response' key"

    answer = response.json()["response"]
    assert isinstance(answer, str), "Answer is not a string"
    assert len(answer) > 0, "Answer is empty"

    # Check response time
    assert end_time - start_time < 60, "Response took too long"

    # Check database storage
    stored_answer = db.get_quran_answer(surah, ayah, question)
    assert stored_answer == answer, "Stored answer doesn't match the API response"

    # Test error handling
    error_response = client.post(
        "/api/v2/ayah",
        json={
            "surah": surah,
            "ayah": ayah,
            "question": question,
            "augment_question": False,
            "apikey": "wrong_api_key",
        },
    )
    assert error_response.status_code == 401, "Incorrect API key should return 401"
