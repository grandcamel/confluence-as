# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Pre-commit hooks for ruff and mypy
- Ruff configuration in pyproject.toml with isort, bugbear, and pyupgrade rules
- CI enforcement of linting (ruff, mypy, bandit)

### Changed
- Code formatted with ruff formatter
- Improved type annotations throughout codebase

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
- **BREAKING**: Renamed package to `confluence-assistant-skills-lib`
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

[Unreleased]: https://github.com/grandcamel/confluence-assistant-skills-lib/compare/v0.3.1...HEAD
[0.3.1]: https://github.com/grandcamel/confluence-assistant-skills-lib/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/grandcamel/confluence-assistant-skills-lib/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/grandcamel/confluence-assistant-skills-lib/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/grandcamel/confluence-assistant-skills-lib/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/grandcamel/confluence-assistant-skills-lib/releases/tag/v0.1.0
