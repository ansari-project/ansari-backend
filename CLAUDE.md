# Ansari Backend - Developer Guide

## Branch Management
- Always create new branches from the `develop` branch, NOT from `main`
- Use descriptive branch names that reflect the feature or fix being implemented
- Keep branches focused on a single feature or fix
- Delete branches after they're merged to keep the repository clean

## Repository Organization
- Keep the root directory clean and organized
- Place temporary files, debug scripts, and other non-production artifacts in the `tmp/` directory
- The `tmp/` directory is gitignored, making it perfect for development-only files
- Make sure scripts and tools intended for the repository are placed in appropriate subdirectories

## Git Commit and PR Guidelines
- Do not include "Generated with Claude Code" or "Co-Authored-By: Claude" in commit messages
- Do not include "Generated with Claude Code" in PR descriptions or anywhere else
- Keep commit messages concise and descriptive
- Use imperative mood in commit messages (e.g., "Add feature" not "Added feature")
- Always run `ruff check` and `ruff format` before committing changes
- Fix all linting errors - clean code is maintainable code
- All PRs should target the `develop` branch, not `main`

## Branch Management Details
- Consider a merged branch "done" - do not add new changes to it
- If you have changes after a branch was merged:
  - Create a new branch from the latest develop branch
  - Apply your new changes there
  - Create a new PR with a descriptive name
- For related but separate features, use separate branches and PRs
- Delete branches after they're merged to keep the repository clean

## Build/Test/Lint Commands
- Install dependencies: `uv sync` - Installs all dependencies from pyproject.toml and uv.lock
- Run backend service:
  1. Use venv python directly: `.venv/Scripts/python.exe src/ansari/app/main_api.py`
  - Alternative (if uvicorn is available): `uvicorn main_api:app --reload`

  **Note**: Direct venv python path is used because `source .venv/Scripts/activate` may not properly activate the virtual environment in bash.

  **Testing changes**: Auto-reload can be unreliable. For reliable testing after code changes:
  1. Kill the running server (`KillShell` tool)
  2. Start new server: `.venv/Scripts/python.exe src/ansari/app/main_api.py`
  3. Wait 10 seconds for startup to complete
  4. Then test with curl
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
- Package commands:
  - Build package: `python -m build`
  - Upload to PyPI: `twine upload dist/*` (requires PyPI credentials)

## Package Management
- **Install dependencies**: `uv sync` - Installs all dependencies from pyproject.toml and uv.lock
- **Add new package**: `uv add <package>` - Adds package to dependencies and updates lock file
- **Add development dependency**: `uv add --dev <package>` - Adds package to dev dependencies
- **Remove package**: `uv remove <package>` - Removes package from dependencies
- **Create virtual environment**: `uv venv` - Creates .venv directory (if not exists)
- **Update dependencies**: `uv lock` - Updates uv.lock file with latest compatible versions

## Code Style Guidelines
- **Imports**: Use absolute imports within the `ansari` package
- **Formatting**: Double quotes for strings, 4-space indentation
- **Line length**: 127 characters maximum
- **Types**: Use Python type hints for function parameters and return types
- **Naming**: Use snake_case for variables/functions, PascalCase for classes
- **Error handling**: Use try/except blocks with specific error types
  - Prefer clean failures over unpredictable recovery attempts
  - Log errors clearly and completely before failing
  - Do not attempt to "fix" malformed data that could lead to unexpected behavior
  - If recovery is necessary, implement it as a well-tested, dedicated fix rather than ad-hoc patches
  - Avoid cascading fallbacks - throw clear errors instead
- **Logging**: Use the logger from `ansari.ansari_logger.get_logger()`
- **Documentation**: Add docstrings to functions, especially complex ones
- **Testing**: Create unit tests in `tests/unit/` and integration tests in `tests/integration/`
- **Citations**:
  - All search tools must format document data as multilingual JSON using `format_multilingual_data`
  - The data format must be valid JSON following the schema in `base_search.py` documentation
  - Store properly formatted JSON in the `data` field of document references
  - Citation handling should account for both full document citations (valid JSON) and partial citations (plain text)
- **Test-first development**: Always write tests before shipping features
  - Write tests that validate both expected behavior and edge cases
  - When fixing bugs, first write a test that reproduces the issue
  - Run tests frequently during development to catch regressions
- **Code complexity management**:
  - Break down complex methods into smaller, focused helpers with clear responsibilities
  - Use meaningful method names that describe what the method does, not how it does it
  - Add clear comments about the purpose and behavior of complex code
  - Extract state machine logic into clearly defined handlers for each state
  - Aim for methods that can be understood without scrolling
- **Error handling philosophy**: Prefer clean failures over unpredictable recovery attempts
  - Log errors clearly and completely before failing
  - Do not attempt to "fix" malformed data that could lead to unexpected behavior
  - If recovery is necessary, implement it as a well-tested, dedicated fix rather than ad-hoc patches

## Testing Best Practices
- Run tests before committing: `pytest tests/`
- Run specific test categories: `pytest tests/unit/` or `pytest tests/integration/`
- Add tests for new functionality in the appropriate directory
- Use fixture factories to keep tests maintainable
- Test both happy path and error conditions
- Keep tests independent (no dependencies between test functions)