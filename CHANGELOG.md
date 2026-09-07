# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - Unreleased

Main is the 2.0 line (spec JAS-31; wayfinder map JAS-6). Fixes for the pinned 1.x line land on branch `1.x`.

### Added

- Vendored, pinned Confluence v2 (primary) and v1 (lower tier) Base Documents
  with `manifest.json` provenance (source URL, declared version, sha256,
  fetch date) and per-document enrichment overlays under
  `src/confluence_as/specs/`; a hatchling build hook compiles deterministic
  operation indexes with as-engine into `src/confluence_as/_generated/` for
  wheels and editable installs (never committed); and an offline-capable
  `scripts/refresh_base_documents.py` that re-fetches a document, records its
  provenance and writes an oasdiff review changelog beside it (JAS-34)
- Enrichment Entries for Confluence: deterministically generated paging
  overlays (v2 90 entries, v1 8) from `scripts/generate_paging_tags.py`,
  hand-reviewed overlays (v2 5, v1 29) carrying the v1 start/limit vocabulary,
  the ambiguous paging decisions, page-create space-key resolution and
  page-update version metadata; one generated test per entry, regeneration
  and override-precedence tests, and an independent oas-patch cross-check
  (test-only dependencies oas-patch and jsonschema) (JAS-35)
- The `api` group from as-engine: `api call <operationId>` (camelCase or
  kebab-case; parameters as spec-derived flags; body from `@file`, stdin or
  `--field path=value`; parameters validated before any request; body
  validation on request or after a 400), `api search <words>`,
  `api describe <operationId>` (parameters, body outline, response schema,
  every `x-as-*` tag, deprecation and replacement) and `api topics`; raw
  JSON by default with `--format table|markdown`; JSON error objects on
  stderr with documented exit codes; `CONFLUENCE_AS_TRANSPORT=responder`
  selects the offline responder double (JAS-36)
- Cassette transports for offline contract tests: `CONFLUENCE_AS_TRANSPORT=cassette`
  with `CONFLUENCE_AS_CASSETTE` replays a recorded, credential-free cassette;
  `CONFLUENCE_AS_RECORD` records through the live transport with recursive
  scrubbing of credentials and site identifiers; `tests/cassettes/` and the
  Generic Surface contract tests; `scripts/check_base_document_drift.py` and
  the weekly/release `drift.yml` workflow compare the pinned Base Documents
  with Atlassian's live documents (oasdiff breaking and changelog, enriched
  operations) and file a JAS ticket on drift (JAS-42)
- Generic api call --all/--limit aggregation, --parameter-limit page sizing,
  tag-derived key aliases such as --space-key, and --version override with
  automatic current-version resolution (JAS-37)

### Removed verbs

- (filled by the Wrapper Verb ticket: every single-call verb dropped in favour of the Generic Surface)

### Rename table

- (filled by the Wrapper Verb ticket: old verb -> `api call <operationId>`)

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
