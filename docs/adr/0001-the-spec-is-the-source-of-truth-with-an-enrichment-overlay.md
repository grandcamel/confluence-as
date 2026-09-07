# The spec is the source of truth with an enrichment overlay

**Status: Accepted 2026-09-07**

Confluence-as takes its operation surface from pinned, pristine Confluence v2
and lower-tier v1 Base Documents, with corrections, tags, advisory notes and
help expressed as evidence-bearing OpenAPI Overlay actions. Each action carries
its description, reason, evidence URL and date, origin and test; as-engine applies
the supported target subset, normalizes defects and compiles the Enriched Spec
into compact operation indexes at build time. The wheel carries those indexes,
and the Generic Surface and help interpret them at runtime. We chose this over
editing Atlassian's vendored documents, which loses the distinction between
upstream changes and our corrections, and over maintaining separate client,
command and help definitions, which recreate drift. The product owns its Base
Documents, overlays, configuration and Wrapper Verbs; the shared engine owns the
compiler and call path. This records the enrichment, migration and testing
decisions of JAS-31 and the build and provenance implementation in JAS-34/35.

## Consequences

- Base Documents retain their recorded version, SHA256 and fetch date. Refreshes
  are deliberate reviewed diffs; nothing is fetched at installation or runtime.
- Enrichment provenance and generated entry tests are release prerequisites.
  Unsupported overlay targets are refused; the independent oas-patch check
  verifies the supported actions without creating a second runtime applier.
- The repository holds source documents and overlays. The wheel carries the
  catalog and both compiled indexes; v2 is primary and v1 loads on demand.
- Help, replacement hints and tag-driven transforms derive from the same index.
  Changes are tested through the argv, transport and build seams.
- The weekly and pre-release drift job compares the pinned documents with
  upstream and reports breaking changes or changes to enriched operations.
  Cassette tests provide offline request/response contract evidence.
- Confluence pilots the engine before Jira's migration. Jira's organizational
  Compatibility Contract and the major-version Promotion gate remain separate
  obligations; a product release records the engine version it carries.
