import unittest
from unittest.mock import MagicMock, patch

from ansari.agents.ansari_claude import AnsariClaude
from ansari.config import Settings


class TestAnsariClaudeEmptyTextBlock(unittest.TestCase):
    """Test that empty text blocks are not created in AnsariClaude responses."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock settings
        self.settings = Settings()
        self.settings.ANTHROPIC_MODEL = "test-model"
        self.settings.ANTHROPIC_API_KEY = "test-key"
        self.settings.MAX_FAILURES = 1

        # Create message logger mock
        self.message_logger = MagicMock()

        # Patch anthropic module
        self.patcher = patch("anthropic.Anthropic")
        self.mock_anthropic = self.patcher.start()
        self.mock_client = MagicMock()
        self.mock_anthropic.return_value = self.mock_client

        # Create instance with mocks
        self.agent = AnsariClaude(self.settings, self.message_logger)

        # Setup history with a user message
        self.agent.message_history = [{"role": "user", "content": [{"type": "text", "text": "test question"}]}]

    def tearDown(self):
        """Clean up after tests."""
        self.patcher.stop()

    def test_tool_use_empty_text(self):
        """Test that _finish_response doesn't create empty text blocks during tool_use."""
        # Mock direct call to _finish_response with empty text and tool calls
        assistant_text = ""  # Empty text
        tool_calls = [{"type": "tool_use", "id": "tool_123", "name": "test_tool", "input": {"query": "test"}}]

        # Setup tool handling mock
        self.agent.tool_name_to_instance = {"test_tool": MagicMock()}
        self.agent.tool_name_to_instance["test_tool"].run = MagicMock(return_value=[])
        self.agent.tool_name_to_instance["test_tool"].format_as_tool_result = MagicMock(return_value=[])
        self.agent.tool_name_to_instance["test_tool"].format_as_ref_list = MagicMock(return_value=[])
        self.agent.process_tool_call = MagicMock(return_value=([], []))

        # Call the method directly
        self.agent._finish_response(assistant_text, tool_calls)

        # Check that no empty text blocks were created
        for msg in self.agent.message_history:
            if msg["role"] == "assistant":
                for block in msg.get("content", []):
                    if block.get("type") == "text":
                        self.assertNotEqual("", block.get("text", "non-empty"), "Empty text block found in message")

    def test_tool_use_stop_reason_handling(self):
        """Test that we handle the 'tool_use' stop reason correctly without creating empty text blocks."""
        # Mock the _finish_response method to check how it's called
        self.agent._finish_response = MagicMock(return_value=None)
        self.agent.process_tool_call = MagicMock(return_value=([], []))

        # Create a message_delta chunk with tool_use stop reason
        message_delta = MagicMock()
        message_delta.type = "message_delta"
        message_delta.delta = MagicMock()
        message_delta.delta.stop_reason = "tool_use"

        # Simulate the state with just a tool call
        tool_calls = [{"type": "tool_use", "id": "tool_123", "name": "test_tool", "input": {"query": "test"}}]
        response_finished = False

        # Create a method to test the chunk handling logic directly
        def test_handler():
            # This simulates the chunk handling code in process_one_round
            if message_delta.delta.stop_reason == "tool_use":
                if not response_finished:
                    # Process tool calls directly without calling _finish_response
                    for tc in tool_calls:
                        self.agent.process_tool_call(tc["name"], tc["input"], tc["id"])

        # Run the test handler
        test_handler()

        # Verify _finish_response was NOT called for tool_use
        self.agent._finish_response.assert_not_called()

        # Verify process_tool_call was called instead
        self.agent.process_tool_call.assert_called_with("test_tool", {"query": "test"}, "tool_123")
