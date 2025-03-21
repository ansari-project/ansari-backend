#\!/usr/bin/env python

import json
import os
import sys

from ansari.agents.ansari_claude import AnsariClaude
from ansari.config import get_settings

def test_message_structure():
    """Test that message history conversion works properly."""
    settings = get_settings()
    agent = AnsariClaude(settings)
    
    # Setup test message history with mixed formats
    message_history = [
        {"role": "user", "content": "Hello, this is a test"},
        {"role": "assistant", "content": "This is a plain text response"},  # Plain string content
        {"role": "user", "content": "What is the definition of Tashahhud?"}
    ]
    
    # Process through replace_message_history
    try:
        generator = agent.replace_message_history(message_history)
        # Just run through the generator to process it
        for _ in generator:
            pass
        print("Test passed - no errors in message processing")
    except Exception as e:
        print(f"Test failed with error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_message_structure()
