# Ansari Backend - Developer Guide

## Git Commit Guidelines
- Do not include "Generated with Claude Code" or "Co-Authored-By: Claude" in commit messages
- Keep commit messages concise and descriptive
- Use imperative mood in commit messages (e.g., "Add feature" not "Added feature")

## Build/Test/Lint Commands
- Install dependencies: `pip install -r requirements.txt`
- Run database setup: `python setup_database.py`
- Run backend service: `uvicorn main_api:app --reload`
- Run CLI version (interactive): 
  - Claude: `python src/ansari/app/main_stdio.py -a AnsariClaude`
  - OpenAI: `python src/ansari/app/main_stdio.py -a Ansari`
- Run CLI with direct input:
  - `python src/ansari/app/main_stdio.py -i "your question here"` 
  - `python src/ansari/app/main_stdio.py --input "your question here"`
- Run tests: `pytest tests/`
- Run single test: `pytest tests/path/to/test.py::test_function_name`
- Run tests with specific marker: `pytest -m integration`
- Lint code: `ruff check src/`
- Format code: `ruff format src/`

## Code Style Guidelines
- **Imports**: Use absolute imports within the `ansari` package
- **Formatting**: Double quotes for strings, 4-space indentation
- **Line length**: 127 characters maximum
- **Types**: Use Python type hints for function parameters and return types
- **Naming**: Use snake_case for variables/functions, PascalCase for classes
- **Error handling**: Use try/except blocks with specific error types
- **Logging**: Use the logger from `ansari.ansari_logger.get_logger()`
- **Documentation**: Add docstrings to functions, especially complex ones
- **Testing**: Create unit tests in `tests/unit/` and integration tests in `tests/integration/`

## File Management
- **Temporary files**: Always place temporary files in the `tmp/` folder, which is in `.gitignore`