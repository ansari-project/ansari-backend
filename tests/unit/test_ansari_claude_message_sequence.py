import json
import uuid
import sys
import os
from unittest.mock import MagicMock, patch

# Add the src directory to the path so we can import the modules
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
sys.path.insert(0, src_path)

from ansari.agents.ansari_claude import AnsariClaude
from ansari.config import Settings
from ansari.ansari_db import MessageLogger


def test_message_sequence_with_tool_use():
    """
    Test a complete message sequence with tool use and tool result.
    
    This tests the following sequence:
    1. Assistant message with tool_use
    2. User message with tool_result
    3. Assistant explanation
    4. Simple user message
    """
    # Create a mock settings object
    settings = MagicMock(spec=Settings)
    settings.ANTHROPIC_MODEL = "claude-3-opus-20240229"
    settings.diskcache_dir = "/tmp/diskcache"
    settings.MAX_FAILURES = 3
    
    # Create a mock message logger
    message_logger = MagicMock(spec=MessageLogger)
    
    # Create a mocked AnsariClaude instance with initial tools setup
    with patch('anthropic.Anthropic'), patch.object(AnsariClaude, '__init__', return_value=None):
        claude = AnsariClaude.__new__(AnsariClaude)
        claude.settings = settings
        claude.message_logger = message_logger
        
        # Set needed attributes that would normally be set in __init__
        claude.tools = []
        claude.tool_name_to_instance = {}
        claude.citations = []
        claude.message_history = []
        claude.client = MagicMock()
        
        # Create a unique tool ID
        tool_id = str(uuid.uuid4())
        
        # Setup a message sequence with tool use and tool result
        claude.message_history = [
            # 1. Assistant message with tool_use
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Let me search for that information."},
                    {
                        "type": "tool_use",
                        "id": tool_id,
                        "name": "search_quran",
                        "input": {"query": "mercy in quran"}
                    }
                ]
            },
            
            # 2. User message with tool_result
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": "Found 114 verses mentioning mercy."
                    }
                ]
            },
            
            # 3. Assistant explanation
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "I found that the concept of mercy appears frequently in the Quran."}
                ]
            },
            
            # 4. Simple user message
            {
                "role": "user",
                "content": "Can you tell me more about that?"
            }
        ]
        
        # Process the message history
        # Mock the API response to avoid actual API calls
        mock_response = MagicMock()
        claude.client.messages.create.return_value = mock_response
        claude.process_one_round = MagicMock(return_value=[])
        
        # Run the message processing
        # Make a copy of the history for comparison
        original_history = [msg.copy() for msg in claude.message_history]
        
        # Process the message history
        list(claude.process_message_history(use_tool=False, stream=False))
        
        # Check that the message history structure was preserved
        processed_history = claude.message_history
        
        # Compare the content of each message to ensure the structure is maintained
        for i, (orig, processed) in enumerate(zip(original_history, processed_history)):
            # Check that roles match
            assert orig["role"] == processed["role"], f"Role mismatch at message {i}"
            
            # For assistant messages, ensure content remains a list of blocks
            if orig["role"] == "assistant":
                assert isinstance(processed["content"], list), f"Assistant content should be a list at message {i}"
                
                # Check for tool_use blocks
                orig_tool_blocks = [b for b in orig["content"] if b.get("type") == "tool_use"]
                processed_tool_blocks = [b for b in processed["content"] if b.get("type") == "tool_use"]
                
                assert len(orig_tool_blocks) == len(processed_tool_blocks), \
                    f"Tool use blocks count mismatch at message {i}"
                
                # If there are tool blocks, check that IDs are preserved
                if orig_tool_blocks:
                    assert orig_tool_blocks[0]["id"] == processed_tool_blocks[0]["id"], \
                        f"Tool use ID mismatch at message {i}"
            
            # For user messages with tool_result, ensure structure is maintained
            if orig["role"] == "user" and isinstance(orig["content"], list):
                # Check that content is still a list
                assert isinstance(processed["content"], list), \
                    f"User tool_result content should remain a list at message {i}"
                
                # Check for tool_result blocks
                orig_result_blocks = [b for b in orig["content"] if b.get("type") == "tool_result"]
                processed_result_blocks = [b for b in processed["content"] if b.get("type") == "tool_result"]
                
                assert len(orig_result_blocks) == len(processed_result_blocks), \
                    f"Tool result blocks count mismatch at message {i}"
                
                # If there are result blocks, check that IDs are preserved
                if orig_result_blocks:
                    assert orig_result_blocks[0]["tool_use_id"] == processed_result_blocks[0]["tool_use_id"], \
                        f"Tool result ID mismatch at message {i}"
        
        print("All assertions passed - message sequence with tool use/result is correctly processed!")


if __name__ == "__main__":
    test_message_sequence_with_tool_use()