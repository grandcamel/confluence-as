# Confluence Assistant Skills Library

[![PyPI version](https://img.shields.io/pypi/v/confluence-assistant-skills-lib.svg)](https://pypi.org/project/confluence-assistant-skills-lib/)
[![Python versions](https://img.shields.io/pypi/pyversions/confluence-assistant-skills-lib.svg)](https://pypi.org/project/confluence-assistant-skills-lib/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Python library for Confluence Cloud REST API - shared utilities for the [Confluence Assistant Skills](https://github.com/grandcamel/Confluence-Assistant-Skills) project.

## Features

- **ConfluenceClient** - HTTP client with retry logic, pagination, and file uploads
- **ConfigManager** - Multi-source configuration (env vars, JSON files)
- **Error Handling** - Exception hierarchy and decorators for clean error handling
- **Validators** - Input validation for page IDs, space keys, CQL queries, etc.
- **Formatters** - Output formatting for pages, spaces, tables, JSON, CSV
- **ADF Helper** - Atlassian Document Format conversion (Markdown ↔ ADF)
- **XHTML Helper** - Legacy storage format conversion
- **Cache** - File-based response caching with TTL

## Installation

```bash
pip install confluence-assistant-skills-lib
```

> **Note:** This is the **library** package. For the CLI tool, install `confluence-assistant-skills` instead:
> ```bash
> pip install confluence-assistant-skills  # CLI with 'confluence' command
> ```

## Quick Start

```python
from confluence_assistant_skills import (
    get_confluence_client,
    validate_page_id,
    format_page,
    markdown_to_adf,
)

# Set environment variables:
# CONFLUENCE_SITE_URL=https://your-site.atlassian.net
# CONFLUENCE_EMAIL=your-email@example.com
# CONFLUENCE_API_TOKEN=your-api-token

# Get a configured client
client = get_confluence_client()

# Get a page
page_id = validate_page_id("12345")
page = client.get(f"/api/v2/pages/{page_id}")
print(format_page(page))

# Create content from Markdown
content = markdown_to_adf("# Hello\n\nThis is **bold** text.")
```

## Direct Client Usage

```python
from confluence_assistant_skills import ConfluenceClient

client = ConfluenceClient(
    base_url="https://your-site.atlassian.net",
    email="your-email@example.com",
    api_token="your-api-token",
    timeout=30,
    max_retries=3,
)

# GET request
page = client.get("/api/v2/pages/12345")

# POST request
new_page = client.post("/api/v2/pages", json_data={
    "spaceId": "123456",
    "title": "New Page",
    "body": {"representation": "atlas_doc_format", "value": "..."}
})

# Pagination
for page in client.paginate("/api/v2/pages", params={"space-id": "123456"}):
    print(page["title"])

# File upload
result = client.upload_file(
    "/api/v2/attachments",
    file_path="/path/to/file.pdf",
    additional_data={"pageId": "12345"}
)
```

## Configuration

### Environment Variables

```bash
export CONFLUENCE_SITE_URL="https://your-site.atlassian.net"
export CONFLUENCE_EMAIL="your-email@example.com"
export CONFLUENCE_API_TOKEN="your-api-token"
```

## Error Handling

```python
from confluence_assistant_skills import (
    handle_errors,
    ConfluenceError,
    AuthenticationError,
    NotFoundError,
    ValidationError,
)

@handle_errors
def main():
    # Validation errors
    page_id = validate_page_id(user_input)  # Raises ValidationError if invalid

    # API errors are caught and formatted
    page = client.get(f"/api/v2/pages/{page_id}")

if __name__ == "__main__":
    main()  # Errors are caught, formatted, and exit with appropriate code
```

## Validators

```python
from confluence_assistant_skills import (
    validate_page_id,      # Numeric string validation
    validate_space_key,    # Space key format
    validate_cql,          # CQL query syntax
    validate_content_type, # page, blogpost, etc.
    validate_url,          # URL format
    validate_email,        # Email format
    validate_title,        # Page title constraints
    validate_label,        # Label format
    validate_limit,        # Pagination limit
)

page_id = validate_page_id("12345")         # Returns "12345"
space_key = validate_space_key("docs")       # Returns "DOCS" (normalized)
cql = validate_cql('space = "DOCS"')         # Validates syntax
```

## ADF Conversion

```python
from confluence_assistant_skills import (
    markdown_to_adf,
    adf_to_markdown,
    text_to_adf,
    adf_to_text,
    create_heading,
    create_paragraph,
    create_bullet_list,
)

# Convert Markdown to ADF
adf = markdown_to_adf("""
# My Document

This is a **bold** paragraph.

- Item 1
- Item 2

```python
print("Hello")
```
""")

# Convert ADF back to Markdown
markdown = adf_to_markdown(adf)

# Build ADF programmatically
from confluence_assistant_skills import create_adf_doc
doc = create_adf_doc([
    create_heading("Title", level=1),
    create_paragraph(text="Hello, World!"),
    create_bullet_list(["Item 1", "Item 2", "Item 3"]),
])
```

## Caching

```python
from confluence_assistant_skills import Cache, cached

# Direct cache usage
cache = Cache(default_ttl=300)  # 5 minutes
cache.set("key", {"data": "value"})
value = cache.get("key")

# Decorator usage
@cached(ttl=300)
def get_page(page_id):
    return client.get(f"/api/v2/pages/{page_id}")

# First call hits API, subsequent calls use cache
page = get_page("12345")
```

## API Reference

### Client

- `ConfluenceClient` - HTTP client class
- `create_client()` - Factory function
- `get_confluence_client()` - Get configured client from environment variables

### Config

- `ConfigManager` - Configuration management class

### Errors

- `ConfluenceError` - Base exception
- `AuthenticationError` - 401 errors
- `PermissionError` - 403 errors
- `ValidationError` - 400 errors
- `NotFoundError` - 404 errors
- `RateLimitError` - 429 errors
- `ConflictError` - 409 errors
- `ServerError` - 5xx errors

### Formatters

- `format_page()`, `format_space()`, `format_comment()`
- `format_table()` - ASCII table formatting
- `format_json()` - JSON formatting
- `export_csv()` - CSV export
- `print_success()`, `print_warning()`, `print_info()`

### ADF Helper

- `markdown_to_adf()`, `adf_to_markdown()`
- `text_to_adf()`, `adf_to_text()`
- `create_*()` - Node creation functions
- `validate_adf()` - Validate ADF structure

### XHTML Helper

- `xhtml_to_markdown()`, `markdown_to_xhtml()`
- `xhtml_to_adf()`, `adf_to_xhtml()`
- `validate_xhtml()` - Validate XHTML structure

### Cache

- `Cache` - File-based cache class
- `cached()` - Caching decorator
- `get_cache()` - Get global cache instance

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Submit a pull request

```bash
# Install development dependencies
pip install -e ".[dev]"

# Install pre-commit hooks (recommended)
pre-commit install

# Run tests
pytest

# Run with coverage
pytest --cov=src/confluence_assistant_skills

# Code quality checks (run automatically on commit with pre-commit)
ruff check src/ tests/      # Linting
ruff format src/ tests/     # Formatting
mypy src/                   # Type checking
bandit -r src/ -q           # Security scanning
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Related Projects

- [Confluence Assistant Skills](https://github.com/grandcamel/Confluence-Assistant-Skills) - Claude Code skills for Confluence automation
