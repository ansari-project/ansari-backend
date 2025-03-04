# Refactor Translation Functionality

## Summary
- Move translation logic from search tools to a dedicated utility module
- Implement parallel text translation using Claude 3.5 Haiku
- Refactor SearchMawsuah to extend SearchVectara and use translation utility
- Remove HTML tags (`<em>`, `</em>`) from Mawsuah search results
- Remove redundant translation from SearchMawsuah.run_as_string method
- Update tests to use the new translation utility
- Add commit message style guidelines to CLAUDE.md

## Changes in Detail
1. Created a new `translation.py` utility with:
   - `translate_text`: Main function to translate single texts with Claude
   - `translate_texts_parallel`: Async function to translate multiple texts in parallel
   - Language detection support with fallback
   
2. Refactored SearchMawsuah to:
   - Extend SearchVectara for better maintainability
   - Filter out HTML emphasis tags for cleaner results
   - Improve results formatting for better readability
   - Remove duplicate translation code

3. Reorganized test files and updated tests to use new utility functions

## Test Plan
- Run unit tests for the search module: `pytest tests/unit/test_search_mawsuah.py`
- Run unit tests for translation: `pytest tests/unit/test_translation.py`
- Run integration tests: `pytest tests/integration/test_claude_integration.py`
- Manually test Arabic to English translation through the API endpoint