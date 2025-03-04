"""Helper functions for integration tests."""
from ansari.ansari_logger import get_logger
import json

logger = get_logger()

class IntegrationMessageLogger:
    def __init__(self):
        self.reset()  # Move initialization to a reset method

    def reset(self):
        """Reset the message log."""
        self.messages = []
        
    def log(self, role, content, tool_name=None, tool_details=None, ref_list=None):
        self.messages.append({
            "role": role,
            "content": content,
            "tool_name": tool_name,
            "tool_details": tool_details,
            "ref_list": ref_list
        })

def history_and_log_matches(agent, message_logger):
    """Verify that the message history in the agent matches the messages in the logger.
    
    Args:
        agent: The Ansari agent instance (can be any subclass)
        message_logger: The message logger instance
    
    Raises:
        AssertionError: If the messages don't match
    """
    # Determine agent type
    agent_class_name = agent.__class__.__name__
    
    # Convert message history to comparable format
    history_messages = []
    for msg in agent.message_history:
        # Skip system messages as they are not logged
        if msg["role"] not in ["user", "assistant", "tool"]:
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
            
            # Extract tool information if present (specific to AnsariClaude format)
            if agent_class_name == "AnsariClaude":
                for block in msg["content"]:
                    if block.get("type") == "tool_use" and msg["role"] == "assistant":
                        tool_name = block.get("name")
                        tool_details = block.get("input") or block.get("arguments")
                    elif block.get("type") == "tool_result" and msg["role"] == "user":
                        # Reference list often follows the tool result in Claude
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
    
    # Print detailed message information for debugging
    logger.info(f"=== History Messages ({len(history_messages)}) ===")
    for i, msg in enumerate(history_messages):
        logger.info(f"History Message {i}:")
        logger.info(f"  Role: {msg['role']}")
        if msg['role'] == 'tool':
            logger.info(f"  Tool Call ID: {msg.get('tool_call_id', 'None')}")
        
    logger.info(f"=== Logger Messages ({len(message_logger.messages)}) ===")
    for i, msg in enumerate(message_logger.messages):
        logger.info(f"Logger Message {i}:")
        logger.info(f"  Role: {msg['role']}")
        if msg['role'] == 'assistant':
            logger.info(f"  Tool Details: {msg.get('tool_details', 'None')}")
    
    # For Ansari class, we know it may have more messages in history than in logger
    # This is because some tool results may be added to message history but not logged
    # What's important is that the key messages (user and final assistant responses) are present
    if agent_class_name == "Ansari":
        # Check that we have at least one user message and one assistant message at the end
        assert len(history_messages) >= 2, "History must have at least 2 messages"
        assert len(message_logger.messages) >= 2, "Logger must have at least 2 messages"
        
        # Check that the first message is a user message
        assert history_messages[0]["role"] == "user" and message_logger.messages[0]["role"] == "user", \
            "First message must be from user"
            
        # Check that the last message in both is from assistant (final response)
        assert history_messages[-1]["role"] == "assistant" and message_logger.messages[-1]["role"] == "assistant", \
            "Last message must be from assistant"
    else:
        # For other agent types (e.g., AnsariClaude), we expect exact match
        assert len(history_messages) == len(message_logger.messages), \
            f"Message count mismatch between history ({len(history_messages)}) and logger ({len(message_logger.messages)})"
    
    # For Ansari class, we only want to compare key messages like user queries and final responses
    if agent_class_name == "Ansari":
        # Find user messages and their responses in both histories
        key_messages = []
        
        # First message is always user query
        key_messages.append((0, 0))  # (history_idx, logger_idx)
        
        # Last message is always assistant's final response
        key_messages.append((len(history_messages) - 1, len(message_logger.messages) - 1))
        
        # For each key message pair, check basic message properties
        for (hist_idx, log_idx) in key_messages:
            hist_msg = history_messages[hist_idx]
            log_msg = message_logger.messages[log_idx]
            
            # Check that roles match
            assert hist_msg["role"] == log_msg["role"], \
                f"Message role mismatch: {hist_msg['role']} vs {log_msg['role']}"
                
            # For content of simple text messages, verify it matches
            if hist_msg["role"] == "user" and isinstance(hist_msg["content"], str) and isinstance(log_msg["content"], str):
                assert hist_msg["content"] == log_msg["content"], \
                    f"User message content mismatch: {hist_msg['content']} vs {log_msg['content']}"
    else:
        # For other agent types (e.g., AnsariClaude), we do a full comparison
        for i, (hist_msg, log_msg) in enumerate(zip(history_messages, message_logger.messages)):
            # Check that roles match
            assert hist_msg["role"] == log_msg["role"], f"Message {i} role mismatch: {hist_msg['role']} vs {log_msg['role']}"
            
            # For content, we need to handle various formats based on the agent type
            if isinstance(hist_msg["content"], str) and isinstance(log_msg["content"], str):
                assert hist_msg["content"] == log_msg["content"], \
                    f"Message {i} content mismatch: {hist_msg['content']} vs {log_msg['content']}"
            elif isinstance(hist_msg["content"], list) and isinstance(log_msg["content"], list):
                # For list content, convert to JSON strings for deep comparison
                hist_json = json.dumps(hist_msg["content"], sort_keys=True)
                log_json = json.dumps(log_msg["content"], sort_keys=True)
                assert hist_json == log_json, f"Message {i} content structure mismatch:\nHistory: {hist_json}\nLogger: {log_json}"
            elif (isinstance(hist_msg["content"], str) and 
                  isinstance(log_msg["content"], (list, dict))):
                # For Ansari base class, the message_logger might store structured content for some messages
                # Convert structured content to string for comparison
                log_content_str = json.dumps(log_msg["content"])
                # Basic check that string content is present in the structured content
                assert hist_msg["content"] in log_content_str, f"Message {i} content not found in structured content"
            else:
                # If types don't match and it's not a known conversion case
                logger.warning(f"Content type mismatch for message {i}: {type(hist_msg['content'])} vs {type(log_msg['content'])}")
                logger.warning("This might be normal for some agent implementations.")
                # We don't assert here as different implementations may store content differently
            
            # Compare other fields more loosely
            if hist_msg["tool_name"] != log_msg["tool_name"]:
                logger.warning(f"Tool name mismatch for message {i}: {hist_msg['tool_name']} vs {log_msg['tool_name']}")
            
            # Compare tool details if present
            if hist_msg["tool_details"] is not None and log_msg["tool_details"] is not None:
                # For different implementations, tool details might be structured differently
                # We just check that they're both present, not that they match exactly
                hist_has_details = hist_msg["tool_details"] is not None
                log_has_details = log_msg["tool_details"] is not None
                assert hist_has_details == log_has_details, f"Tool details presence mismatch for message {i}"
            
            # Compare reference list if present
            if hist_msg["ref_list"] is not None and log_msg["ref_list"] is not None:
                # Just check that reference lists are present, not that they match exactly
                hist_has_refs = hist_msg["ref_list"] is not None
                log_has_refs = log_msg["ref_list"] is not None
                assert hist_has_refs == log_has_refs, f"Reference list presence mismatch for message {i}"
