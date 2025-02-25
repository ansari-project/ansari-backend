import pytest
import json
from typing import Type, List, Callable

from ansari.agents.ansari import Ansari
from ansari.agents.ansari_claude import AnsariClaude
from ansari.config import Settings
from ansari.ansari_db import MessageLogger
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
        agent = self.create_agent(message_logger)
        
        # Test a simple conversation
        responses = []
        for response in agent.process_input("What sources do you use?"):
            responses.append(response)
        
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
        
        # Check for references or tool usage in the response (implementation-specific)
        has_references = False
        for msg in message_logger.messages:
            # Check for tool name
            if msg.get("tool_name") in ["search_quran", "search_hadith"]:
                has_references = True
                break
            # Check for reference list
            if msg.get("ref_list"):
                has_references = True
                break
            # Check for tool_details
            if msg.get("tool_details"):
                has_references = True
                break
                
        assert has_references, "No references found in the response"
        
        return True
    
    def test_multi_turn_conversation(self):
        """Test a multi-turn conversation with the agent."""
        logger.info(f"Starting multi-turn conversation test for {self.agent_class.__name__}")
        
        message_logger = IntegrationMessageLogger()
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
    
    def run_all_tests(self) -> List[bool]:
        """Run all tests and return the results."""
        test_methods = [
            self.test_simple_conversation,
            self.test_conversation_with_references,
            self.test_multi_turn_conversation
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

# Helper function to run tests directly
def run_tests_for_implementation(agent_class: Type[Ansari]):
    """Run all tests for a specific implementation."""
    settings = Settings()
    tester = AnsariTester(agent_class, settings)
    results = tester.run_all_tests()
    return all(results) 