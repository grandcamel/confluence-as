# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the `confluence-as` PyPI package - a shared Python library providing HTTP client, configuration management, error handling, and utilities for Confluence Cloud REST API automation. It is a dependency of the [Confluence Assistant Skills](https://github.com/grandcamel/Confluence-Assistant-Skills) project.

**Usage context**: This library powers the `confluence-as` CLI and skill scripts. When Claude Code invokes a Confluence skill, it loads the SKILL.md context, then uses Bash to execute `confluence-as` CLI commands which call this library.

## Common Commands

```bash
# Install for development
pip install -e ".[dev]"

# Run all tests
pytest

# Run tests with verbose output
pytest -v

# Run a specific test file
pytest tests/test_validators.py

# Run a specific test class or method
pytest tests/test_validators.py::TestValidators
pytest tests/test_validators.py::TestValidators::test_validate_page_id

# Run tests with coverage
pytest --cov=src/confluence_as --cov-report=xml -v

# Code Quality
ruff check .                    # Check for issues
ruff check --fix .              # Auto-fix issues
mypy src/                       # Type checking
bandit -r src/ -q               # Security scanning
```

## Architecture

### Module Structure

The package is organized under `src/confluence_as/`:

- **confluence_client.py**: HTTP client with retry logic (3 attempts, exponential backoff with jitter on 429/5xx, respects Retry-After header), session management, file upload/download, and context manager support for Confluence REST API v2. Supports GET, POST, PUT, PATCH, DELETE methods.
- **config_manager.py**: Configuration from environment variables. Priority: env vars > keychain > settings.local.json > settings.json > defaults
- **credential_manager.py**: Secure credential storage via system keychain (macOS Keychain, Windows Credential Manager) with JSON fallback
- **error_handler.py**: Exception hierarchy mapping HTTP status codes to domain exceptions (400→ValidationError, 401→AuthenticationError, 403→PermissionError, 404→NotFoundError, 409→ConflictError, 429→RateLimitError, 5xx→ServerError)
- **validators.py**: Input validation for Confluence-specific formats (page IDs, attachment IDs, space keys, CQL, URLs, emails)
- **formatters.py**: Output formatting for pages, spaces, tables (via tabulate), JSON, and CSV export
- **adf_helper.py**: Atlassian Document Format conversion (markdown/text ↔ ADF) - shared with JIRA
- **xhtml_helper.py**: Legacy XHTML storage format conversion for older Confluence content
- **markdown_parser.py**: Shared Markdown parser producing intermediate representation
- **space_context.py**: Space metadata and content defaults caching
- **autocomplete_cache.py**: CLI autocomplete suggestions caching (spaces, pages, labels)

### Dependencies

This library inherits from `assistant-skills-lib` (base library) and extends it with Confluence-specific functionality. Key dependencies:
- `requests>=2.28.0`: HTTP client
- `click>=8.0.0`: CLI framework
- `assistant-skills-lib>=0.2.1`: Base validation, error handling, config management

### Configuration

Environment variables (highest priority):
- `CONFLUENCE_API_TOKEN`: API token from https://id.atlassian.com/manage-profile/security/api-tokens
- `CONFLUENCE_EMAIL`: Email associated with Atlassian account
- `CONFLUENCE_SITE_URL`: Confluence Cloud URL (e.g., https://company.atlassian.net)
- `CONFLUENCE_MOCK_MODE`: Set to `true` to use mock client instead of real API

Credentials can also be stored securely in:
1. System keychain (highest priority if available)
2. `.claude/settings.local.json` (fallback)

### Error Handling Pattern

All modules use a consistent 4-layer approach:
1. Pre-validation via validators.py before API calls
2. API errors via handle_confluence_error() which maps status codes to exceptions
3. Retry logic in ConfluenceClient for [429, 500, 502, 503, 504]
4. User messages with troubleshooting hints in exception messages

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

### CLI Module

- **cli/main.py**: Entry point for `confluence-as` command
- **cli/cli_utils.py**: Shared CLI utilities including:
  - `get_client_from_context(ctx)` - shared ConfluenceClient via Click context (preferred over direct `get_confluence_client()`)
  - `handle_cli_errors` - exception handling decorator with distinct exit codes
  - `output_results` - unified output formatting (text/json)
  - `parse_comma_list`, `parse_json_arg` - input parsing with security limits (1MB max JSON)
  - `validate_positive_int`, `validate_non_negative_int` - Click callbacks
  - `validate_page_id_callback`, `validate_space_key_callback` - Click argument validators
  - `with_date_range` - decorator adding --start-date/--end-date options
  - `get_output_format` - context-aware output format resolution
- **cli/helpers.py**: Domain-specific helpers (space lookup, file reading)
- **cli/commands/**: Command groups (page, space, search, comment, label, attachment, etc.)

### Export Pattern

All public APIs are exported from `__init__.py`. Consumer scripts should use:
```python
from confluence_as import get_confluence_client, ValidationError, validate_page_id
```

### ConfluenceClient Usage Pattern

**Always use context manager** for ConfluenceClient to ensure proper resource cleanup:

```python
# Correct - context manager handles cleanup automatically
with get_confluence_client() as client:
    page = client.get("/wiki/api/v2/pages/12345")
    return page

# Also correct - explicit close
client = get_confluence_client()
try:
    page = client.get("/wiki/api/v2/pages/12345")
finally:
    client.close()
```

Both `ConfluenceClient` and `MockConfluenceClient` implement `__enter__` and `__exit__` methods.

**Available HTTP methods:**
- `client.get(endpoint, params, operation)` - GET requests
- `client.post(endpoint, json_data, operation)` - Create resources
- `client.put(endpoint, json_data, operation)` - Full resource replacement
- `client.patch(endpoint, json_data, operation)` - Partial updates (v2 API)
- `client.delete(endpoint, params, operation)` - Delete resources

## Adding New Functionality

When adding new modules:
1. Create the module in `src/confluence_as/`
2. Export public APIs from `__init__.py` in both the imports section and `__all__`
3. Add corresponding tests in `tests/`
4. Use existing error classes from error_handler.py
5. Follow the validation pattern: validate inputs before API calls

## Mock Client

The library includes a mock Confluence client for testing without real API calls.

### Architecture

```
src/confluence_as/mock/
├── __init__.py      # Exports MockConfluenceClient, is_mock_mode
├── base.py          # MockConfluenceClientBase with core operations + is_mock_mode()
├── client.py        # Composed client (MockConfluenceClient = Base + all mixins)
└── mixins/          # Specialized functionality
    ├── page.py      # Page CRUD operations
    ├── space.py     # Space operations
    └── content.py   # Generic content operations
```

### Enabling Mock Mode

Set `CONFLUENCE_MOCK_MODE=true` environment variable. The `get_confluence_client()` function checks this:

```python
def get_confluence_client():
    from .mock import is_mock_mode, MockConfluenceClient
    if is_mock_mode():
        return MockConfluenceClient()  # Returns mock instead of real client
    # ... normal client creation from CONFLUENCE_* env vars
```

### Seed Data

Mock client provides deterministic test data:
- **TEST space**: Space key "TEST", name "Test Space"
- **DEV space**: Space key "DEV", name "Development"
- **DOCS space**: Space key "DOCS", name "Documentation"
- **Home pages**: Each space has a home page with id 100001, 100002, 100003
- **Users**: Admin User (user-001), Developer (user-002)

## Security Considerations

### Input Validation (validators.py)

- **Path Traversal Prevention**: Use `validate_file_path(path, "param_name")` for any user-provided file paths. Rejects `..` sequences and paths escaping current directory.
- **CQL Injection Prevention**: User input in CQL queries is escaped via `_escape_cql_string()` (escapes backslashes and double quotes). Use `validate_cql()` for syntax validation.
- **URL Validation**: Use `validate_url(url, require_https=True)` for site URLs
- **Attachment ID Validation**: Use `validate_attachment_id()` for attachment IDs (accepts numeric or `att`-prefixed format)

### CLI Security Patterns

- **File Operations**: Always call `validate_file_path()` before `open()` in CLI commands
- **JSON Input Limits**: `parse_json_arg()` enforces 1MB max size to prevent DoS
- **Credentials**: Never log or expose tokens/passwords; store in `.claude/settings.local.json` (gitignored)

### Data Handling

- **CSV Parsing**: Always use Python's `csv` module, never `split(",")` which breaks on quoted fields
- **HTML Sanitization**: Use `strip_html_tags()` when displaying content that may contain HTML

## Testing Patterns

### Mock Client Fixtures

When mocking `get_confluence_client()` in tests, always add context manager support:

```python
@pytest.fixture
def mock_client():
    """Create mock Confluence client with context manager support."""
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=None)
    return client
```

To verify cleanup, assert on `__exit__` instead of `close`:
```python
# Correct
mock_client.__exit__.assert_called_once()

# Wrong - close() is no longer called directly
mock_client.close.assert_called_once()
```

### Test Markers

```bash
# Run only unit tests
pytest -m unit

# Skip slow tests
pytest -m "not slow"

# Run live integration tests (requires credentials)
pytest --live
```

Available markers (see pyproject.toml for full list):

**Core markers:**
- `@pytest.mark.unit` - Fast unit tests, no external calls
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.slow` - Slow running tests
- `@pytest.mark.live` - Requires live API credentials
- `@pytest.mark.destructive` - Modifies data
- `@pytest.mark.e2e` - End-to-end tests requiring Claude Code CLI

**Domain-specific markers:**
- Page: `page`, `page_create`, `page_update`, `page_delete`, `page_move`, `page_versions`
- Space: `space`, `space_create`, `space_settings`, `space_permissions`
- Search: `search`, `cql`, `search_pagination`, `search_export`
- Comments: `comment`, `footer_comment`, `inline_comment`
- Labels: `label`, `label_add`, `label_remove`, `label_search`
- Attachments: `attachment`, `attachment_upload`, `attachment_download`

## Gotchas

- **Context manager required**: Always use `with get_confluence_client() as client:` pattern. Manual `try/finally` with `close()` works but context manager is preferred.
- **Test mock context manager**: Mock fixtures must include `__enter__` and `__exit__` methods or tests will fail with context manager usage.
- **Ruff may remove re-exports**: Mark intentional re-exports with `# noqa: F401` to prevent removal
- **API URL prefix**: Confluence Cloud uses `/wiki` prefix (e.g., `/wiki/api/v2/pages`). The client handles this automatically.
- **v1 vs v2 API**: Prefer v2 API (`/api/v2`) for new code. Legacy v1 (`/rest/api`) still supported for backward compatibility.
- **v2 API uses PATCH for updates**: Space updates and other partial modifications use `client.patch()` not `client.put()`. PUT is for full replacements.

## Pre-commit Hooks

Pre-commit hooks run ruff and mypy automatically before each commit:

```bash
# Install hooks (one-time setup after cloning)
pre-commit install

# Run manually on all files
pre-commit run --all-files
```

## PyPI Publishing

### Package Name

Published to PyPI as `confluence-as`:

```bash
pip install confluence-as
```

**Important:** This is the library package. The CLI is published separately as `confluence-assistant-skills`.

### GitHub Actions Trusted Publishers

Trusted Publishers on PyPI are configured **per-package**, not per-repository:

1. Each package needs its own Trusted Publisher configuration
2. Configure at: PyPI Project Settings → Publishing → Add a new publisher
3. Settings:
   - Owner: `grandcamel`
   - Repository: `confluence-as`
   - Workflow: `publish.yml`
   - Environment: `pypi` (optional but recommended)

### Release Process

```bash
# Bump __version__ in src/confluence_as/__init__.py, then:
git add -A && git commit -m "chore: bump version to 0.4.0"
git push
git tag v0.4.0
git push origin v0.4.0
# GitHub Actions publishes to PyPI automatically
```

Note: Version is defined in `__init__.py` and read dynamically by pyproject.toml via hatch.
