import sys
import os
from unittest.mock import MagicMock, patch

# Add the src directory to the path so we can import the modules
src_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
sys.path.insert(0, src_path)

from ansari.agents.ansari_claude import AnsariClaude
from ansari.config import Settings


def test_logging_changes_dont_break_basic_functionality():
    """
    Test that our logging changes don't break basic functionality.
    This is a minimal test to verify nothing fundamental was broken.
    """
    # Create a mock settings object
    settings = MagicMock(spec=Settings)
    settings.ANTHROPIC_MODEL = "claude-3-opus-20240229"
    settings.MAX_FAILURES = 3

    # Create a mocked AnsariClaude instance with initial tools setup
    with patch("anthropic.Anthropic"), patch.object(AnsariClaude, "__init__", return_value=None):
        claude = AnsariClaude.__new__(AnsariClaude)
        claude.settings = settings
        claude.message_logger = None
        
        # Set needed attributes that would normally be set in __init__
        claude.tools = []
        claude.tool_name_to_instance = {}
        claude.citations = []
        claude.message_history = []
        claude.client = MagicMock()

        # Set up a simple message history
        claude.message_history = [
            {"role": "user", "content": "Hello, world!"}
        ]
        
        # Mock the API response to avoid actual API calls
        claude.process_one_round = MagicMock(side_effect=lambda: [])
        
        # Add an assistant response
        claude.message_history.append({
            "role": "assistant", 
            "content": [{"type": "text", "text": "Hello! How can I help you today?"}]
        })
        
        # Verify basic validation works
        assert claude.validate_message(claude.message_history[-1]) == True
        
        # Test message logging works
        claude.message_logger = MagicMock()
        claude._log_message(claude.message_history[-1])
        
        # Verify logger was called
        claude.message_logger.log.assert_called_once()
        
        print("Test passed - basic functionality works!")


if __name__ == "__main__":
    test_logging_changes_dont_break_basic_functionality()