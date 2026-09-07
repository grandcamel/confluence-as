# Confluence-as

Discover and call Confluence Cloud operations.

Usage: confluence-as COMMAND

API: `api search WORDS`, `api describe OPERATION [--full|--examples]`,
`api call OPERATION`, `api topics`.

Wrapper groups: page, search, label, hierarchy, permission, analytics, template,
property, jira, admin, bulk, ops. Migration hints: `help migration`, or invoke an old group or verb.
Deferred: attachment download (JAS-61), jira create-from-page (jira-as release).

Topics: adf, paging, search, fields, project-types, permissions, rate-limits,
representations, sandbox, auth, scope, risk, errors, migration.

Learn: `help GROUP` or `help TOPIC`; `--format json` for structured help;
`--examples` for invocations and bodies. Large lists continue with `--offset`.

Auth: environment credentials (`CONFLUENCE_SITE_URL`, `CONFLUENCE_EMAIL`,
`CONFLUENCE_API_TOKEN`); discovery needs none. Sandbox:
`CONFLUENCE_AS_TRANSPORT=simulation` for stateful workflows;
`api --transport responder` for stateless API responses;
`CONFLUENCE_AS_TRANSPORT=cassette` plus `CONFLUENCE_AS_CASSETTE` for offline playback.

Risk: destructive/irreversible API calls preview without sending;
`--confirm` sends through the normal checks.
