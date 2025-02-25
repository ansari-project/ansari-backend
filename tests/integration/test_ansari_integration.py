import pytest
import json

from ansari.agents.ansari import Ansari
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
        
        # Store message with all details
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
    """Integration test for a simple conversation with Ansari"""
    logger.info("Starting simple conversation integration test")
    
    agent = Ansari(settings=settings, message_logger=message_logger)
    
    # Test a simple conversation
    responses = []
    for response in agent.process_input("What sources do you use?"):
        responses.append(response)
    
    # Combine all responses
    full_response = "".join(responses)
    
    # Verify we got a meaningful response
    assert len(full_response) > 50  # Response should be substantial
    
    # Verify messages were logged
    assert len(message_logger.messages) >= 2  # Should have at least user input and Ansari response
    
    # Verify message logger messages match agent history
    history_and_log_matches(agent, message_logger)
    
    # Verify messages were logged
    assert any(msg["role"] == "user" for msg in message_logger.messages)
    assert any(msg["role"] == "assistant" for msg in message_logger.messages)

@pytest.mark.integration
def test_conversation_with_references(settings, message_logger):
    """Integration test for a conversation that should include Quran/Hadith references"""
    logger.info("Starting conversation with references integration test")
    
    agent = Ansari(settings=settings, message_logger=message_logger)
    
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
    assert any("tool_name" in msg and msg["tool_name"] == "search_quran" for msg in message_logger.messages), "No Quran references found in the response"

@pytest.mark.integration
def test_multi_turn_conversation(settings, message_logger):
    """Integration test for a multi-turn conversation"""
    logger.info("Starting multi-turn conversation integration test")
    
    agent = Ansari(settings=settings, message_logger=message_logger)
    
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
    assert any("Tawakkul" in str(msg["content"]) for msg in messages), "Context should be retained"


class TestMessageReconstruction:
    """Tests that focus specifically on message reconstruction between agent and database"""
    
    @pytest.mark.integration
    def test_full_reconstruction_cycle(self, settings, mock_db):
        """Test the full cycle: Message creation → Database storage → Retrieval → Reconstruction"""
        logger.info("Testing full message reconstruction cycle")
        
        # Create logger that uses our mock database
        message_logger = MessageLogger(mock_db, 1, 1)
        
        # Create the agent
        agent = Ansari(settings=settings, message_logger=message_logger)
        
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
    
    @pytest.mark.integration
    def test_edge_cases(self, settings):
        """Test edge cases for message reconstruction"""
        logger.info("Testing message reconstruction edge cases")
        
        mock_db = MockDatabase()
        
        # Test Case 1: Plain text message
        plain_text_msg = ("assistant", "Simple text response", None, None, None)
        reconstructed = mock_db.convert_message_llm(plain_text_msg)
        assert len(reconstructed) == 1, "Should have one reconstructed message"
        assert reconstructed[0]["role"] == "assistant", "Role should be preserved"
        assert reconstructed[0]["content"] == "Simple text response", "Content should be preserved as is"
        
        # Test Case 2: Tool call message
        tool_msg = (
            "assistant", 
            "Let me search for that", 
            "search_quran", 
            json.dumps({"id": "123", "input": {"query": "test"}}), 
            None
        )
        reconstructed = mock_db.convert_message_llm(tool_msg)
        assert len(reconstructed) == 1, "Should have one reconstructed message"
        assert reconstructed[0]["role"] == "assistant", "Role should be preserved"
        assert isinstance(reconstructed[0]["content"], str), "Content should be a string for base Ansari"
        
        # Test Case 3: Message with tool results
        tool_result_msg = (
            "tool",
            "Tool result text",
            "search_quran",
            json.dumps({"id": "123", "internal_message": "Internal message", "tool_message": "Tool message"}),
            None
        )
        reconstructed = mock_db.convert_message_llm(tool_result_msg)
        assert len(reconstructed) == 1, "Should have one reconstructed message"
        assert reconstructed[0]["role"] == "tool", "Role should be preserved"
        assert isinstance(reconstructed[0]["content"], str), "Content should be a string" 