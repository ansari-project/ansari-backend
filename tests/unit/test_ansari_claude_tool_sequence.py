import uuid
import sys
import os

# Add the src directory to the path so we can import the modules
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
sys.path.insert(0, src_path)

from unittest.mock import MagicMock, patch
from ansari.agents.ansari_claude import AnsariClaude
from ansari.config import Settings


def test_process_message_history_with_tools():
    """Test that message processing correctly handles tool_use and tool_result relationships."""

    # Create mock settings
    settings = MagicMock(spec=Settings)
    settings.ANTHROPIC_MODEL = "claude-3-opus-20240229"

    # Create a unique tool ID for testing
    tool_id = str(uuid.uuid4())
    invalid_tool_id = str(uuid.uuid4())  # This won't match any tool_use block

    # Create a test message history with tool use and tool result
    test_history = [
        # Message 1: Assistant with tool_use
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Let me search for that information."},
                {"type": "tool_use", "id": tool_id, "name": "search_quran", "input": {"query": "mercy in quran"}},
            ],
        },
        # Message 2: User with tool_result (valid tool_use_id)
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": "Found 114 verses mentioning mercy."}],
        },
        # Message 3: User with tool_result (invalid tool_use_id)
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": invalid_tool_id, "content": "This should be filtered out"}],
        },
        # Message 4: User with simple text
        {"role": "user", "content": "Tell me more about mercy in the Quran."},
    ]

    # Mock the necessary parts of AnsariClaude
    with (
        patch.object(AnsariClaude, "__init__", return_value=None),
        patch.object(AnsariClaude, "process_one_round", return_value=[]),
    ):
        claude = AnsariClaude.__new__(AnsariClaude)
        claude.settings = settings
        claude.message_history = test_history.copy()
        claude.message_logger = None
        claude.client = MagicMock()

        # Add a final assistant response to avoid infinite loop
        def add_assistant_response(*args, **kwargs):
            if len(claude.message_history) > 0 and claude.message_history[-1]["role"] == "user":
                claude.message_history.append({"role": "assistant", "content": [{"type": "text", "text": "Test response"}]})
            return []

        claude.process_one_round = MagicMock(side_effect=add_assistant_response)

        # Run the message processing
        list(claude.process_message_history(use_tool=False, stream=False))

        # Verify the results
        processed_history = claude.message_history

        # Message 1 (assistant with tool_use) should keep its structure
        assert processed_history[0]["role"] == "assistant"
        assert len(processed_history[0]["content"]) == 2
        assert processed_history[0]["content"][0]["type"] == "text"
        assert processed_history[0]["content"][1]["type"] == "tool_use"
        assert processed_history[0]["content"][1]["id"] == tool_id

        # Message 2 (user with valid tool_result) should keep its structure
        assert processed_history[1]["role"] == "user"
        assert isinstance(processed_history[1]["content"], list)
        assert len(processed_history[1]["content"]) == 1
        assert processed_history[1]["content"][0]["type"] == "tool_result"
        assert processed_history[1]["content"][0]["tool_use_id"] == tool_id

        # Message 3 (user with invalid tool_result) should be filtered
        assert processed_history[2]["role"] == "user"
        if isinstance(processed_history[2]["content"], list):
            assert len(processed_history[2]["content"]) == 0
        else:
            assert isinstance(processed_history[2]["content"], str)

        # Message 4 (user with simple text) should remain unchanged
        assert processed_history[3]["role"] == "user"
        assert processed_history[3]["content"] == "Tell me more about mercy in the Quran."

        print("All assertions passed - message processing correctly handled tool relationships!")


if __name__ == "__main__":
    test_process_message_history_with_tools()
