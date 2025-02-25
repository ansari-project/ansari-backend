import pytest
import json

from ansari.agents.ansari import Ansari
from ansari.config import Settings
from ansari.ansari_db import MessageLogger, AnsariDB
from ansari.ansari_logger import get_logger
from tests.integration.test_helpers import history_and_log_matches
from tests.integration.test_ansari_generic import AnsariTester, IntegrationMessageLogger, MockDatabase

logger = get_logger()

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
def ansari_tester(settings):
    """Create an AnsariTester configured for base Ansari"""
    return AnsariTester(Ansari, settings)

@pytest.mark.integration
def test_simple_conversation(ansari_tester):
    """Integration test for a simple conversation with Ansari"""
    logger.info("Starting simple conversation integration test for Ansari")
    assert ansari_tester.test_simple_conversation()

@pytest.mark.integration
def test_conversation_with_references(ansari_tester):
    """Integration test for a conversation that should include Quran/Hadith references"""
    logger.info("Starting conversation with references integration test for Ansari")
    assert ansari_tester.test_conversation_with_references()

@pytest.mark.integration
def test_multi_turn_conversation(ansari_tester):
    """Integration test for a multi-turn conversation"""
    logger.info("Starting multi-turn conversation integration test for Ansari")
    assert ansari_tester.test_multi_turn_conversation()


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

@pytest.mark.integration
def test_run_all_ansari_tests(settings):
    """Run all tests for base Ansari using the generic tester"""
    tester = AnsariTester(Ansari, settings)
    results = tester.run_all_tests()
    assert all(results), "All tests should pass for base Ansari" 