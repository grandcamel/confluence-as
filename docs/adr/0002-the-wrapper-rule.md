# The wrapper rule

**Status: Accepted 2026-09-07**

A named Wrapper Verb exists only when it makes more than one HTTP call with a
decision or loop between them, performs a transform that the spec cannot express
and no tag covers, or provides an auth, config, cache or paging affordance. Pure
prerequisite chains do not justify a verb: paging, key resolution, version
injection and supported rich-text conversions belong to the Generic Surface's
tag-driven transforms. Surviving HTTP workflows call Surface.call for every
request and keep their 1.x group and verb names. We chose this over retaining a
command per operation or a second client inside each wrapper, which would let
command behavior, help and guard enforcement drift away from the Enriched Spec.
Applied to Confluence's 108 reviewed verbs, the rule yields 37 survivors, 70
dropped verbs and one deferred implementation, as recorded in
[the decision table](../wrapper-verbs.md) and tests/wrapper_verbs.json. This
records JAS-31's wrapper rule and the reviewed JAS-41/JAS-61 decisions (12 and
13): attachment download now survives on the shared binary path, while jira
create-from-page remains deferred until the jira-as release.

## Consequences

- The 70 dropped verbs are migration shims: old invocations send no requests,
  emit a JSON error naming the replacement api call on stderr and exit 2.
  Their help remains available; help migration discovers the rename topic.
- The changelog's removed list is generated from the rename inventory and
  checked against the compiled rename records. A prerequisite lookup alone
  cannot be used to reintroduce a dropped verb.
- Surviving workflows use the same scope guard, paging, version and rich-text
  transforms as api call. Bulk dry-run may read targets but sends no writes;
  checkpoints and resume support workflows that mutate many targets.
- The opt-in stateful simulation tests decisions and loops at the transport
  seam; the stateless responder and cassette player use that same seam.
  Dropped implementations' per-verb tests give way to shim and generic tests.
- The deferred jira create-from-page implementation is explicitly outside the
  survivor seam until it can use the Jira core. Legacy Python library exports
  remain available; their presence does not authorize new single-call verbs.
