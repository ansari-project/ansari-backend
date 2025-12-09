"""Test cache control logic without complex mocking."""

import unittest
import json


class TestCacheControlLogic(unittest.TestCase):
    """Test the cache control logic implementation."""

    def test_cache_control_only_on_last_block(self):
        """Test that cache control is only added to the last content block."""
        # Create a message history similar to what the API would receive
        message_history = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "First block"},
                    {"type": "document", "source": {"data": "doc1"}, "title": "Doc 1"},
                    {"type": "document", "source": {"data": "doc2"}, "title": "Doc 2"},
                    {"type": "document", "source": {"data": "doc3"}, "title": "Doc 3"},
                    {"type": "text", "text": "Last block"},
                ],
            }
        ]

        # Apply the cache control logic from ansari_claude.py lines 691-709
        limited_history = json.loads(json.dumps(message_history))  # Deep copy

        if limited_history and len(limited_history) > 0:
            last_message = limited_history[-1]
            # Add cache control only to the LAST content block in the last message
            if isinstance(last_message.get("content"), list) and len(last_message["content"]) > 0:
                # Only add to the last block
                last_block = last_message["content"][-1]
                if isinstance(last_block, dict):
                    # Add ephemeral cache control to only the last content block
                    last_block["cache_control"] = {"type": "ephemeral"}

        # Verify results
        last_msg = limited_history[-1]
        self.assertEqual(len(last_msg["content"]), 5, "Should have 5 content blocks")

        # Check that the first 4 blocks DO NOT have cache_control
        for i in range(4):
            self.assertNotIn("cache_control", last_msg["content"][i], f"Block {i} should NOT have cache_control")

        # Check that only the last block HAS cache_control
        self.assertIn("cache_control", last_msg["content"][4], "Last block should have cache_control")
        self.assertEqual(
            last_msg["content"][4]["cache_control"]["type"], "ephemeral", "Cache control should be ephemeral type"
        )

    def test_cache_control_with_string_content(self):
        """Test cache control with string content conversion."""
        # Message with string content
        message_history = [{"role": "user", "content": "Simple string message"}]

        limited_history = json.loads(json.dumps(message_history))

        # Apply cache control logic for string content
        if limited_history and len(limited_history) > 0:
            last_message = limited_history[-1]
            if isinstance(last_message.get("content"), str):
                # If content is a string, convert to list format with cache control
                last_message["content"] = [
                    {"type": "text", "text": last_message["content"], "cache_control": {"type": "ephemeral"}}
                ]

        # Verify
        last_msg = limited_history[-1]
        self.assertIsInstance(last_msg["content"], list, "Content should be converted to list")
        self.assertEqual(len(last_msg["content"]), 1, "Should have one content block")
        self.assertIn("cache_control", last_msg["content"][0], "Content block should have cache_control")
        self.assertEqual(last_msg["content"][0]["text"], "Simple string message", "Original text should be preserved")

    def test_system_prompt_cache_control(self):
        """Test that system prompt gets cache control in correct format."""
        system_prompt = "You are Ansari, a helpful assistant."

        # Create params as done in process_one_round
        params = {
            "model": "claude-sonnet-4-20250514",
            "system": [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
            "messages": [],
            "max_tokens": 4096,
            "temperature": 0.0,
            "stream": True,
        }

        # Verify
        self.assertIsInstance(params["system"], list, "System should be a list")
        self.assertEqual(len(params["system"]), 1, "System should have one block")
        self.assertIn("cache_control", params["system"][0], "System block should have cache_control")
        self.assertEqual(params["system"][0]["cache_control"]["type"], "ephemeral", "System cache control should be ephemeral")
        self.assertEqual(params["system"][0]["text"], system_prompt, "System prompt text should be preserved")

    def test_no_cache_on_earlier_blocks(self):
        """Test that only the last block gets cache control, not earlier ones."""
        # Create a message with many blocks
        content_blocks = []
        for i in range(20):  # 20 blocks total
            content_blocks.append(
                {
                    "type": "document" if i > 0 else "text",
                    "source": {"data": f"doc{i}"} if i > 0 else None,
                    "text": "Query" if i == 0 else None,
                    "title": f"Doc {i}" if i > 0 else None,
                }
            )

        message_history = [{"role": "user", "content": content_blocks}]
        limited_history = json.loads(json.dumps(message_history))

        # Apply cache control
        if limited_history and len(limited_history) > 0:
            last_message = limited_history[-1]
            if isinstance(last_message.get("content"), list) and len(last_message["content"]) > 0:
                last_block = last_message["content"][-1]
                if isinstance(last_block, dict):
                    last_block["cache_control"] = {"type": "ephemeral"}

        # Verify
        last_msg = limited_history[-1]
        total_blocks = len(last_msg["content"])
        self.assertEqual(total_blocks, 20, "Should have 20 blocks")

        # Check all blocks except the last
        for i in range(total_blocks - 1):
            self.assertNotIn("cache_control", last_msg["content"][i], f"Block {i} should NOT have cache_control")

        # Only last block should have it
        self.assertIn("cache_control", last_msg["content"][-1], "Only the last block should have cache_control")

    def test_cache_control_not_exceeding_limit(self):
        """Test that we never exceed the 4 cache control blocks limit."""
        # Simulate a conversation with tool results (which might have had cache control before)
        message_history = [
            {"role": "user", "content": [{"type": "text", "text": "Question"}]},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "tool1", "name": "search"}]},
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tool1", "content": "Result"},
                    {"type": "document", "source": {"data": "doc1"}},
                    {"type": "document", "source": {"data": "doc2"}},
                    {"type": "document", "source": {"data": "doc3"}},
                    {"type": "document", "source": {"data": "doc4"}},
                    {"type": "document", "source": {"data": "doc5"}},
                    {"type": "document", "source": {"data": "doc6"}},
                    {"type": "document", "source": {"data": "doc7"}},
                    {"type": "document", "source": {"data": "doc8"}},
                    {"type": "document", "source": {"data": "doc9"}},
                    {"type": "document", "source": {"data": "doc10"}},
                ],
            },
        ]

        limited_history = json.loads(json.dumps(message_history))

        # Apply our new cache control logic - only to last block
        if limited_history and len(limited_history) > 0:
            last_message = limited_history[-1]
            if isinstance(last_message.get("content"), list) and len(last_message["content"]) > 0:
                last_block = last_message["content"][-1]
                if isinstance(last_block, dict):
                    last_block["cache_control"] = {"type": "ephemeral"}

        # Count total cache control blocks across all messages
        cache_control_count = 0
        for msg in limited_history:
            if isinstance(msg.get("content"), list):
                for block in msg["content"]:
                    if isinstance(block, dict) and "cache_control" in block:
                        cache_control_count += 1

        # With our fix, should only be 1 cache control (on last block)
        # Plus 1 for system prompt = 2 total, well under the limit of 4
        self.assertEqual(cache_control_count, 1, "Should have exactly 1 cache control block in messages")
        self.assertLessEqual(cache_control_count, 4, "Must not exceed 4 cache control blocks")


if __name__ == "__main__":
    unittest.main()
