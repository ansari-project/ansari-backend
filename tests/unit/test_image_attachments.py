"""Tests for image attachments in chat messages (helpers, DB storage, and the thread endpoints).

Images are sent to the LLM for the current turn only and are never stored.
"""

import base64
import uuid
from unittest.mock import patch

import pytest
from bson import ObjectId
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from ansari.ansari_db import AnsariDB, SourceType
from ansari.util.attachments import (
    add_omitted_image_notes,
    decode_and_validate_image,
    make_image_block,
    omitted_images_note,
    redact_images,
    replace_images_with_placeholders,
)

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32
PNG_B64 = base64.b64encode(PNG_BYTES).decode()
PLACEHOLDER = {"type": "image_placeholder", "media_type": "image/png"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestDecodeAndValidateImage:
    def test_valid_png(self):
        assert decode_and_validate_image(PNG_B64, "image/png", 1000) == PNG_BYTES

    def test_data_url_prefix_is_tolerated(self):
        assert decode_and_validate_image(f"data:image/png;base64,{PNG_B64}", "image/png", 1000) == PNG_BYTES

    def test_unsupported_media_type(self):
        with pytest.raises(ValueError, match="Unsupported image type"):
            decode_and_validate_image(PNG_B64, "image/svg+xml", 1000)

    def test_invalid_base64(self):
        with pytest.raises(ValueError, match="not valid base64"):
            decode_and_validate_image("not base64!!", "image/png", 1000)

    def test_too_large(self):
        with pytest.raises(ValueError, match="too large"):
            decode_and_validate_image(PNG_B64, "image/png", 10)

    def test_content_must_match_declared_type(self):
        with pytest.raises(ValueError, match="does not match"):
            decode_and_validate_image(base64.b64encode(JPEG_BYTES).decode(), "image/png", 1000)


def test_replace_images_with_placeholders():
    content = [make_image_block("image/png", PNG_BYTES), {"type": "text", "text": "hi"}]
    assert replace_images_with_placeholders(content) == [PLACEHOLDER, {"type": "text", "text": "hi"}]
    # Content without images is returned as-is
    text_only = [{"type": "text", "text": "hi"}]
    assert replace_images_with_placeholders(text_only) is text_only
    assert replace_images_with_placeholders("hi") == "hi"


class TestAddOmittedImageNotes:
    def test_text_only_history_is_unchanged(self):
        messages = [
            {"id": "1", "role": "user", "content": "Salam"},
            {"id": "2", "role": "assistant", "content": "Wa alaikum salam"},
        ]
        assert add_omitted_image_notes(messages) == messages

    def test_note_is_prepended_and_field_removed(self):
        messages = [{"id": "1", "role": "user", "content": "What ayah is this?", "image_count": 2}]
        [result] = add_omitted_image_notes(messages)
        assert "image_count" not in result
        assert result["content"] == f"{omitted_images_note(2)}\n\nWhat ayah is this?"

    def test_image_only_message_is_never_empty(self):
        [result] = add_omitted_image_notes([{"id": "1", "role": "user", "content": "", "image_count": 1}])
        assert result["content"] == omitted_images_note(1)


def test_redact_images_does_not_mutate_original():
    message = {"role": "user", "content": [make_image_block("image/png", PNG_BYTES), {"type": "text", "text": "hi"}]}
    redacted = redact_images(message)

    assert "redacted" in redacted["content"][0]["source"]["data"]
    assert message["content"][0]["source"]["data"] == PNG_B64
    assert redacted["content"][1] == {"type": "text", "text": "hi"}


# ---------------------------------------------------------------------------
# DB layer (with an in-memory stand-in for the Mongo collection)
# ---------------------------------------------------------------------------


class _FakeCollection:
    def __init__(self):
        self.updates = []

    def update_one(self, query, update):
        self.updates.append((query, update))


@pytest.fixture
def fake_db():
    db = AnsariDB.__new__(AnsariDB)
    threads = _FakeCollection()
    db.get_collection = lambda name: threads
    return db, threads


def test_append_message_does_not_store_image_data(fake_db):
    db, threads = fake_db
    message = {"role": "user", "content": [make_image_block("image/png", PNG_BYTES), {"type": "text", "text": "hi"}]}

    db.append_message(SourceType.WEB, ObjectId(), message)

    stored = threads.updates[0][1]["$push"]["messages"]
    assert stored["content"] == [PLACEHOLDER, {"type": "text", "text": "hi"}]
    # The in-memory message (still used by the agent during this turn) keeps its image
    assert message["content"][0]["source"]["type"] == "base64"


def test_convert_message_exposes_image_count(fake_db):
    db, _ = fake_db

    with_text = db.convert_message({"id": "1", "role": "user", "content": [PLACEHOLDER, {"type": "text", "text": "hi"}]})
    assert with_text == {"id": "1", "role": "user", "content": "hi", "image_count": 1}

    image_only = db.convert_message({"id": "2", "role": "user", "content": [PLACEHOLDER, PLACEHOLDER]})
    assert image_only == {"id": "2", "role": "user", "content": "", "image_count": 2}

    # Messages without images keep their previous shape (no `image_count` key)
    tool_result = [{"type": "tool_result", "tool_use_id": "t1", "content": []}]
    assert db.convert_message({"id": "3", "role": "user", "content": tool_result}) == {
        "id": "3",
        "role": "user",
        "content": tool_result,
    }


# ---------------------------------------------------------------------------
# API (uses the configured MongoDB, like test_main_api.py; the LLM call is mocked)
# ---------------------------------------------------------------------------


@pytest.fixture
def api_client():
    from ansari.app.main_api import app

    return TestClient(app)


@pytest.fixture
def auth_headers(api_client):
    email = f"test+{uuid.uuid4()}@example.com"
    password = "StrongPassword123!"
    headers = {"x-mobile-ansari": "ANSARI"}
    response = api_client.post(
        "/api/v2/users/register",
        headers=headers,
        json={"email": email, "password": password, "first_name": "John", "last_name": "Doe"},
    )
    assert response.status_code == 200
    response = api_client.post("/api/v2/users/login", headers=headers, json={"email": email, "password": password})
    assert response.status_code == 200
    return {**headers, "Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def captured_histories():
    """Replace the LLM call: record the history it receives and log the user message like the agent does."""
    histories = []

    def fake_complete(history, message_logger=None):
        histories.append(history["messages"])
        message_logger.log(history["messages"][-1])
        message_logger.log({"role": "assistant", "content": [{"type": "text", "text": "ok"}]})
        return StreamingResponse(iter(["ok"]))

    with patch("ansari.app.main_api.presenter.complete", side_effect=fake_complete):
        yield histories


def test_image_is_sent_once_and_not_stored(api_client, auth_headers, captured_histories):
    from ansari.app.main_api import db

    thread_id = api_client.post("/api/v2/threads", headers=auth_headers).json()["thread_id"]

    response = api_client.post(
        f"/api/v2/threads/{thread_id}",
        headers=auth_headers,
        json={
            "role": "user",
            "content": "What is written here?",
            "attachments": [{"media_type": "image/png", "data": PNG_B64}],
        },
    )
    assert response.status_code == 200
    assert captured_histories[0][-1]["content"] == [
        make_image_block("image/png", PNG_BYTES),
        {"type": "text", "text": "What is written here?"},
    ]

    # Nothing of the image is stored in the thread
    raw_thread = db.get_collection("threads").find_one({"_id": ObjectId(thread_id)})
    assert PNG_B64 not in str(raw_thread)

    # The thread shows that an image was attached
    thread = api_client.get(f"/api/v2/threads/{thread_id}", headers=auth_headers).json()
    [user_msg] = [m for m in thread["messages"] if m["role"] == "user"]
    assert user_msg["content"] == "What is written here?"
    assert user_msg["image_count"] == 1

    # A follow-up turn tells the LLM about the earlier image without resending it
    response = api_client.post(
        f"/api/v2/threads/{thread_id}", headers=auth_headers, json={"role": "user", "content": "And the second line?"}
    )
    assert response.status_code == 200
    history = captured_histories[1]
    assert history[0]["content"] == f"{omitted_images_note(1)}\n\nWhat is written here?"
    assert all("image_count" not in m for m in history)
    assert history[-1]["content"] == [{"type": "text", "text": "And the second line?"}]


def test_image_only_message(api_client, auth_headers, captured_histories):
    thread_id = api_client.post("/api/v2/threads", headers=auth_headers).json()["thread_id"]
    response = api_client.post(
        f"/api/v2/threads/{thread_id}",
        headers=auth_headers,
        json={"role": "user", "attachments": [{"media_type": "image/png", "data": PNG_B64}]},
    )
    assert response.status_code == 200
    assert captured_histories[0][-1]["content"] == [make_image_block("image/png", PNG_BYTES)]

    thread = api_client.get(f"/api/v2/threads/{thread_id}", headers=auth_headers).json()
    assert thread["thread_name"] == "Image"
    assert thread["messages"][0]["content"] == ""
    assert thread["messages"][0]["image_count"] == 1


@pytest.mark.parametrize(
    "body, detail",
    [
        ({"role": "user", "content": "  "}, "must contain text or at least one image"),
        (
            {"role": "user", "content": "hi", "attachments": [{"media_type": "image/png", "data": PNG_B64}] * 5},
            "At most 4 images",
        ),
        (
            {"role": "user", "content": "hi", "attachments": [{"media_type": "image/jpeg", "data": PNG_B64}]},
            "does not match",
        ),
    ],
)
def test_invalid_messages_are_rejected(api_client, auth_headers, captured_histories, body, detail):
    thread_id = api_client.post("/api/v2/threads", headers=auth_headers).json()["thread_id"]
    response = api_client.post(f"/api/v2/threads/{thread_id}", headers=auth_headers, json=body)
    assert response.status_code == 400
    assert detail in response.json()["detail"]
    assert captured_histories == []
