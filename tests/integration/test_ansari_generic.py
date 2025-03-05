import pytest
import json
from typing import Type, List

from ansari.agents.ansari import Ansari
from ansari.agents.ansari_claude import AnsariClaude
from ansari.config import Settings
from ansari.ansari_logger import get_logger
from tests.integration.test_helpers import history_and_log_matches, IntegrationMessageLogger

# Set logging level for this module
logger = get_logger(__name__)

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
        
    def convert_message(self, msg):
        """Convert a message from database format to API format.
        
        Delegates to the real AnsariDB.convert_message method.
        """
        # Import the actual implementation from ansari_db.py
        from ansari.ansari_db import AnsariDB
        db = AnsariDB(Settings())
        return db.convert_message(msg)


class AnsariTester:
    """Generic tester class for Ansari implementations.
    
    This class provides methods to test different Ansari implementations with the same test cases.
    It can be used to ensure all implementations satisfy the common interface and behavior.
    """
    
    def __init__(self, agent_class: Type[Ansari], settings: Settings = None):
        """Initialize the tester with the Ansari implementation class to test.
        
        Args:
            agent_class: The Ansari implementation class to test
            settings: Optional settings object
        """
        self.agent_class = agent_class
        self.settings = settings or Settings()
        
    def create_agent(self, message_logger=None):
        """Create an instance of the agent with the given logger."""
        return self.agent_class(settings=self.settings, message_logger=message_logger)
    
    def test_simple_conversation(self):
        """Test a simple conversation with the agent."""
        logger.info(f"Starting simple conversation test for {self.agent_class.__name__}")
        
        message_logger = IntegrationMessageLogger()
        message_logger.reset()  # Reset before the test
        agent = self.create_agent(message_logger)
        
        # Test a simple conversation
        logger.debug("Starting simple conversation test")
        responses =  agent.process_input("What sources do you use?")
        logger.debug("Ended")
        
        # Combine all responses
        full_response = "".join(responses)
        
        # Verify we got a meaningful response
        assert len(full_response) > 50  # Response should be substantial
        
        # Verify messages were logged
        assert len(message_logger.messages) >= 2  # Should have at least user input and response
        
        # Verify message logger messages match agent history
        history_and_log_matches(agent, message_logger)
        
        # Verify messages were logged with correct roles
        assert any(msg["role"] == "user" for msg in message_logger.messages)
        assert any(msg["role"] == "assistant" for msg in message_logger.messages)
        
        return True
    
    def test_conversation_with_references(self):
        """Test a conversation with references to religious texts."""
        logger.info(f"Starting conversation with references test for {self.agent_class.__name__}")
        
        message_logger = IntegrationMessageLogger()
        message_logger.reset()  # Reset before the test
        agent = self.create_agent(message_logger)
        
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


        return True
    
    def test_multi_turn_conversation(self):
        """Test a multi-turn conversation with the agent."""
        logger.info(f"Starting multi-turn conversation test for {self.agent_class.__name__}")
        
        message_logger = IntegrationMessageLogger()
        message_logger.reset()  # Reset before the test
        agent = self.create_agent(message_logger)
        
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
        
        # Verify context retention (look for "Tawakkul" in any message content)
        has_context = False
        for msg in messages:
            content = msg["content"]
            content_str = content if isinstance(content, str) else json.dumps(content)
            if "Tawakkul" in content_str:
                has_context = True
                break
                
        assert has_context, "Context was not retained between conversation turns"
        
        return True
    
    def test_message_conversion(self):
        """Test message conversion functions for converting database messages to API/LLM format."""
        logger.info(f"Starting message conversion test for {self.agent_class.__name__}")
        
        mock_db = MockDatabase()
        
        # Process a message to generate some conversation data
        message_logger = IntegrationMessageLogger()
        message_logger.reset()  # Reset before the test
        agent = self.create_agent(message_logger)
        
        # Generate some message data
        for response in agent.process_input("What are the five pillars of Islam?"):
            pass
            
        # Store messages in mock database
        for i, msg in enumerate(message_logger.messages):
            mock_db.append_message(
                user_id=1, 
                thread_id=1, 
                role=msg["role"], 
                content=msg["content"],
                tool_name=msg["tool_name"],
                tool_details=msg["tool_details"],
                ref_list=msg["ref_list"]
            )
            
        # Test convert_message (DB format to API format)
        for i, msg in enumerate(mock_db.get_stored_messages()):
            api_msg = mock_db.convert_message(msg)
            assert "role" in api_msg, f"API message {i} missing role"
            assert "content" in api_msg, f"API message {i} missing content"
            assert api_msg["role"] == msg[0], f"API message {i} has incorrect role"
            
        # Test convert_message_llm (DB format to LLM format)
        for i, msg in enumerate(mock_db.get_stored_messages()):
            llm_msgs = mock_db.convert_message_llm(msg)
            assert len(llm_msgs) >= 1, "LLM conversion must return at least one message"
            
            for llm_msg in llm_msgs:
                assert "role" in llm_msg, f"LLM message {i} missing role"
                assert "content" in llm_msg, f"LLM message {i} missing content"
                assert llm_msg["role"] == msg[0], f"LLM message {i} has incorrect role"
                
        return True
    

    def run_all_tests(self) -> List[bool]:
        """Run all tests and return the results."""
        test_methods = [
            self.test_simple_conversation,
            self.test_conversation_with_references,
            self.test_multi_turn_conversation,
            self.test_message_conversion
        ]
        
        results = []
        for test_method in test_methods:
            try:
                result = test_method()
                results.append(result)
                logger.info(f"Test {test_method.__name__} passed for {self.agent_class.__name__}")
            except Exception as e:
                logger.error(f"Test {test_method.__name__} failed for {self.agent_class.__name__}: {str(e)}")
                results.append(False)
                
        return results


# Pytest fixtures and tests

@pytest.fixture
def settings():
    return Settings()

@pytest.fixture(autouse=True)
def setup_message_logger():
    message_logger = IntegrationMessageLogger()
    yield message_logger
    message_logger.reset()  # Clean up after each test

@pytest.mark.integration
@pytest.mark.parametrize("agent_class", [Ansari, AnsariClaude])
def test_simple_conversation_all_agents(agent_class, settings):
    """Run the simple conversation test on all agent implementations."""
    tester = AnsariTester(agent_class, settings)
    assert tester.test_simple_conversation()

@pytest.mark.integration
@pytest.mark.parametrize("agent_class", [Ansari, AnsariClaude])
def test_conversation_with_references_all_agents(agent_class, settings):
    """Run the conversation with references test on all agent implementations."""
    tester = AnsariTester(agent_class, settings)
    assert tester.test_conversation_with_references()

@pytest.mark.integration
@pytest.mark.parametrize("agent_class", [Ansari, AnsariClaude])
def test_multi_turn_conversation_all_agents(agent_class, settings):
    """Run the multi-turn conversation test on all agent implementations."""
    tester = AnsariTester(agent_class, settings)
    assert tester.test_multi_turn_conversation()

@pytest.mark.integration
@pytest.mark.parametrize("agent_class", [Ansari, AnsariClaude])
def test_message_conversion_all_agents(agent_class, settings):
    """Test message conversion functions for all agent implementations."""
    tester = AnsariTester(agent_class, settings)
    assert tester.test_message_conversion()

# Helper function to run tests directly
def run_tests_for_implementation(agent_class: Type[Ansari]):
    """Run all tests for a specific implementation."""
    settings = Settings()
    tester = AnsariTester(agent_class, settings)
    results = tester.run_all_tests()
    return all(results) 