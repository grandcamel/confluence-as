# Confluence AS

[![PyPI version](https://img.shields.io/pypi/v/confluence-as.svg)](https://pypi.org/project/confluence-as/)
[![Python versions](https://img.shields.io/pypi/pyversions/confluence-as.svg)](https://pypi.org/project/confluence-as/)
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
pip install confluence-as
```

> **Note:** This is the **library** package. For the CLI tool, install `confluence-assistant-skills` instead:
> ```bash
> pip install confluence-assistant-skills  # CLI with 'confluence' command
> ```

## Quick Start

```python
from confluence_as import (
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
from confluence_as import ConfluenceClient

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
from confluence_as import (
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
from confluence_as import (
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
from confluence_as import (
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
from confluence_as import create_adf_doc
doc = create_adf_doc([
    create_heading("Title", level=1),
    create_paragraph(text="Hello, World!"),
    create_bullet_list(["Item 1", "Item 2", "Item 3"]),
])
```

## Caching

```python
from confluence_as import Cache, cached

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
pytest --cov=src/confluence_as

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

## Build

Confluence v2 (primary) and v1 (lower tier, loaded on demand) Base Documents
are pinned in `src/confluence_as/specs/manifest.json` by source URL, declared
version, SHA256 and fetch time. The JSON overlays beside them are the source
of enrichment; vendored documents remain pristine. `as-engine` verifies the
pins, strips the narrative extension, applies overlays and defect hooks, and
compiles one deterministic operation index per document.

Wheel and editable builds both generate `src/confluence_as/_generated/`.
It is ignored by git; wheels include its indexes and catalog, while source
archives include the inputs and build hook. Nothing is fetched at build or
runtime. Consumers use `as_engine.index.load_index(path)` for one document,
or `ProductIndexes(generated_directory)` to load primary indexes eagerly and
retrieve v1 on demand with `.get("v1")`.

Until a compatible `as-engine` release is available on PyPI, install the
engine from its source checkout (or `git+https://github.com/grandcamel/as-engine@main`)
and install `hatchling` in the build environment before using
`python -m pip install --no-build-isolation -e '.[dev]'`. For offline prepared
lanes, `python -m build --wheel --no-isolation` uses the installed engine.
CI follows the git-source route; the engine pipeline must land there first.
An isolated build needs `as-engine>=0.1.0a0,<0.2` available from its package
index. Package versions are unchanged by this pipeline.

Refresh deliberately with `python scripts/refresh_base_documents.py`, with
`oasdiff` on PATH (or `OASDIFF=/path/to/oasdiff`). For an offline refresh use
`--from-file v2=/path/to/new-v2.json`; only named documents are refreshed in
that mode. Each refresh appends `<document>.changelog.md`, then replaces the
source and updates the manifest pin. Review and commit those sources and
changelogs together. A missing oasdiff binary records an explicit skip in the
changelog and stderr; install it and obtain the real diff before accepting a
refresh. Invalid JSON, changed existing pins or a failed oasdiff command leave
the sources unchanged.

## Indexed API operations

The `api` group calls operations from the packaged OpenAPI index through as-engine:

```bash
confluence-as api search page
confluence-as api describe createPage
confluence-as api call getPages --limit 5
confluence-as api call get-pages --space-id '[123,456]' --limit 5
confluence-as api call createPage --body @page.json
confluence-as api call createPage --body - < page.json
confluence-as api call createPage --field 'spaceId="123"' --field title=Example
confluence-as api topics
```

Operation IDs accept canonical camelCase or kebab-case. Spec parameters become
kebab-case flags; `api call OPERATION --help` lists them. Booleans take explicit
`true`/`false`; arrays accept repeated flags, comma-separated values or JSON arrays.
`--field path=value` builds dotted object fields, parsing JSON values where possible;
quote a numeric ID as JSON when the body schema requires a string. Invalid
parameters are refused before a transport is created. `--limit` is the operation's
spec parameter; one response page is returned.

Calls emit raw JSON; `--format table|markdown` renders the top-level result.
Search defaults to a table and supports `--format json`; describe defaults to
Markdown and supports `--format json`. Search excludes deprecated operations unless
`--include-deprecated` is set; calls warn and show a replacement when enrichment
provides one. Topics come from `x-as-topic`, with a clean empty state until tagged.
Only v2 is loaded for primary discovery; a named v1 operation loads v1 on demand.

Use `--validate-body` to check a body before sending. Otherwise body checks run only
after a 400 to enrich the error. The checker reflects the indexed schema and reports
unsupported validators explicitly. Upstream `createPage` body alternatives overlap:
its body oneOf may reject a valid service payload until a correcting overlay lands.
Ordinary calls do not run that optional body check.

HTTP uses the existing configuration chain (`CONFLUENCE_SITE_URL`,
`CONFLUENCE_EMAIL`, `CONFLUENCE_API_TOKEN`), timeouts, TLS settings and retry settings.
The engine supplies pooled HTTP with 429/5xx backoff and Retry-After support.
Confluence's existing domain error mapper is reused. JSON bodies are supported;
non-JSON media types are explicitly refused. Existing commands remain available.

Offline responder mode uses the same call path without reading credentials:

```bash
CONFLUENCE_AS_TRANSPORT=responder confluence-as api call getPages --limit 5
CONFLUENCE_AS_TRANSPORT=responder confluence-as api --respond-with 400 call getPages
```

The responder returns indexed examples or bounded schema-generated bodies, never a
live request. It is stateless and returns null where no 200 schema/example survives
in the index. `--respond-with` is a test hook accepted only in responder mode.

Errors are JSON on stderr: `{status, messages, operation, note}`. Exit codes are
usage/400 **2**, auth **3**, permission/scope **4**, not found **5**, server/exhausted
rate limit **6**, other failure (including 409) **1**, success **0**. No Confluence
project guard is introduced. Live-site acceptance is held separately from offline
responder tests pending the Confluence sandbox ruling.
