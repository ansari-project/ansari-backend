# Ansari Integration Tests

This directory contains integration tests for Ansari and its various implementations. The goal
is to test different Ansari implementations with the same test cases to ensure consistent behavior.

## Test Structure

The integration tests are organized as follows:

1. `test_helpers.py` - Contains helper functions used by the other test files
2. `test_ansari_generic.py` - Contains generic test cases that can be applied to any Ansari implementation 
3. `test_ansari_integration.py` - Tests specifically targeting the base Ansari implementation
4. `test_claude_integration.py` - Tests specifically targeting the AnsariClaude implementation

## Generic Testing Framework

The `test_ansari_generic.py` module provides a reusable testing framework through the `AnsariTester` class.
This allows running the same test cases against different Ansari implementations to ensure consistent behavior.

```python
from tests.integration.test_ansari_generic import AnsariTester
from ansari.agents.ansari import Ansari

# Create a tester for a specific implementation
tester = AnsariTester(Ansari)

# Run a specific test
tester.test_simple_conversation()

# Run all tests
results = tester.run_all_tests()
```

## Test Cases

The following test cases are implemented:

1. **Simple Conversation** - Tests a basic conversation flow with no tools/references
2. **Conversation with References** - Tests a conversation that should trigger tool usage for references
3. **Multi-turn Conversation** - Tests context retention across multiple conversation turns
4. **Message Reconstruction** - Tests the database storage and reconstruction of messages

## Running the Tests

To run the integration tests:

```bash
# Run all integration tests
pytest tests/integration/ -m integration

# Run specific test file
pytest tests/integration/test_ansari_generic.py -m integration

# Run a specific test case
pytest tests/integration/test_ansari_generic.py::test_simple_conversation_all_agents -v
```

## Adding New Implementations

To test a new Ansari implementation:

1. Create a new test file (e.g., `test_new_impl_integration.py`)
2. Import the `AnsariTester` from `test_ansari_generic.py`
3. Create a fixture that returns an `AnsariTester` for your implementation
4. Add tests using the tester instance
5. Add the new implementation to the parametrized tests in `test_ansari_generic.py`
