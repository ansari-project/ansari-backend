# Integration Tests

This directory contains integration tests that interact with real external services (like the Anthropic Claude API).

## Requirements

- Valid Anthropic API key set in your environment (`ANTHROPIC_API_KEY`)
- All project dependencies installed

## Running the Tests

To run only the integration tests:

```bash
pytest tests/integration -v -m integration
```

To run a specific test:

```bash
pytest tests/integration/test_claude_integration.py -v -k test_simple_conversation
```

## Test Categories

1. `test_simple_conversation`: Tests basic conversation functionality with Claude
2. `test_conversation_with_references`: Tests conversations that involve Quran/Hadith references
3. `test_multi_turn_conversation`: Tests multi-turn conversations to verify context retention

## Notes

- These tests interact with the real Claude API and may incur costs
- Tests may take longer to run compared to unit tests due to API latency
- Ensure you have sufficient API quota before running tests
