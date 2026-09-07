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
- Help-first discovery: a four-level help command group with a hand-authored
  Level 0, tagged topic and example pages, full operation descriptions with
  --full, and zero-request previews requiring --confirm for destructive or
  irreversible api calls; Confluence v2 and lower-tier space deletion and CQL
  help enrichment (JAS-40)
- Allowed-space (CONFLUENCE_ALLOWED_SPACES) and site-operation
  (CONFLUENCE_ALLOW_SITE_OPERATIONS) settings with api call --space
  enforcement on 82 tagged v2 operations: verified key/id ownership, metadata-
  only bounded resolution reads, documented coverage, and offline request-
  sequence and cassette acceptance tests (JAS-39)
- Page and blog body conversions wired into api call: Markdown writes default
  to storage, --representation atlas_doc_format sends serialized ADF, reads
  render Markdown unless --raw, tagged --field body=@file input, a richtext
  overlay on 14 operations with representation help, and offline
  argv/transport coverage (JAS-38 phase B)
- JAS-41: Wrapper Verbs under the rule — 36 survivors rebuilt on the generic
  Surface path (bulk operations with read-only dry-run and resumable
  checkpoints, hierarchy, permission removals, page copy, property set, label
  popular, analytics space, templates, search export and history, ops, admin
  permission check, jira link/linked/embed/sync-macro); 70 legacy single-
  operation verbs dropped behind the rename overlays (`x-as-legacy-verbs`) and
  a legacy shim that exits 2 naming the replacing `api call`; `attachment
  download` (JAS-61) and `jira create-from-page` deferred;
  `CONFLUENCE_AS_TRANSPORT=simulation` opt-in stateful double; rich-text tags
  on comment writes and version injection on comment and property updates;
  lazy command imports; the full table in `docs/wrapper-verbs.md`. (JAS-41)
- JAS-61: `attachment download` rebuilt on the generic Surface (single and
  `--all`, `--output`/`-o` kept, `--output-dir` added, server filenames
  sanitized) — the last deferred verb besides `jira create-from-page`;
  `specs/v1.attachments.overlay.json` tags `downloadAttatchment` as a binary
  response and documents the multipart request shape on `createAttachment` and
  `updateAttachmentData`, whose rename hints no longer carry a multipart
  caveat; the Wrapper Verb inventory is 37 survivors, 70 dropped, 1 deferred.
  (JAS-61)
- JAS-63: `api describe`, `api search`, `help` and `--version` no longer load
  the legacy client, the converters, the rich-text validator or the
  configuration manager (host: `api describe getPages` 390 → 154 ms median
  against a 41 ms interpreter start); scope configuration is applied exactly
  once immediately before the first call, ahead of the guard and the
  transport, with unchanged refusals and configuration-error output;
  `tests/test_startup.py` pins the request-free discovery path. (JAS-63)

### Removed

The 70 dropped verbs below are the rename table, generated with
`python scripts/changelog_removed_verbs.py`; check it with `--check`.
The [full decision inventory](docs/wrapper-verbs.md) also records the 37
survivors and the one remaining deferral. Replace placeholders and inspect
`api describe OPERATION` for required fields, scope and confirmation flags.

- `admin group add-user` → `api call addUserToGroupByGroupId --group-id GROUP_ID --body @member.json`
- `admin group create` → `api call createGroup --body @group.json`
- `admin group delete` → `api call removeGroupById --id GROUP_ID`
- `admin group get` → `api call getGroupByGroupId --id GROUP_ID`
- `admin group list` → `api call getGroups --all`
- `admin group members` → `api call getGroupMembersByGroupId --group-id GROUP_ID --all`
- `admin group remove-user` → `api call removeMemberFromGroupByGroupId --group-id GROUP_ID --account-id ACCOUNT`
- `admin space permissions` → `api call getSpacePermissionsAssignments --id SPACE_ID --all`
- `admin space settings` → `api call getSpaceSettings --space-key KEY`
- `admin space update` → `api call updateSpace --space-key KEY --body @space.json`
- `admin template get` → `api call getContentTemplate --content-template-id TEMPLATE_ID`
- `admin template list` → `api call getContentTemplates --space-key KEY --all`
- `admin user get` → `api call getUser --account-id ACCOUNT`
- `admin user groups` → `api call getGroupMembershipsForUser --account-id ACCOUNT --all`
- `admin user search` → `api call searchUser --cql 'user.fullname ~ "NAME"'`
- `analytics popular` → `api call searchByCQL --cql 'type=page ORDER BY lastmodified desc' --all`
- `analytics views` → `api call getViews --content-id PAGE_ID`
- `analytics watchers` → `api call getWatchesForPage --id PAGE_ID`
- `attachment delete` → `api call deleteAttachment --id ATTACHMENT_ID`
- `attachment list` → `api call getPageAttachments --id PAGE_ID --all`
- `attachment update` → `api call updateAttachmentData --id PAGE_ID --attachment-id ATTACHMENT_ID`
- `attachment upload` → `api call createAttachment --id PAGE_ID`
- `comment add` → `api call createFooterComment --body @comment.json`
- `comment add-inline` → `api call createInlineComment --body @comment.json`
- `comment delete` → `api call deleteFooterComment --comment-id COMMENT_ID`
- `comment list` → `api call getPageFooterComments --id PAGE_ID --all`
- `comment resolve` → `api call updateInlineComment --comment-id COMMENT_ID --body @resolution.json`
- `comment update` → `api call updateFooterComment --comment-id COMMENT_ID --body @comment.json`
- `hierarchy ancestors` → `api call getPageAncestors --id PAGE_ID --all`
- `hierarchy children` → `api call getChildPages --id PAGE_ID --all`
- `hierarchy descendants` → `api call getPageDescendants --id PAGE_ID --all`
- `label add` → `api call addLabelsToContent --id PAGE_ID --body @labels.json`
- `label list` → `api call getPageLabels --id PAGE_ID --all`
- `label remove` → `api call removeLabelFromContent --id PAGE_ID --label LABEL`
- `label search` → `api call searchByCQL --cql 'label="LABEL"' --all`
- `page blog create` → `api call createBlogPost --space DOCS --space-key DOCS --field title=T --field body=@body.md`
- `page blog get` → `api call getBlogPostById --id BLOG_ID --body-format storage`
- `page create` → `api call createPage --space DOCS --space-key DOCS --field title=T --field body=@body.md`
- `page delete` → `api call deletePage --id PAGE_ID --confirm`
- `page get` → `api call getPageById --id PAGE_ID --body-format storage`
- `page move` → `api call updatePage --id PAGE_ID --body @move.json --confirm`
- `page restore` → `api call restoreContentVersion --id PAGE_ID --body @version.json`
- `page update` → `api call updatePage --id PAGE_ID --field title=T --field body=@body.md --confirm`
- `page versions` → `api call getPageVersions --id PAGE_ID --all`
- `permission page add` → `api call addRestrictions --id PAGE_ID --body @restrictions.json`
- `permission page get` → `api call getRestrictions --id PAGE_ID`
- `permission space add` → `api call addPermissionToSpace --space-key KEY --body @permission.json`
- `permission space get` → `api call getSpacePermissionsAssignments --id SPACE_ID --all`
- `property delete` → `api call deletePagePropertyById --page-id PAGE_ID --property-id PROPERTY_ID`
- `property get` → `api call getPageContentPropertiesById --page-id PAGE_ID --property-id PROPERTY_ID`
- `property list` → `api call getPageContentProperties --page-id PAGE_ID --all`
- `search content` → `api call searchByCQL --cql 'space=DOCS AND text~"TEXT"' --all`
- `search cql` → `api call searchByCQL --cql 'space=DOCS' --all`
- `search interactive` → `api call searchByCQL --cql 'QUERY'`
- `search validate` → `api call searchByCQL --cql 'QUERY' --limit 1`
- `space content` → `api call getPagesInSpace --id SPACE_ID --all`
- `space create` → `api call createSpace --body @space.json`
- `space delete` → `api call deleteSpace --space-key KEY`
- `space get` → `api call getSpaces --keys KEY`
- `space list` → `api call getSpaces --all`
- `space settings` → `api call getSpaces --keys KEY`
- `space update` → `api call updateSpace --space-key KEY --body @space.json`
- `template create` → `api call createContentTemplate --body @template.json`
- `template get` → `api call getContentTemplate --content-template-id TEMPLATE_ID`
- `template update` → `api call updateContentTemplate --body @template.json`
- `watch list` → `api call getWatchesForPage --id PAGE_ID`
- `watch page` → `api call addContentWatcher --content-id PAGE_ID`
- `watch space` → `api call addSpaceWatcher --space-key KEY --x-atlassian-token no-check`
- `watch status` → `api call getContentWatchStatus --content-id PAGE_ID`
- `watch unwatch-page` → `api call removeContentWatcher --content-id PAGE_ID --x-atlassian-token no-check`

### Migration

The generic surface in five lines:

```text
confluence-as help                          # surface map and discovery
confluence-as api search page               # find an operation
confluence-as api describe getPages         # parameters, body, notes and examples
confluence-as api call getPages --help       # spec-derived invocation flags
confluence-as api topics                    # tagged guidance and gotchas
```

- Replace each dropped command with its indexed `api call` above; camelCase
  operation IDs also accept kebab-case. Parameters become named flags, bodies
  come from `--body @file`, `--body -` or `--field path=value`, and paging uses
  `--all` with optional `--limit`. Read the operation's help before calling it.
- The legacy shim accepts the old invocation only to return a JSON error on
  stderr naming the replacing operation and invocation, with exit **2** and
  no request. Its `--help` remains available with exit 0. Use
  `confluence-as help migration` to discover the rename topic.
- Of the two JAS-41 deferrals, `attachment download` returned in JAS-61 on
  the generic binary path (single or `--all`, `--output`/`-o` and
  `--output-dir`). Multipart upload/update are available through their
  replacement API operations with `--field file=@PATH`.
  `jira create-from-page` remains deferred until the jira-as release.
- Configuration names and the existing configuration chain remain. Discovery
  (`api describe`, `api search`, `help`, `--version`) sends no requests and
  does not load scope configuration. Scope configuration is applied once,
  immediately before the first call, ahead of the guard and transport
  (JAS-63); discovery success is not proof of permission to call.
- Set `CONFLUENCE_ALLOWED_SPACES=DOCS,ENG` or `confluence.allowed_spaces` for
  tagged operations. Body-scoped writes require `--space KEY` matching the
  resolved body space; filtered lists require their space-id flags. Site
  operations require `CONFLUENCE_ALLOW_SITE_OPERATIONS=1` or
  `confluence.allow_site_operations`. Local scope refusals exit **4**.
  Coverage is tag-defined, including the 82 tagged v2 operations (JAS-39).
- Tagged page/blog Markdown writes default to storage XHTML; use
  `--representation atlas_doc_format` for serialized ADF. Reads render
  tagged rich text as Markdown unless `--raw` preserves its stored body;
  `--raw` still converts write input. `--body-format` chooses the read
  representation. Existing JSON body envelopes remain encoded input
  (JAS-38). Destructive API operations preview until `--confirm` is given.
- The responder is a stateless offline double; `CONFLUENCE_AS_TRANSPORT=simulation`
  selects the opt-in stateful double for workflows. Cassette tests exercise
  the shared request/response seam, and the weekly/release drift job compares
  the pinned Base Documents with upstream and files a JAS ticket for breaking
  changes or changes to enriched operations (JAS-42).
- Main is the 2.x line; the 1.x branch carries fixes for one quarter after
  2.0.0. Legacy Python library exports remain available in this Confluence
  candidate; new integrations should use the generic call path and surviving
  workflows. Jira follows with its Compatibility Contract and separate
  organizational Promotion acceptance.

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
