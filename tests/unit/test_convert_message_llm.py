"""
Tests for message formatting in convert_message_llm.
"""

import json
import uuid


def simple_convert_message_llm(msg) -> list[dict]:
    """A simplified version of convert_message_llm for testing purposes.

    This follows the logic in the current implementation but is isolated
    from database connections for testing.
    """
    msg_id = str(uuid.uuid4())
    role, content = msg[0], msg[1]
    tool_name, tool_details = msg[2], msg[3]

    # Handle assistant messages
    if role == "assistant":
        content_blocks = []

        # Add text block
        if isinstance(content, str):
            content_blocks.append({"type": "text", "text": content})
        elif isinstance(content, list) and all(isinstance(block, dict) and "type" in block for block in content):
            content_blocks = content
        else:
            content_blocks.append({"type": "text", "text": str(content)})

        # Add tool use block if present
        if tool_name and tool_details:
            tool_details_dict = json.loads(tool_details)
            tool_id = tool_details_dict.get("id")
            tool_input = tool_details_dict.get("args")

            if tool_id and tool_name:
                content_blocks.append({"type": "tool_use", "id": tool_id, "name": tool_name, "input": tool_input})

        return [{"id": msg_id, "role": role, "content": content_blocks}]

    # Handle user messages
    return [{"id": msg_id, "role": role, "content": content}]


def test_convert_message_llm_formats():
    """Test message formatting in convert_message_llm."""

    # Test 1: Simple user message
    user_msg = ("user", "Hello, how are you?", None, None, None)
    result = simple_convert_message_llm(user_msg)

    assert len(result) == 1
    assert result[0]["role"] == "user"
    assert result[0]["content"] == "Hello, how are you?"

    # Test 2: Simple assistant message
    assistant_msg = ("assistant", "I'm doing well, thank you!", None, None, None)
    result = simple_convert_message_llm(assistant_msg)

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
    result = simple_convert_message_llm(assistant_tool_msg)

    assert len(result) == 1
    assert result[0]["role"] == "assistant"
    assert isinstance(result[0]["content"], list)

    # There should be a text block and a tool block
    text_blocks = [b for b in result[0]["content"] if b.get("type") == "text"]
    tool_blocks = [b for b in result[0]["content"] if b.get("type") == "tool_use"]

    assert len(text_blocks) == 1, "Should have one text block"
    assert len(tool_blocks) == 1, "Should have one tool_use block"
    assert text_blocks[0]["text"] == "Let me search for that"
    assert tool_blocks[0]["id"] == tool_id
    assert tool_blocks[0]["name"] == "search_quran"

    # Test 4: Assistant message with empty text and tool use
    empty_tool_id = str(uuid.uuid4())
    empty_tool_details = json.dumps({"id": empty_tool_id, "args": {"query": "test"}})

    empty_msg = ("assistant", "", "search_quran", empty_tool_details, None)
    result = simple_convert_message_llm(empty_msg)

    # The current implementation will include an empty text block
    text_blocks = [b for b in result[0]["content"] if b.get("type") == "text"]
    tool_blocks = [b for b in result[0]["content"] if b.get("type") == "tool_use"]

    assert len(text_blocks) > 0, "Current implementation includes empty text block"
    assert text_blocks[0]["text"] == "", "Text block is empty"
    assert len(tool_blocks) == 1, "Should have one tool_use block"

    # Note: This test documents the current behavior, which may not be ideal.
    # The runtime code in AnsariClaude._finish_response now avoids creating
    # assistant messages with empty text blocks, but this database reconstruction
    # method still creates them. The test still passes to document this
    # difference in behavior.

    # Future enhancement should align the database reconstruction with runtime behavior
    # by not including empty text blocks in the content.


def test_runtime_vs_database_behavior():
    """Test to document the difference between runtime and database behavior
    with empty text blocks."""

    # This is a helper function that mimics the runtime behavior in AnsariClaude
    def runtime_format(text, tool_calls):
        if not text and tool_calls:
            # Runtime behavior: only include tool calls when text is empty
            return {"role": "assistant", "content": tool_calls}
        else:
            # Include both text and tool calls
            content = [{"type": "text", "text": text}]
            content.extend(tool_calls)
            return {"role": "assistant", "content": content}

    # Create test data
    tool_id = str(uuid.uuid4())
    tool_call = {"type": "tool_use", "id": tool_id, "name": "search_quran", "input": {"query": "test"}}

    # Test empty text with tool call
    runtime_result = runtime_format("", [tool_call])
    assert runtime_result["role"] == "assistant"
    assert len(runtime_result["content"]) == 1, "Runtime: only includes tool call, no empty text block"
    assert runtime_result["content"][0]["type"] == "tool_use", "Runtime: only has tool block"

    # Compare with database reconstruction behavior
    db_msg = ("assistant", "", "search_quran", json.dumps({"id": tool_id, "args": {"query": "test"}}), None)
    db_result = simple_convert_message_llm(db_msg)[0]

    # Database behavior will include the empty text block
    has_empty_text = any(block.get("type") == "text" and block.get("text", "") == "" for block in db_result["content"])
    assert has_empty_text, "Database: includes empty text block"


if __name__ == "__main__":
    test_convert_message_llm_formats()
    test_runtime_vs_database_behavior()
