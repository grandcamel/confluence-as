# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.1] - 2026-08-19

### Fixed
- XHTML conversion handles real Confluence storage-format input: ac:/ri:
  namespace normalization preserves opening vs closing tags, so macro
  handlers (code, panels, status, toc, expand) work on namespaced input,
  including `ac:name` parameter elements and CDATA plain-text bodies
- Unhandled `<structured-macro>` blocks are dropped wholesale (innermost
  first) so their parameters and bodies never leak into Markdown output;
  macro names sharing a known prefix (e.g. `expand-foo`) are not treated
  as known
- Multiline table cell structure is preserved: paragraph- and `<br>`-
  separated cell content renders as `<br>` inside Markdown table rows
- Global `-o/--output` now propagates to all subcommands as their
  default; an explicit subcommand `--output` still wins
- `page create` distinguishes a missing create-page grant (reported by
  Confluence as HTTP 404) from a genuine not-found by probing space
  permission grants
- `admin permissions check` derives Yes/No/Unknown per operation from
  the space's actual permission grants, current user identity, and group
  memberships instead of hardcoded optimistic results
- `get_confluence_client()` honors `CONFLUENCE_MOCK_MODE=true` and
  returns the mock client without requiring credentials

### Changed
- CI coverage threshold set just below the current measured baseline
  (38%, measured 39.8%)

## [1.0.0] - 2025-01-20

### Changed
- **BREAKING**: Package renamed from `confluence-assistant-skills-lib` to `confluence-as`
- **BREAKING**: Module renamed from `confluence_assistant_skills_lib` to `confluence_as`
- All imports must be updated: `from confluence_as import ...`
- Updated dependency to `assistant-skills-lib>=1.0.0`

---

## Previous Releases (as confluence-assistant-skills-lib)

## [0.4.1] - 2025-01-20

### Changed
- Updated dependency to `assistant-skills-lib>=1.0.0`

## [0.4.0] - 2025-01-18

### Added
- Pre-commit hooks for ruff and mypy
- Ruff configuration in pyproject.toml with isort, bugbear, and pyupgrade rules
- CI enforcement of linting (ruff, mypy, bandit)
- Pytest markers for e2e, slow, and integration tests
- Integration tests validating component workflows
- Comprehensive tests for adf_helper.py (coverage: 59% → 93%)
- Tests for xhtml_helper.py (coverage: 8% → 92%)
- Tests for confluence_client.py (coverage: 15% → 89%)
- Tests for config_manager.py (coverage: 24% → 100%)
- Extended tests for formatters.py (coverage: 65% → 85%)

### Changed
- Code formatted with ruff formatter
- Improved type annotations throughout codebase
- Overall test coverage improved from 31% to 40%

## [0.3.1] - 2025-01-18

### Added
- Mypy configuration in pyproject.toml
- Code quality commands documented in CLAUDE.md
- `types-requests` dev dependency for mypy

### Fixed
- Type errors in CLI commands
- Added missing attachment methods to ConfluenceClient (`upload_attachment`, `download_attachment`, `update_attachment`)

## [0.3.0] - 2025-01-18

### Added
- Shared markdown parser module for consistent parsing across ADF and XHTML helpers
- `strip_html_tags()` utility function in formatters
- Click dev dependency for CLI tests

### Changed
- Refactored adf_helper to use shared markdown parser
- Refactored xhtml_helper to use shared markdown parser
- Consolidated duplicate text cleaning code

### Fixed
- Package configuration for proper module discovery

## [0.2.0] - 2025-01-17

### Changed
- **BREAKING**: Migrated CLI from plugin to library
- **BREAKING**: Renamed package to `confluence-as`
- **BREAKING**: Removed profile feature from configuration

### Added
- PyPI publishing via GitHub Actions with Trusted Publishers

## [0.1.1] - 2025-01-16

### Changed
- Refactored to inherit from assistant-skills-lib base classes

### Fixed
- HTTP 415 error on file uploads by properly handling Content-Type header
- Added pytest-cov to dev dependencies

## [0.1.0] - 2025-01-15

### Added
- Initial release
- ConfluenceClient with retry logic and pagination
- ConfigManager for environment variable configuration
- Error handling with exception hierarchy
- Validators for input validation
- Formatters for output formatting
- ADF Helper for Atlassian Document Format conversion
- XHTML Helper for legacy storage format conversion
- Cache functionality from assistant-skills-lib

[Unreleased]: https://github.com/grandcamel/confluence-as/compare/v0.4.1...HEAD
[0.4.1]: https://github.com/grandcamel/confluence-as/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/grandcamel/confluence-as/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/grandcamel/confluence-as/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/grandcamel/confluence-as/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/grandcamel/confluence-as/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/grandcamel/confluence-as/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/grandcamel/confluence-as/releases/tag/v0.1.0
