import pytest
import json
from ansari.agents.ansari_claude import AnsariClaude
from ansari.config import Settings
from ansari.ansari_db import MessageLogger, AnsariDB
from ansari.ansari_logger import get_logger
from tests.integration.test_helpers import history_and_log_matches
from tests.integration.test_ansari_generic import AnsariTester

logger = get_logger()

# Import the generic tester class to reuse test logic
from tests.integration.test_ansari_generic import IntegrationMessageLogger, MockDatabase

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

@pytest.fixture
def claude_tester(settings):
    """Create an AnsariTester configured for AnsariClaude"""
    return AnsariTester(AnsariClaude, settings)

@pytest.mark.integration
def test_simple_conversation(claude_tester):
    """Integration test for a simple conversation with Claude"""
    logger.info("Starting simple conversation integration test for AnsariClaude")
    assert claude_tester.test_simple_conversation()

@pytest.mark.integration
def test_conversation_with_references(claude_tester):
    """Integration test for a conversation that should include Quran/Hadith references"""
    logger.info("Starting conversation with references integration test for AnsariClaude")
    assert claude_tester.test_conversation_with_references()

@pytest.mark.integration
def test_multi_turn_conversation(claude_tester):
    """Integration test for a multi-turn conversation"""
    logger.info("Starting multi-turn conversation integration test for AnsariClaude")
    assert claude_tester.test_multi_turn_conversation()

# The following tests are specific to AnsariClaude implementation and test Claude-specific features

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
    def test_claude_specific_message_structure(self, settings):
        """Test Claude-specific message structure validation"""
        logger.info("Testing Claude-specific message structure")
        
        agent = AnsariClaude(settings=settings)
        
        # Validate message structure for Claude
        valid_message = {
            "role": "assistant",
            "content": [{"type": "text", "text": "Test response"}]
        }
        assert agent.validate_message(valid_message), "Valid Claude message should pass validation"
        
        # Test invalid message
        invalid_message = {
            "role": "assistant",
            "content": "Plain text content"  # Claude requires list content for assistant
        }
        assert not agent.validate_message(invalid_message), "Invalid Claude message should fail validation"
    
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
def test_run_all_claude_tests(settings):
    """Run all tests for AnsariClaude using the generic tester"""
    tester = AnsariTester(AnsariClaude, settings)
    results = tester.run_all_tests()
    assert all(results), "All tests should pass for AnsariClaude"
