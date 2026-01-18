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

## Architecture

The library is organized into focused modules under `src/confluence_assistant_skills/`:

- **confluence_client.py** - HTTP client with retry logic, pagination, and file upload/download. Uses `requests` with exponential backoff for 429/5xx errors.
- **config_manager.py** - Multi-source configuration from environment variables and JSON profiles (`.claude/settings.local.json`)
- **error_handler.py** - Exception hierarchy mapping HTTP status codes to specific error types (`AuthenticationError`, `NotFoundError`, `RateLimitError`, etc.)
- **validators.py** - Input validation functions that raise `ValidationError` on failure
- **formatters.py** - Output formatting for pages, spaces, tables, JSON, and CSV export. Also provides shared utilities like `strip_html_tags()`.
- **markdown_parser.py** - Shared Markdown parser producing intermediate representation. Used by both adf_helper and xhtml_helper for consistent parsing.
- **adf_helper.py** - Atlassian Document Format (ADF) conversion: Markdown ↔ ADF, programmatic node creation
- **xhtml_helper.py** - Legacy XHTML storage format conversion

## Key Patterns

- All public APIs are re-exported from `__init__.py` for convenient imports
- Cache functionality is inherited from `assistant-skills-lib` base library
- Confluence API endpoints use `/wiki` prefix in URLs; the client handles this automatically
- Supports both v2 (`/api/v2`) and legacy v1 (`/rest/api`) Confluence endpoints
- Shared utilities live in the most general module (e.g., `strip_html_tags` in formatters, `parse_markdown` in markdown_parser)
- When two modules need the same logic, extract to a shared module with an intermediate representation pattern
- Use `__version__` from `__init__.py` dynamically (e.g., in User-Agent headers) rather than hardcoding

## Required Environment Variables

```bash
CONFLUENCE_SITE_URL=https://your-site.atlassian.net
CONFLUENCE_EMAIL=your-email@example.com
CONFLUENCE_API_TOKEN=your-api-token
```

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
