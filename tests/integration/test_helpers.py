"""Helper functions for integration tests."""
from ansari.ansari_logger import get_logger
import json

logger = get_logger()

def history_and_log_matches(agent, message_logger):
    """Verify that the message history in the agent matches the messages in the logger.
    
    Args:
        agent: The AnsariClaude agent instance
        message_logger: The message logger instance
    
    Raises:
        AssertionError: If the messages don't match
    """
    # Convert message history to comparable format
    history_messages = []
    for msg in agent.message_history:
        # Skip system messages as they are not logged
        if msg["role"] not in ["user", "assistant"]:
            continue
            
        logger.debug(f"Processing message from history: {msg}")
        
        # For simple string content (mostly user messages)
        if isinstance(msg["content"], str):
            history_msg = {
                "role": msg["role"],
                "content": msg["content"],
                "tool_name": None,
                "tool_details": None,
                "ref_list": None
            }
            history_messages.append(history_msg)
            continue
            
        # Handle Claude's message format where content is a list of blocks
        if isinstance(msg["content"], list):
            content = msg["content"]  # Keep the original content structure
            tool_name = None
            tool_details = None
            ref_list = None
            
            # Extract tool information if present
            for block in msg["content"]:
                if block.get("type") == "tool_use" and msg["role"] == "assistant":
                    tool_name = block.get("name")
                    tool_details = block.get("input") or block.get("arguments")
                elif block.get("type") == "tool_result" and msg["role"] == "user":
                    # Reference list often follows the tool result
                    ref_blocks = [b for b in msg["content"] if b.get("type") == "document"]
                    if ref_blocks:
                        ref_list = ref_blocks
                    
            history_msg = {
                "role": msg["role"],
                "content": content,
                "tool_name": tool_name,
                "tool_details": tool_details,
                "ref_list": ref_list
            }
        else:
            # Handle plain text messages
            history_msg = {
                "role": msg["role"],
                "content": msg["content"],
                "tool_name": None,
                "tool_details": None,
                "ref_list": None
            }
            
        history_messages.append(history_msg)
    
    logger.debug(f"History messages: {history_messages}")
    logger.debug(f"Logger messages: {message_logger.messages}")
    
    # Compare the messages
    assert len(history_messages) == len(message_logger.messages), f"Message count mismatch between history ({len(history_messages)}) and logger ({len(message_logger.messages)})"
    
    for i, (hist_msg, log_msg) in enumerate(zip(history_messages, message_logger.messages)):
        # Check that roles match
        assert hist_msg["role"] == log_msg["role"], f"Message {i} role mismatch: {hist_msg['role']} vs {log_msg['role']}"
        
        # For content, we need to handle various formats
        if isinstance(hist_msg["content"], str) and isinstance(log_msg["content"], str):
            assert hist_msg["content"] == log_msg["content"], f"Message {i} content mismatch: {hist_msg['content']} vs {log_msg['content']}"
        elif isinstance(hist_msg["content"], list) and isinstance(log_msg["content"], list):
            # For list content, convert to JSON strings for deep comparison
            hist_json = json.dumps(hist_msg["content"], sort_keys=True)
            log_json = json.dumps(log_msg["content"], sort_keys=True)
            assert hist_json == log_json, f"Message {i} content structure mismatch:\nHistory: {hist_json}\nLogger: {log_json}"
        else:
            # If one is a string and one is a list, that's a problem
            assert False, f"Message {i} content type mismatch: {type(hist_msg['content'])} vs {type(log_msg['content'])}"
        
        # Compare other fields
        if hist_msg["tool_name"] != log_msg["tool_name"]:
            logger.warning(f"Tool name mismatch for message {i}: {hist_msg['tool_name']} vs {log_msg['tool_name']}")
        
        # Compare tool details if present
        if hist_msg["tool_details"] is not None and log_msg["tool_details"] is not None:
            hist_json = json.dumps(hist_msg["tool_details"], sort_keys=True)
            log_json = json.dumps(log_msg["tool_details"], sort_keys=True)
            if hist_json != log_json:
                logger.warning(f"Tool details mismatch for message {i}:\nHistory: {hist_json}\nLogger: {log_json}")
        
        # Compare reference list if present
        if hist_msg["ref_list"] is not None and log_msg["ref_list"] is not None:
            hist_json = json.dumps(hist_msg["ref_list"], sort_keys=True)
            log_json = json.dumps(log_msg["ref_list"], sort_keys=True)
            if hist_json != log_json:
                logger.warning(f"Reference list mismatch for message {i}:\nHistory: {hist_json}\nLogger: {log_json}")
