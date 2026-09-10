# Guarded SBX live tranche — JAS-43

Status: the supervisor verified the first nine cases and snapshotted them at
`337ccfe090ea97f5607c7136fbf88621da306423`: 155 targeted offline passes,
1557 full offline passes / 432 skips / 10 Claude E2E deselections, and nine HTTP
passes with all 14 created resources cleaned (315 receipt events). This is
bounded first-tranche evidence, not product-main landing or JAS-43 closure.
The four Tranche 2 cases are also verified at source snapshot
`8ae991c929d5502253b45b1257bc987e26909ca0`: 309 targeted offline passes,
1711 full offline passes / 418 skips / 10 Claude E2E deselections, lint/format
passes, and an independently reviewed HTTP run of four cases in 51.45 seconds.
Run `a2f9925ac3984a4daa6ccbefe5c41014` produced 183 contiguous receipt events;
all nine created pages were verified removed from current content, with no
residual, unknown outcome or timeout and unchanged source hashes. Jira comment
12476 and `jas43-tranche2-live-result.json` in the JAS coordination record
preserve the bounded proof. The first nine cases were not replayed. These
results do not establish product-main landing or final JAS-43 acceptance.

The active files are `test_page_live.py` (six cases) and
`test_property_live.py` (three cases). They drive the real CLI through Click's
runner, ordinary Surface guards and the HTTP transport supplied by the product.
Four additional files now provide the fixed Tranche 2 cases described below.
All remaining legacy live modules remain unchanged and HELD. The only supported live
interface is `run_sbx.py`, invoked with the exact lane interpreter, `-I`, and the
canonical absolute launcher path. Its standard-library admission runs before
pytest or repository imports. It accepts only the following fixed choices and
optional `--collect-only`; help displays usage and exits.

| Choice | Exact scope |
|---|---|
| `all` (default) | Original nine page/property cases |
| `pages` / `properties` | Original six / three cases |
| `copy` | `test_page_copy_live.py::test_copy_owned_leaf_same_sbx_nonrecursive` |
| `tree` | `test_hierarchy_live.py::test_tree_matches_owned_root_child_grandchild` |
| `versions` | `test_page_versions_live.py::test_versions_match_owned_page_updates` |
| `space-content` | `test_space_content_live.py::test_space_listing_matches_exact_owned_ids` |
| `tranche2` | Exactly the four new cases above |

There is no combined thirteen-case selection and no first-tranche rerun authority.
No raw selector or additional pytest argument is forwarded.

Raw `pytest --live` is unsupported. It may import external plugins or initial,
ancestor or nested conftests before any local diagnostic. Root conftest's
configuration refusal is an interface diagnostic, and its file hook is only a
secondary check. Neither is an authentication or universal pre-import guard.
Without `--live`, the existing offline live-test opt-out remains in effect.
There are no new blanket skips or xfails.

The launcher validates canonical regular, non-symlink selected files and named
support, including every path component beneath the canonical lane root. Trusted
support is `tests/__init__.py`, `tests/live/__init__.py`, `tests/conftest.py`,
`tests/live/conftest.py`, `tests/live/test_utils.py`, and the launcher itself.
The supervisor must review/freeze their hashes along with the selected cases,
interpreter, installed pytest and prepared product/dependency build. Paths are
rechecked immediately before pytest. This is a bounded supported test entrypoint,
not arbitrary-code containment or atomic protection against filesystem replacement.

Nonempty `PYTEST_ADDOPTS` and `PYTEST_PLUGINS` are refused. The launcher sets
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` before importing installed pytest, then exposes
only the named tests packages through their explicit `__path__` values. The
repository root is never added to global `sys.path`; fixed
`--import-mode=importlib` prevents pytest from prepending it during imports.
The launcher checks that the root remains absent. Prepared product/dependency
imports use the supervisor-prepared environment, not root-level module lookup.
Only the two named conftests and launcher
admission object are explicitly supplied as plugins, alongside pytest's built-in
plugins. Fixed arguments include `--noconftest`, `-c /dev/null`, the canonical
root and selected paths, `--live`, `--space-key SBX`, `--capture=no`, `-v`,
`--tb=short`, `--maxfail=1`, and empty `addopts`/`pythonpath` overrides.
No repository configuration or conftest discovery is used. Before fixture setup,
the final collection must contain exactly the approved one, four, six, three or nine node
IDs, with no missing, duplicate or extra nodes. Collection-only success is
discovery evidence and never live acceptance.

Pytest visits sibling files while resolving explicit selections. The launcher's
collection traversal filter admits only the already selected files and their
ancestor directories, avoiding unrelated siblings at the secondary file hook.
This filter is not initial admission: raw arguments and source paths have already
been validated before pytest imports, and automatic conftest loading is disabled.

Supervisor-verified offline source contracts cover the following rejection/admission matrix:

| Input or condition | Required result |
|---|---|
| File, directory, nested file/directory, node ID, outside path or outside symlink selector | Argument error before pytest/repository imports |
| Unknown/abbreviated case, `-p`, `--pyargs`, `-k`, `-m`, config/root/capture/scope override, response file or selector after `--` | Argument error before imports |
| Ambient pytest plugin/options injection | Configuration error before imports |
| Missing/nonregular trusted file, file symlink or directory escape | Path error before imports; recheck before pytest |
| Poison project/CWD/ancestor/nested conftest, repository config, discoverable third-party plugin | Never loaded by supported positive invocation |
| Exact inert one/four/six/three/nine nodes, with or without collection-only | Successful admission preserving private HOME/CWD and keeping the root absent from sys.path |
| Empty/missing/extra/duplicate collection | Error before fixture setup |
| Root product/dependency module shadows and root-only module | Prepared product remains importable; shadow code never executes and root-only module cannot be found |
| Injected bootstrap failure in the copied shipped fixture, six approved page names | Launcher admits six nodes; setup candidate precedes registered cleanup, no test body executes |
| Checkout ancestor containing `tests/live` | Ordinary offline case runs; explicitly marked and actual live-directory cases still skip |

Copied-source subprocess fixtures use a real disposable no-pip venv, not a
whole-venv symlink (which can normalize interpreter identity on macOS). A private
`.pth` references prepared dependency site-packages and the exact prepared
editable product source directory. It does not expose the repository root or
install anything. The fake pytest11 distribution and importable poison module
live in that private environment, so disabling plugin autoload is tested without
root search-path exposure. Subprocesses use `-B` to avoid shared bytecode writes.
The supervisor verified the first-tranche admission matrix and the expanded
matrix, including every new selected-file alias and exact one/four-node refusal.
The 309 targeted passes include these contracts and production scope checks;
workers performed source-only work, while the supervisor owned all execution.

## Permitted execution

Only jas-supervisor-m may invoke the host broker for this exact lane. The
supervisor runs long validation through a one-shot new-session controller and
`scripts/validate-battery` reservation, with a finite deadline and captured output.
Neither a worker turn nor a raw product/HTTP command is an alternative.

The verified Tranche 2 workload used the following fixed launcher argv under
a supervisor-owned timeout child (840 seconds plus 60 seconds for cleanup).
The host broker waited for that child and the journal was captured externally.
This command shape is documentation, not authority for a repeat run:

```sh
/Users/jasonkrueger/projects/grand-camel-platform/scripts/confluence-dev-host /Users/jasonkrueger/projects/lanes/jas-ab-w47/confluence-as --suite /Users/jasonkrueger/projects/lanes/jas-ab-w47/confluence-as/.venv/bin/python -I /Users/jasonkrueger/projects/lanes/jas-ab-w47/confluence-as/tests/live/run_sbx.py --case tranche2
```

`--capture=no` is fixed by the launcher: the incremental journal must reach the
supervisor's captured stream before any timeout. Absolute test paths preserve
the broker's private working directory. Tests do not chdir into the lane or
create another CliRunner isolated filesystem. The broker's `--explain` flag, when separately
needed, precedes the lane argument. Do not run bootstrap or reap here. Global SBX
already exists by the supervisor's recorded bootstrap/read-back.

The suite requires exactly `CONFLUENCE_ALLOWED_SPACES=SBX`, no site-operation
variable, and ordinary HTTP transport. Cassette, record, simulation and mock
overrides are rejected. Host credentials are consumed by the normal product
configuration under the broker. Helpers neither read credentials from files or
Keychain nor print them. These checks are not authentication of execution
provenance. The broker is not arbitrary-code/process containment; untagged
operations and numeric ownership still need their own contracts. A broker
refusal means stop and report, never bypass.

Proposed targeted offline command, from the lane root, under later supervisor authority:

```sh
.venv/bin/python -m pytest tests/test_live_sbx_contract.py tests/test_api_scope.py -q
```

The supervisor must separately prepare the full offline command with the exact
Claude E2E deselection because launching/resuming Claude sessions is forbidden.
The full offline suite with that exclusion is required before any
code commit. The existing prepared full-offline controller is unlaunched and
its source hashes must be refreshed after this amendment. No runtime command,
including lint, import, compile or installation, is authorized by this document.

## Active behavior and ownership

The six page cases cover create/read, owned child creation, title update,
Markdown/storage round-trip, version increment and confirmed deletion from
current content. The three property cases cover indexed create/read/delete,
versioned update and the surviving `property set` wrapper's create/upsert path.
They assert concrete IDs, space, parent, title, content, key/value and version;
a lack of errors or an empty result alone is not a successful lifecycle test.

Tranche 2 adds four narrow behaviors:

- Copy a new owned leaf after a complete `getChildPages --limit 2` preflight,
  with a fresh run title, explicit `--space SBX` and owned root `--parent`.
  No `--include-children` is supplied. The current wrapper still snapshots the
  source children because `--parent` is present; recording-transport contracts
  require that read and exactly one create. The direct returned page ID is
  journaled before assertions/read-back, then SBX, title, parent, current status
  and copied storage body establish ownership. Duplicate/source/parent IDs and
  unknown outcomes retain obligations; no title search or retry recovers them.
- Read a tiny newly owned root/child/grandchild through `hierarchy tree
  --max-depth 2 --stats`. Bounded immediate-child preflights precede the wrapper.
  Exact owned IDs, titles, child shape, depths and stats must match. Tree output
  never establishes ownership.
- Record the initial version and two guarded +1 updates, then call
  `getPageVersions --body-format storage --limit 4 --raw`. Require exactly the
  three recorded unique versions, with no continuation. `PageVersion.page` is
  optional; when present its ID must match the requested owned page.
- List two owned pages with `getPages --space-id '["<SBX-id>"]'
  --id '["<A>","<B>"]' --status '["current"]' --limit 3 --raw`. Exact unique
  IDs, recorded titles/parents, SBX and current status are required. No `--all`,
  title discovery, `getPagesInSpace` or global space sweep is used.

Observed unknown/unexpected child relationships in preflight/tree/list results
block deletion of affected owned parents and emit `child-relationship-unresolved`.
Malformed/incomplete child preflight and ambiguous tree failures also retain
parents conservatively. Unknown IDs are never adopted. Blocks persist for the
run and produce residual receipts even after independent resources are cleaned.
Copy/tree wrappers have no hard aggregate read-count cap and can observe remote
changes after preflight. These cases do not establish atomic protection against
unseen concurrent writers. The host controller must retain its finite budget;
stronger wrapper ownership/read-budget enforcement needs a separate production
claim, never a guard bypass in this suite.

There is one session root and fresh run-owned pages for individual cases. The
session finalizer is registered before bootstrap and retains every successful
creation even when fixture setup or a test fails. Resources remain in the
session journal until explicitly deleted or final cleanup; there is no
pre-existing-content adoption or per-space sweep.

A root page is created through `api call createPage --space SBX --space-key SBX`.
The product scope transform performs its bounded metadata lookup. Its space ID
is then independently checked with guarded `getSpaceById` for key SBX/type
global. Calling `getSpaces` directly would require site permission; it is not a
fixture escape hatch. All creation/update titles and property keys have a fresh
`jas43-<run UUID>-` namespace. Namespace alone never establishes ownership.

Successful creation responses immediately produce a candidate ID event, before
assertions/read-back. Only the exact returned identity, expected name/parent and
SBX read-back promote a candidate to owned. Unknown or ambiguous writes stay
pending, preventing dependent deletion. Malformed responses, duplicate IDs,
failed metadata reads and changed parent/space/key fail closed. No raw response
is included in a helper exception or journal event.

Every destructive helper requires a known owned resource. Pages are guarded
again before mutation; properties require the exact owned page/property/key
relationship because the product's property guard scopes the parent page ID.
Explicit page deletion refuses while ANY known child/property remains owned,
candidate or uncertain, or a dependent write is unresolved. Cleanup uses the
same rule, properties/children first and parents last. It never infers a cascade
or marks child IDs deleted from a parent's deletion or a 404.

After page deletion, `getPages` is constrained by both SBX space ID and the exact
owned page ID/current status; an incomplete listing or a still-present ID fails.
Property deletion requires a complete bounded property list on the owned parent
with the exact ID and key absent. No purge/draft flag, space deletion, title
search recovery or presumed idempotent retry is used. This tranche proves
removal from current content, not permanent trash purge.

## Receipt and failure semantics

Each event is one flushed JSON object with `jas43: 1`, run UUID, sequence and
event name, plus approved operation and validated numeric resource/parent IDs
when applicable. Names, keys, bodies, server messages, credentials and CLI argv
are never copied to the receipt. The stream reference is captured outside
CliRunner redirection. Live pytest capture must remain disabled. The supervisor
must persist the outer stdout stream; a private-CWD log is insufficient because
the broker removes that directory on exit.

`intent` precedes every invocation; `candidate` records a returned create/upsert
ID before validation; `owned`, `mutation`, `cleanup`, `cleanup-failed`,
`unknown-outcome`, `residual` and `unresolved-intent` document progress. A terminal
`complete` requires no residual resources or pending writes. Otherwise cleanup
emits `incomplete` and fails pytest. On hard timeout the last unresolved intent
is the evidence of an unknown outcome: no finalizer or final summary is promised
after SIGKILL, and no one may assume the remote request failed. The controller
must preserve the incremental output and classify the run incomplete.

Cleanup attempts only independent already-owned resources after a failure. It
keeps uncertain/candidate identities for supervisor review and refuses blocked
parents. No missing parent metadata, suppressed exception, 404, or timeout counts
as deletion proof. No automatic retries after uncertain creates are allowed.

## Retained, retired and unresolved obligations

The old suite contains 435 statically inventoried test methods in 91 modules.
The first tranche replaced two modules and shared helper/fixture paths. Tranche 2
replaces only four more named modules, one semantic case each. **The remaining
85 test-bearing modules are retained.** The two verified tranches cover only
the named slices; broader runtime acceptance and legacy disposition remain held.
The proposed later consolidation/deletion of 85 modules is NOT approved.

| Domain or old entry point | Disposition |
|---|---|
| `page create/get/update/delete/move/versions`, `property get/list/delete` | Old CLI verbs are migration stubs; active tests use indexed operations, not old invocations. `property set` survives and is tested. |
| Raw page CRUD duplicates in the two rewritten modules | Consolidated into six lifecycle cases; arbitrary/nonexistent foreign IDs are offline guard cases. Draft/purge/archive/restore and full prior breadth remain unaccepted. |
| Raw v1 property operations in rewritten property module | Replaced by three indexed/wrapper cases using owned keys; full historical property type/search/bulk breadth remains unaccepted. |
| Page copy, hierarchy tree, version list, owned-ID listing | Four verified cases above, with exact owned-content and cleanup evidence. Recursive copy, reorder, restore and broader version/history behavior remain held obligations. |
| Blog posts | createBlogPost is scoped, but numeric get/update/delete lack scope tags; cleanup acceptance unresolved. |
| Labels | addLabelsToContent/removeLabelFromContent and CQL paths are untagged; no label lifecycle acceptance. `label popular` and bulk wrappers still survive. |
| Attachments | createAttachment/updateAttachmentData/downloadAttatchment are untagged; no upload/download/lifecycle acceptance. `attachment download` survives. |
| Restrictions | Untagged addRestrictions/deleteRestrictions plus safe principal/ownership requirements remain unresolved. Permission/bulk wrappers are not declared retired. |
| Search | searchByCQL lacks a scope tag. Search export/stream-export/history/suggest survival remains explicit; no live CQL bypass or invented refusal. |
| Comments | Mutation authority is not enumerated by this ruling, and createFooterComment is untagged; retained as an unresolved obligation. |
| Space/site/account/watch/notification/template/analytics | No site/account changes or space lifecycle. Existing global SBX only. Surviving wrappers are not retired by this exclusion. |
| Jira | Cross-product activity is not authorized. Any future owned-page-only macro work needs a distinct bounded plan. |

Untagged operations are rejected by this tranche's helper allowlist, but that
is not a production scope fix or an assertion that the Surface would refuse
them. Missing guards require a separately claimed production plan and offline
proof before their live acceptance. Never run foreign-space live negatives.

A future report must give the actual selected-case collection/pass/failure/skip
counts, transport/host command, cleanup receipt and residual IDs, and distinguish
source checks, offline tests and live acceptance. A selected-suite green is only
this tranche's evidence. JAS-43 remains open pending broader scope and tracker
acceptance decisions by the supervisor.
