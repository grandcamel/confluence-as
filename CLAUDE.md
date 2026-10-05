# CLAUDE.md

Guidance for changes to `confluence-as`, the Confluence Cloud CLI and Python
library.

## Architecture

The CLI's primary request path is the indexed Generic Surface. Product-owned
OpenAPI Base Documents live in `src/confluence_as/specs/`; enrichment overlays
there add paging, scope, version, rich-text and binary-response behavior. The
Hatchling build hook compiles deterministic operation indexes for editable and
wheel builds. Do not edit generated indexes as source or fetch documents during
normal builds.

CLI discovery is lazy: `api describe`, `api search`, `api topics`, `help` and
`--version` avoid HTTP and defer optional legacy-client imports. Requests enter
through `src/confluence_as/engine.py`, where engine validation, transforms,
transport, scope guards and error shapes apply. Surviving wrapper workflows use
the Surface for Confluence requests and retain only multi-step decisions,
unsupported transforms or local affordances.

`jira create-from-page` is a documented bounded exception. Its Confluence reads
and marker update use indexed operations through the guarded Surface. Jira
`createIssue` uses the JAS-51 hand-built operation through engine
`HTTPTransport`, with a 30-second timeout, zero retries, and no `jira-as`
dependency or Jira project guard. This does not establish universal
`Surface.call` coverage. Scope refusal precedes Jira creation; later Confluence
calls recheck scope. The cross-product workflow is not transactional, so inspect
the reported Jira issue before retrying after a marker-update failure.

Legacy Python exports remain supported for existing integrations. Their client,
configuration, credential, mock and conversion modules are compatibility
surfaces; new CLI request behavior belongs on the indexed path. `CONFLUENCE_MOCK_MODE`
affects legacy client consumers. Indexed CLI calls use responder, cassette,
simulation or HTTP transports selected through the engine seam.

## Change map

- `src/confluence_as/specs/`: pinned Base Documents, provenance manifests and
  product enrichment overlays.
- `src/confluence_as/engine.py`, `src/confluence_as/cli/`: indexed call setup,
  lazy commands and wrapper workflows.
- `hatch_build.py`: deterministic index generation for package builds.
- `tests/`: CLI argument/transport contracts, scope and transform checks,
  migration inventory, build/release checks and offline fixtures.
- `tests/live/run_sbx.py`: the only supported entry point for the separately
  supervised JAS-43 SBX live cases. Its default `all` selection is nine cases,
  `tranche2` is four, and `blog` is one. The blog case has offline ownership and
  admission coverage; live blog acceptance remains unrun. Do not use raw
  `pytest --live` or infer live acceptance from offline results.

## Development and validation

See [README contributing prerequisites](README.md#contributing) for the pinned
build compiler and local setup. Typical checks are:

```bash
python -m pytest
ruff check .
mypy src/
bandit -r src/ -q
python scripts/check_release_tag.py v2.0.0
```

The release-tag check also requires the `RELEASE_DATE` placeholder in README
and CHANGELOG to be replaced. Release publication and promotion use separate
review gates.

Use deterministic responder, cassette or simulation fixtures for offline
request behavior. Do not direct tests to a real tenant unless the task's
separate SBX authority and supported launcher explicitly permit it. The
Confluence allowed-space guard is default-deny for tagged operations; site
operations require separate configuration.

## Release and documentation boundaries

The runtime engine compatibility range is `as-engine>=0.1.2,<0.2`. Release and
isolated builds use the pinned `as-engine==0.1.2` wheel and `hatchling==1.32.0`
compiler described in README and the release workflows. Do not substitute a
moving engine branch in a release build.

The wrapper disposition is 38 survivors, 70 dropped commands and no deferred
implementations. `docs/wrapper-verbs.md` is the detailed inventory. Keep its
bounded JAS-51 Jira transport exception distinct from ordinary guarded Surface
calls. Historical rc1 changelog entries retain their original chronology;
current migration guidance is in the 2.0.0 section.
