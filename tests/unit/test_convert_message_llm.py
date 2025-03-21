import json
import uuid
from unittest.mock import MagicMock, patch

from ansari.ansari_db import AnsariDB
from ansari.config import Settings


def test_convert_message_llm_formats():
    """Test the convert_message_llm function to ensure it formats messages correctly."""
    # Setup a mocked DB instance
    settings = MagicMock(spec=Settings)
    settings.DATABASE_URL = "postgresql://fake:fake@localhost:5432/fake"
    settings.SECRET_KEY = MagicMock()
    settings.SECRET_KEY.get_secret_value.return_value = "test_secret_key"
    settings.ALGORITHM = "HS256"
    settings.ENCODING = "utf-8"

    with patch("psycopg2.pool.SimpleConnectionPool"):
        db = AnsariDB(settings)

    # Test 1: Simple user message
    user_msg = ("user", "Hello, how are you?", None, None, None)
    result = db.convert_message_llm(user_msg)

    assert len(result) == 1
    assert result[0]["role"] == "user"
    assert result[0]["content"] == "Hello, how are you?"

    # Test 2: Simple assistant message
    assistant_msg = ("assistant", "I'm doing well, thank you!", None, None, None)
    result = db.convert_message_llm(assistant_msg)

    assert len(result) == 1
    assert result[0]["role"] == "assistant"
    assert isinstance(result[0]["content"], list)
    assert len(result[0]["content"]) == 1
    assert result[0]["content"][0]["type"] == "text"
    assert result[0]["content"][0]["text"] == "I'm doing well, thank you!"

    # Test 3: Assistant message with tool use
    tool_id = str(uuid.uuid4())
    tool_details_json = json.dumps({"id": tool_id, "args": {"query": "mercy in quran"}})

    assistant_tool_msg = ("assistant", "Let me search for that", "search_quran", tool_details_json, None)
    result = db.convert_message_llm(assistant_tool_msg)

    assert len(result) == 1
    assert result[0]["role"] == "assistant"
    assert isinstance(result[0]["content"], list)
    assert len(result[0]["content"]) == 2  # text block + tool_use block

    # Check text block
    assert result[0]["content"][0]["type"] == "text"
    assert result[0]["content"][0]["text"] == "Let me search for that"

    # Check tool_use block
    assert result[0]["content"][1]["type"] == "tool_use"
    assert result[0]["content"][1]["id"] == tool_id
    assert result[0]["content"][1]["name"] == "search_quran"

    print("All tests passed!")


if __name__ == "__main__":
    test_convert_message_llm_formats()
