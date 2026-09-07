# Offline cassette contracts and Base Document drift

The Generic Surface supports three transports. `http` is the default;
`CONFLUENCE_AS_TRANSPORT=responder` retains the schema/example responder.
For playback:

```bash
CONFLUENCE_AS_TRANSPORT=cassette \
CONFLUENCE_AS_CASSETTE=tests/cassettes/generic-surface.json \
confluence-as api call getPages --limit 5
```

Playback never loads credentials or creates HTTP requests. Missing cassette
paths, malformed files and unmatched requests fail explicitly, with the normal
JSON error envelope. `--transport` is an existing hidden option for http and
responder; select cassette through the environment variables above.

For a newly authorized host recording, leave the transport as `http` and set
`CONFLUENCE_AS_RECORD` to a **new** path. Existing paths are refused. The normal
product configuration supplies credentials; the recorder registers the site,
email, token and encoded Basic credential, then scrubs sensitive response fields
and `_links.base` recursively. Python users can supply extra registrations via
`as_engine.cassette.Scrubber`. `CONFLUENCE_AS_RECORD` cannot be combined with
cassette/responder mode; `CONFLUENCE_AS_CASSETTE` requires cassette mode. One
`create_surface()` instance records a named session, including multiple calls
and both document tiers. Separate CLI invocations use separate new paths.
HTTP recording captures final error status, headers and body before the surface
converts them to the existing error codes. Connection exceptions are not recorded.
See as-engine's `docs/cassettes.md` for matching, file format and scrub limits.

## Contract coverage

`tests/cassettes/generic-surface.json` is synthetic. The test helper
`record_local_fixture` in `tests/test_cassette_contract.py` sends requests through
HTTPTransport to an in-process `responses` fake service. The fake receives Basic
authentication and realistic page/create/update/error bodies and deliberately
echoes secret strings. The regression re-records into a temporary path, checks
that none survive and requires byte parity with the committed fixture.

The integration-marked tests drive `api call` for getPages, getPageById,
createPage, updatePage and a 404, plus `api search`, `describe` and `topics`.
A socket guard prevents network; playback additionally forbids requests and
credential loading. Tests have no `live` marker, so the existing CI pytest jobs
run them without a workflow edit:

```bash
python -m pytest -q tests/test_cassette_contract.py
```

Live re-recording remains held on JAS-43. After authorization, use a host with
approved synthetic content, register all opaque identifiers/secrets before the
first call, record to a new file, inspect the scrubbed bytes/diff, replay with
network disabled, then replace the reviewed fixture. A fake-service recording
proves scrubbing and offline playback; it does not prove the live API contract.

## Drift checks

`scripts/check_base_document_drift.py` checks both manifest documents without
updating vendored files. It compares live URLs only when no `--from-file` is
supplied; with that option only named local replacements are checked:

```bash
python scripts/check_base_document_drift.py --oasdiff ../bin/oasdiff \
  --dry-run --from-file v2=/path/to/changed-v2.json
python scripts/check_base_document_drift.py --oasdiff ../bin/oasdiff \
  --dry-run --from-file v2=src/confluence_as/specs/confluence-openapi-v2.json
```

Matching documents exit 0 without output. Breaking changes or changes affecting
an enriched operation produce a Markdown diff summary in a JSON ticket payload
with `--dry-run`. Without that flag, the script prints both Markdown and JSON.
Tool failures, invalid pins and unsupported targets fail loudly. Shared component
changes conservatively flag enriched operations, which can over-report; review
the included pointers and oasdiff output. The script never refreshes pins: a
release refresh still uses `refresh_base_documents.py` and reviews its committed
oasdiff changelog.

The drift workflow runs weekly, on manual dispatch and on prerelease/published
release events, invoking `--file-ticket`. The Principal must provision repository
secrets `JIRA_SITE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, with permission to create
Tasks in JAS using component `confluence-as`. Jira v3 receives an ADF description;
missing credentials and rejected submissions fail the job. This is a product CI
integration, separate from private organizational host wrappers. No live ticket
was filed from the worker lane. Repeated runs can create repeat tickets until a
reviewed Base Document refresh resolves the finding.
