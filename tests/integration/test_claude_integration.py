import pytest
import json
from ansari.agents.ansari_claude import AnsariClaude
from ansari.config import Settings
from ansari.ansari_db import MessageLogger, AnsariDB
from ansari.ansari_logger import get_logger
from tests.integration.test_helpers import history_and_log_matches

logger = get_logger()

class IntegrationMessageLogger:
    def __init__(self):
        self.messages = []
        
    def log(self, role: str, content: str, tool_name: str = None, tool_details: dict = None, ref_list: list = None):
        logger.debug(f"Logging message: role={role}, content={content}, tool_name={tool_name}")
        
        # Ensure content is properly structured
        # For assistant messages with tool use, we need to include both the content and tool information
        if role == "assistant" and tool_name and tool_details:
            # Make sure content is a list
            if not isinstance(content, list):
                content = [{"type": "text", "text": content}]
                
            # Create a tool_use block and add it to content
            tool_use_block = {
                "type": "tool_use",
                "id": tool_details.get("id", "unknown_id"),
                "name": tool_name,
                "input": tool_details.get("input", {})
            }
            
            # Make a copy of the content to avoid modifying the original
            full_content = content.copy()
            # Add the tool_use block
            full_content.append(tool_use_block)
            
            # Store the full content with tool_use included
            content = full_content
        
        # For user messages with tool results and reference lists
        elif role == "user" and isinstance(content, list) and ref_list:
            # Make sure we include the reference list items in the content
            full_content = content.copy()
            
            # Append reference list items to content
            for ref_item in ref_list:
                if ref_item not in full_content:
                    full_content.append(ref_item)
            
            # Update content to include references
            content = full_content
            
        self.messages.append({
            "role": role,
            "content": content,
            "tool_name": tool_name,
            "tool_details": tool_details,
            "ref_list": ref_list
        })

# Mock database implementation for testing reconstruction
class MockDatabase:
    def __init__(self):
        self.stored_messages = []
        
    def append_message(self, user_id, thread_id, role, content, tool_name=None, tool_details=None, ref_list=None):
        """Store message in mock database"""
        # Serialize complex structures like a real database would
        serialized_content = json.dumps(content) if isinstance(content, (dict, list)) else content
        serialized_tool_details = json.dumps(tool_details) if tool_details is not None else None
        serialized_ref_list = json.dumps(ref_list) if ref_list is not None else None
        
        self.stored_messages.append((
            role,
            serialized_content,
            tool_name,
            serialized_tool_details,
            serialized_ref_list
        ))
        
    def get_stored_messages(self):
        """Return all stored messages"""
        return self.stored_messages
        
    def convert_message_llm(self, msg):
        """Replicate the AnsariDB.convert_message_llm method"""
        # Import the actual implementation from ansari_db.py
        from ansari.ansari_db import AnsariDB
        db = AnsariDB(Settings())
        return db.convert_message_llm(msg)

@pytest.fixture
def settings():
    settings = Settings()
    return settings

@pytest.fixture
def message_logger():
    return IntegrationMessageLogger()

@pytest.fixture
def mock_db():
    return MockDatabase()

@pytest.mark.integration
def test_simple_conversation(settings, message_logger):
    """Integration test for a simple conversation with Claude"""
    logger.info("Starting simple conversation integration test")
    
    agent = AnsariClaude(settings=settings, message_logger=message_logger)
    
    # Test a simple conversation
    responses = []
    for response in agent.process_input("What sources do you use?"):
        responses.append(response)
    
    # Combine all responses
    full_response = "".join(responses)
    
    # Verify we got a meaningful response
    assert len(full_response) > 50  # Response should be substantial
    
    # Verify messages were logged
    assert len(message_logger.messages) >= 2  # Should have at least user input and Claude response
    
    # Verify message logger messages match agent history
    history_and_log_matches(agent, message_logger)
    
    # Verify messages were logged
    assert any(msg["role"] == "user" for msg in message_logger.messages)
    assert any(msg["role"] == "assistant" for msg in message_logger.messages)

@pytest.mark.integration
def test_conversation_with_references(settings, message_logger):
    """Integration test for a conversation that should include Quran/Hadith references"""
    logger.info("Starting conversation with references integration test")
    
    agent = AnsariClaude(settings=settings, message_logger=message_logger)
    
    # Test a query that should trigger reference lookups
    responses = []
    for response in agent.process_input("Are corals mentioned in the Quran?"):
        responses.append(response)
    
    # Combine all responses
    full_response = "".join(responses)
    
    # Verify we got a meaningful response
    assert len(full_response) > 100  # Response should be substantial
    
    # Verify messages were logged with references
    assert len(message_logger.messages) >= 2
    
    # Verify message logger messages match agent history
    history_and_log_matches(agent, message_logger)
    
    # Check for references in the response
    assert any("ref_list" in msg and msg["ref_list"] for msg in message_logger.messages), "No references found in the response"

@pytest.mark.integration
def test_multi_turn_conversation(settings, message_logger):
    """Integration test for a multi-turn conversation"""
    logger.info("Starting multi-turn conversation integration test")
    
    agent = AnsariClaude(settings=settings, message_logger=message_logger)
    
    # First turn
    responses1 = []
    for response in agent.process_input("What is the concept of Tawakkul in Islam?"):
        responses1.append(response)
    full_response1 = "".join(responses1)
    assert len(full_response1) > 50
    
    # Second turn - follow-up question
    responses2 = []
    for response in agent.process_input("How can one practically apply this concept in daily life?"):
        responses2.append(response)
    full_response2 = "".join(responses2)
    assert len(full_response2) > 50
    
    # Verify conversation flow
    messages = message_logger.messages
    assert len(messages) >= 4  # Should have at least 4 messages (2 user, 2 assistant)
    
    # Verify message logger messages match agent history
    history_and_log_matches(agent, message_logger)
    
    # Verify context retention
    assert any("Tawakkul" in msg["content"] for msg in messages), "Context should be retained"


class TestMessageReconstruction:
    """Tests that focus specifically on message reconstruction between agent and database"""
    
    @pytest.mark.integration
    def test_full_reconstruction_cycle(self, settings, mock_db):
        """Test the full cycle: Message creation → Database storage → Retrieval → Reconstruction"""
        logger.info("Testing full message reconstruction cycle")
        
        # Create logger that uses our mock database
        message_logger = MessageLogger(mock_db, 1, 1)
        
        # Create the agent
        agent = AnsariClaude(settings=settings, message_logger=message_logger)
        
        # Process a query likely to use tools
        for _ in agent.process_input("What does Surah Al-Baqarah say about fasting?"):
            pass
            
        # Verify we have messages in the agent's history
        assert len(agent.message_history) > 0, "No messages in agent history"
        
        # Get the stored messages from the mock DB
        stored_messages = mock_db.get_stored_messages()
        assert len(stored_messages) > 0, "No messages stored in mock database"
        
        # Reconstruct messages using the convert_message_llm method
        reconstructed_messages = []
        for msg in stored_messages:
            reconstructed_msgs = mock_db.convert_message_llm(msg)
            reconstructed_messages.extend(reconstructed_msgs)
            
        # Verify reconstructed messages match agent's history in structure
        assert len(reconstructed_messages) > 0, "No messages were reconstructed"
        
        # Check each message for structural validity
        for msg in reconstructed_messages:
            assert "role" in msg, "Reconstructed message missing role"
            assert "content" in msg, "Reconstructed message missing content"
            
            # Assistant messages should have structured content
            if msg["role"] == "assistant":
                assert isinstance(msg["content"], list), "Assistant message content should be a list"
                for block in msg["content"]:
                    assert isinstance(block, dict), "Assistant message content block should be a dict"
                    assert "type" in block, "Assistant message content block missing type"
    
    @pytest.mark.integration
    def test_edge_cases(self, settings):
        """Test edge cases for message reconstruction"""
        logger.info("Testing message reconstruction edge cases")
        
        mock_db = MockDatabase()
        
        # Test Case 1: Empty content
        empty_content_msg = ("assistant", json.dumps([{"type": "text", "text": ""}]), None, None, None)
        reconstructed = mock_db.convert_message_llm(empty_content_msg)
        assert len(reconstructed) == 1, "Should have one reconstructed message"
        assert reconstructed[0]["role"] == "assistant", "Role should be preserved"
        assert isinstance(reconstructed[0]["content"], list), "Content should be a list"
        
        # Test Case 2: Only tool use with no text content
        tool_only_msg = (
            "assistant", 
            "[]",  # Empty content array
            "search_hadith", 
            json.dumps({"id": "123", "input": {"query": "test"}}), 
            None
        )
        reconstructed = mock_db.convert_message_llm(tool_only_msg)
        assert len(reconstructed) == 1, "Should have one reconstructed message"
        assert reconstructed[0]["role"] == "assistant", "Role should be preserved"
        assert isinstance(reconstructed[0]["content"], list), "Content should be a list"
        assert any(block.get("type") == "tool_use" for block in reconstructed[0]["content"]), "Should have tool use block"
        
        # Test Case 3: Message with tool results
        tool_result_msg = (
            "user",
            json.dumps([{"type": "tool_result", "tool_use_id": "123", "content": "Test result"}]),
            "search_hadith",
            json.dumps({"id": "123"}),
            json.dumps([{"type": "document", "document": {"title": "Test Doc", "content": "Test content"}}])
        )
        reconstructed = mock_db.convert_message_llm(tool_result_msg)
        assert len(reconstructed) == 1, "Should have one reconstructed message"
        assert reconstructed[0]["role"] == "user", "Role should be preserved"
        assert isinstance(reconstructed[0]["content"], list), "Content should be a list"
        assert any(block.get("type") == "tool_result" for block in reconstructed[0]["content"]), "Should have tool result block"
        assert any(block.get("type") == "document" for block in reconstructed[0]["content"]), "Should have document block"
        
    @pytest.mark.integration
    def test_malformed_messages(self, settings):
        """Test reconstruction of malformed messages"""
        logger.info("Testing reconstruction of malformed messages")
        
        mock_db = MockDatabase()
        
        # Test Case 1: Malformed JSON in content
        malformed_content_msg = ("assistant", "{broken json", None, None, None)
        reconstructed = mock_db.convert_message_llm(malformed_content_msg)
        assert len(reconstructed) == 1, "Should have one reconstructed message"
        assert reconstructed[0]["role"] == "assistant", "Role should be preserved"
        
        # Test Case 2: Malformed JSON in tool details
        malformed_tool_msg = (
            "assistant", 
            json.dumps([{"type": "text", "text": "Test"}]), 
            "search_hadith", 
            "{broken json", 
            None
        )
        reconstructed = mock_db.convert_message_llm(malformed_tool_msg)
        assert len(reconstructed) == 1, "Should have one reconstructed message"
        assert reconstructed[0]["role"] == "assistant", "Role should be preserved"
        
        # Test Case 3: Malformed JSON in reference list
        malformed_ref_msg = (
            "user",
            json.dumps([{"type": "tool_result", "tool_use_id": "123", "content": "Test result"}]),
            "search_hadith",
            json.dumps({"id": "123"}),
            "{broken json"
        )
        reconstructed = mock_db.convert_message_llm(malformed_ref_msg)
        assert len(reconstructed) == 1, "Should have one reconstructed message"
        assert reconstructed[0]["role"] == "user", "Role should be preserved"

    @pytest.mark.integration
    def test_message_structure_consistency(self, settings):
        """Test that messages maintain consistent structure expected by the system"""
        logger.info("Testing message structure consistency")
        
        mock_db = MockDatabase()
        
        # 1. Test assistant message format
        assistant_msg = (
            "assistant",
            json.dumps([{"type": "text", "text": "This is a test response"}]),
            None,
            None,
            None
        )
        reconstructed = mock_db.convert_message_llm(assistant_msg)
        assert len(reconstructed) == 1, "Should have one reconstructed message"
        assert reconstructed[0]["role"] == "assistant", "Role should be preserved"
        
        # Assistant messages should always have list content with typed blocks
        content = reconstructed[0]["content"]
        assert isinstance(content, list), "Assistant content should be a list"
        for block in content:
            assert isinstance(block, dict), "Content blocks should be dictionaries"
            assert "type" in block, "Content blocks should have a type field"
            if block["type"] == "text":
                assert "text" in block, "Text blocks should have a text field"
        
        # 2. Test assistant message with tool use
        assistant_tool_msg = (
            "assistant",
            json.dumps([{"type": "text", "text": "Let me search for that"}]),
            "search_hadith",
            json.dumps({"id": "tool123", "input": {"query": "test query"}}),
            None
        )
        reconstructed = mock_db.convert_message_llm(assistant_tool_msg)
        assert len(reconstructed) == 1, "Should have one reconstructed message"
        
        # Tool use should be properly structured
        content = reconstructed[0]["content"]
        tool_blocks = [b for b in content if b.get("type") == "tool_use"]
        assert len(tool_blocks) == 1, "Should have one tool use block"
        tool_block = tool_blocks[0]
        assert "id" in tool_block, "Tool use block should have an id"
        assert "name" in tool_block, "Tool use block should have a name"
        assert "input" in tool_block, "Tool use block should have input"
        
        # 3. Test user message with tool results and references
        user_tool_result_msg = (
            "user",
            json.dumps([
                {"type": "tool_result", "tool_use_id": "tool123", "content": "Tool result"}
            ]),
            "search_hadith",
            json.dumps({"id": "tool123"}),
            json.dumps([
                {"type": "document", "document": {"title": "Doc 1", "content": "Content 1"}},
                {"type": "document", "document": {"title": "Doc 2", "content": "Content 2"}}
            ])
        )
        reconstructed = mock_db.convert_message_llm(user_tool_result_msg)
        assert len(reconstructed) == 1, "Should have one reconstructed message"
        
        # Tool result should have tool_use_id and content
        content = reconstructed[0]["content"]
        tool_result_blocks = [b for b in content if b.get("type") == "tool_result"]
        assert len(tool_result_blocks) > 0, "Should have tool result blocks"
        for block in tool_result_blocks:
            assert "tool_use_id" in block, "Tool result block should have tool_use_id"
            assert "content" in block, "Tool result block should have content"
            
        # References should be included
        document_blocks = [b for b in content if b.get("type") == "document"]
        assert len(document_blocks) == 2, "Should have document blocks"
        for block in document_blocks:
            assert "document" in block, "Document block should have document field"
            assert "title" in block["document"], "Document should have title"
            assert "content" in block["document"], "Document should have content"
            
        # 4. Test message conversion from string to proper structure
        simple_assistant_msg = (
            "assistant",
            "Simple text response",  # Plain string, not JSON
            None,
            None,
            None
        )
        reconstructed = mock_db.convert_message_llm(simple_assistant_msg)
        assert len(reconstructed) == 1, "Should have one reconstructed message"
        content = reconstructed[0]["content"]
        assert isinstance(content, list), "Content should be converted to list format"
        assert len(content) == 1, "Should have one content block"
        assert content[0]["type"] == "text", "Content should be converted to text block"
        assert "text" in content[0], "Text block should have text field"
