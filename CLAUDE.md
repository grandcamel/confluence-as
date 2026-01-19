# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Python library providing shared utilities for Confluence Cloud REST API automation. This is a dependency of the [Confluence Assistant Skills](https://github.com/grandcamel/Confluence-Assistant-Skills) project.

## Development Commands

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run tests with coverage
pytest --cov=src/confluence_assistant_skills

# Run a single test file
pytest tests/test_validators.py

# Run a specific test
pytest tests/test_validators.py::test_validate_page_id
```

## Code Quality

```bash
# Linting (ruff)
ruff check .                    # Check for issues
ruff check --fix .              # Auto-fix issues

# Type checking (mypy)
mypy src/                       # Check types (should be clean)

# Security scanning (bandit)
bandit -r src/ -q               # Quiet mode, only show issues
```

**Notes:**
- Ruff may remove "unused" imports that are actually re-exports. Mark these with `# noqa: F401`
- Mypy config in pyproject.toml ignores missing stubs for `assistant_skills_lib`
- Run all three before committing significant changes

## Pre-commit Hooks

Pre-commit hooks run ruff and mypy automatically before each commit:

```bash
# Install hooks (one-time setup after cloning)
pre-commit install

# Run manually on all files
pre-commit run --all-files
```

## Architecture

The library is organized into focused modules under `src/confluence_assistant_skills/`:

### Core Modules

- **confluence_client.py** - HTTP client with retry logic, pagination, file upload/download, and context manager support. Uses `requests` with exponential backoff for 429/5xx errors.
- **config_manager.py** - Multi-source configuration from environment variables and JSON profiles (`.claude/settings.local.json`)
- **credential_manager.py** - Secure credential storage via system keychain (macOS Keychain, Windows Credential Manager) with JSON fallback
- **error_handler.py** - Exception hierarchy mapping HTTP status codes to specific error types with service-specific troubleshooting hints

### CLI Module

- **cli/main.py** - Entry point for CLI commands
- **cli/cli_utils.py** - Shared CLI utilities including:
  - `get_client_from_context(ctx)` - shared ConfluenceClient via Click context
  - `handle_cli_errors` - exception handling decorator with exit codes
  - `output_results` - unified output formatting (text/json)
  - `parse_comma_list`, `parse_json_arg` - input parsing with security limits
  - `validate_positive_int`, `validate_non_negative_int` - Click callbacks
- **cli/helpers.py** - Domain-specific helpers (space lookup, file reading)
- **cli/commands/** - Command groups (page, space, search, comment, label, attachment, etc.)

### Utility Modules

- **validators.py** - Input validation functions that raise `ValidationError` on failure
- **formatters.py** - Output formatting for pages, spaces, tables, JSON, and CSV export
- **markdown_parser.py** - Shared Markdown parser producing intermediate representation
- **adf_helper.py** - Atlassian Document Format (ADF) conversion: Markdown ↔ ADF
- **xhtml_helper.py** - Legacy XHTML storage format conversion
- **space_context.py** - Space-specific context loading and caching

## Key Patterns

### ConfluenceClient Usage

**Always use context manager** for ConfluenceClient to ensure proper resource cleanup:

```python
# Correct - context manager handles cleanup automatically
with get_confluence_client() as client:
    page = client.get("/api/v2/pages/12345")
    return page

# Also correct - explicit close
client = get_confluence_client()
try:
    page = client.get("/api/v2/pages/12345")
finally:
    client.close()
```

### Error Handling Pattern

Exception hierarchy with dual inheritance for type checking:

```
ConfluenceError (base)
├── AuthenticationError (401) - with troubleshooting hints
├── PermissionError (403) - with troubleshooting hints
├── ValidationError (400)
├── NotFoundError (404)
├── RateLimitError (429)
├── ConflictError (409) - with recovery hints
└── ServerError (5xx) - with retry guidance
```

### CLI Commands

When adding new CLI commands:
- Use `client = get_client_from_context(ctx)` instead of `get_confluence_client()` directly
- Use `@handle_cli_errors` decorator for consistent error handling
- Use `output_results(data, output_format)` for formatted output

### Other Patterns

- All public APIs are re-exported from `__init__.py` for convenient imports
- Cache functionality is inherited from `assistant-skills-lib` base library
- Confluence API endpoints use `/wiki` prefix in URLs; the client handles this automatically
- Supports both v2 (`/api/v2`) and legacy v1 (`/rest/api`) Confluence endpoints

## Required Environment Variables

```bash
CONFLUENCE_SITE_URL=https://your-site.atlassian.net
CONFLUENCE_EMAIL=your-email@example.com
CONFLUENCE_API_TOKEN=your-api-token
```

Credentials can also be stored securely in:
1. System keychain (highest priority if available)
2. `.claude/settings.local.json` (fallback)

## Test Markers

```bash
# Run only unit tests
pytest -m unit

# Skip slow tests
pytest -m "not slow"

# Run live integration tests (requires credentials)
pytest --live
```

Available markers:
- `@pytest.mark.unit` - Fast unit tests, no external calls
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.slow` - Slow running tests
- `@pytest.mark.live` - Requires live API credentials
- `@pytest.mark.destructive` - Modifies data
- `@pytest.mark.e2e` - End-to-end tests requiring Claude Code CLI

## PyPI Publishing

### Package Name

Published to PyPI as `confluence-assistant-skills-lib`:

```bash
pip install confluence-assistant-skills-lib
```

**Important:** This is the library package. The CLI is published separately as `confluence-assistant-skills`.

### GitHub Actions Trusted Publishers

Trusted Publishers on PyPI are configured **per-package**, not per-repository:

1. Each package (`confluence-assistant-skills`, `confluence-assistant-skills-lib`) needs its own Trusted Publisher configuration
2. Configure at: PyPI Project Settings → Publishing → Add a new publisher
3. Settings:
   - Owner: `grandcamel`
   - Repository: `confluence-assistant-skills-lib` (or appropriate repo)
   - Workflow: `publish.yml`
   - Environment: `pypi` (optional but recommended)

### Release Process

```bash
# Bump __version__ in src/confluence_assistant_skills/__init__.py, then:
git add -A && git commit -m "chore: bump version to 0.3.0"
git push
git tag v0.3.0
git push origin v0.3.0
# GitHub Actions publishes to PyPI automatically
```

Note: Version is defined in `__init__.py` and read dynamically by pyproject.toml via hatch.
