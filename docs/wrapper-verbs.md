# Wrapper verbs and migration

The reviewed inventory is 108 legacy verbs: **37 survivors, 70 dropped, 1 deferred**.
The original research classifications remain A27 / B63 / C6 / D12. A is a single
indexed operation; B adds prerequisite lookups; C combines independent operations;
D is a local transform or workflow. The reviewed decision reflects the current
tag coverage, so class alone does not determine survival.

The machine-readable source is `tests/wrapper_verbs.json`. The count test checks
these rows against the command tree and compiled rename entries. Dropped commands
accept old arguments only to emit a JSON error on stderr with exit 2 and an indexed
replacement; they send nothing. Their `--help` documents remain exit 0. Numeric ID
placeholders mean the generic operation requires that ID; use discovery for any
needed lookup. File bodies must match the operation schema: `api describe OPERATION`
and `api call OPERATION --help` document fields, guards and required parameters.
Generic destructive calls preview by default and require `--confirm` to send.

Surviving HTTP workflows use `Surface.call` for every request, including reads.
They use the same paging, prerequisite, version, rich-text and scope tags as the
API group. Configure `CONFLUENCE_ALLOWED_SPACES`; site operations also require
`CONFLUENCE_ALLOW_SITE_OPERATIONS=1`. Local history/cache operations keep their
existing file behavior. Legacy Python library APIs remain available.

| Verb | Research class | Decision | Reason | Replacement / operation |
|---|---|---|---|---|
| admin user search | A | dropped | Single indexed operation. | api call searchUser --cql 'user.fullname ~ "NAME"' |
| admin user get | A | dropped | Single indexed operation. | api call getUser --account-id ACCOUNT |
| admin user groups | A | dropped | Single indexed operation. | api call getGroupMembershipsForUser --account-id ACCOUNT --all |
| admin group list | A | dropped | Single indexed operation. | api call getGroups --all |
| admin group get | A | dropped | Single indexed operation. | api call getGroupByGroupId --id GROUP_ID |
| admin group members | A | dropped | Single indexed operation. | api call getGroupMembersByGroupId --group-id GROUP_ID --all |
| admin group create | A | dropped | Single indexed operation. | api call createGroup --body @group.json |
| admin group delete | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call removeGroupById --id GROUP_ID |
| admin group add-user | A | dropped | Single indexed operation. | api call addUserToGroupByGroupId --group-id GROUP_ID --body @member.json |
| admin group remove-user | A | dropped | Single indexed operation. | api call removeMemberFromGroupByGroupId --group-id GROUP_ID --account-id ACCOUNT |
| admin space settings | A | dropped | Single indexed operation. | api call getSpaceSettings --space-key KEY |
| admin space update | A | dropped | Single indexed operation. | api call updateSpace --space-key KEY --body @space.json |
| admin space permissions | A | dropped | Single indexed operation. | api call getSpacePermissionsAssignments --id SPACE_ID --all |
| admin template list | A | dropped | Single indexed operation. | api call getContentTemplates --space-key KEY --all |
| admin template get | A | dropped | Single indexed operation. | api call getContentTemplate --content-template-id TEMPLATE_ID |
| admin permissions check | B | survivor | Identity/group grants are evaluated to answer permission questions. | — |
| analytics views | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call getViews --content-id PAGE_ID The legacy verb read content history; getViews is the indexed analytics replacement. |
| analytics watchers | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call getWatchesForPage --id PAGE_ID |
| analytics popular | A | dropped | Single indexed operation. | api call searchByCQL --cql 'type=page ORDER BY lastmodified desc' --all |
| analytics space | B | survivor | Aggregate counts and contributor/date statistics across selected content categories; uncovered report transform. | — |
| attachment list | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call getPageAttachments --id PAGE_ID --all |
| attachment upload | A | dropped | Single indexed operation. | api call createAttachment --id PAGE_ID Multipart request bodies use --field file=@PATH and send the required X-Atlassian-Token: nocheck header. |
| attachment download | B | survivor | Attachment metadata lookup followed by a binary download, including an all-attachment loop. | — |
| attachment update | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call updateAttachmentData --id PAGE_ID --attachment-id ATTACHMENT_ID Multipart request bodies use --field file=@PATH and send the required X-Atlassian-Token: nocheck header. |
| attachment delete | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call deleteAttachment --id ATTACHMENT_ID |
| bulk label add | B | survivor | CQL selection followed by per-page label writes; loop and checkpoints. | — |
| bulk label remove | B | survivor | CQL selection followed by per-page label removals; loop and checkpoints. | — |
| bulk move | B | survivor | CQL selection and target checks followed by per-page moves; loop and checkpoints. | — |
| bulk delete | B | survivor | CQL selection followed by per-page deletion; loop and checkpoints. | — |
| bulk permission | B | survivor | CQL selection, current grants, diff then writes; decision and loop. | — |
| bulk update | B | survivor | CQL selection followed by per-page field updates; loop and checkpoints. | — |
| comment list | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. Comment tags added by JAS-41. | api call getPageFooterComments --id PAGE_ID --all |
| comment add | C | dropped | Rich-text transform belongs to tags. Comment tags added by JAS-41. | api call createFooterComment --body @comment.json |
| comment add-inline | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. Comment tags added by JAS-41. | api call createInlineComment --body @comment.json |
| comment update | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. Comment tags added by JAS-41. | api call updateFooterComment --comment-id COMMENT_ID --body @comment.json |
| comment delete | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. Comment tags added by JAS-41. | api call deleteFooterComment --comment-id COMMENT_ID |
| comment resolve | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. Comment tags added by JAS-41. | api call updateInlineComment --comment-id COMMENT_ID --body @resolution.json |
| hierarchy children | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call getChildPages --id PAGE_ID --all |
| hierarchy ancestors | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call getPageAncestors --id PAGE_ID --all |
| hierarchy descendants | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call getPageDescendants --id PAGE_ID --all |
| hierarchy tree | B | survivor | Recursive child traversal with depth limit and statistics. | — |
| hierarchy reorder | B | survivor | Local order/reverse transform has no tag; preserve proposed-order-only behavior, never claim a write. | — |
| jira link | B | survivor | Read, optional duplicate decision, append marker and write. | — |
| jira linked | C | survivor | Local storage macro/reference extraction is not covered by rich-text tags. | — |
| jira embed | B | survivor | Local macro insertion/replacement is not generic Markdown conversion. | — |
| jira create-from-page | B | deferred | Explicit release-ticket deferral; current module remains untouched. | — |
| jira sync-macro | B | survivor | Local macro extraction/JQL rewriting has no tag. | — |
| label list | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call getPageLabels --id PAGE_ID --all |
| label add | A | dropped | Single indexed operation. | api call addLabelsToContent --id PAGE_ID --body @labels.json |
| label remove | A | dropped | Single indexed operation. | api call removeLabelFromContent --id PAGE_ID --label LABEL |
| label search | A | dropped | Single indexed operation. | api call searchByCQL --cql 'label="LABEL"' --all |
| label popular | B | survivor | Actual code counts/ranks labels from expanded CQL results; uncovered aggregation transform, not three sequential sources. | — |
| ops cache-status | D | survivor | Core cache, diagnostic, autocomplete or local history affordance; retain shape. | — |
| ops cache-clear | D | survivor | Core cache, diagnostic, autocomplete or local history affordance; retain shape. | — |
| ops cache-warm | B | survivor | Cache affordance; keep public shape and route HTTP through Surface. | — |
| ops health-check | D | survivor | Core cache, diagnostic, autocomplete or local history affordance; retain shape. | — |
| ops rate-limit-status | D | survivor | Core cache, diagnostic, autocomplete or local history affordance; retain shape. | — |
| ops api-diagnostics | D | survivor | Core cache, diagnostic, autocomplete or local history affordance; retain shape. | — |
| page get | C | dropped | Rich-text transform belongs to tags. | api call getPageById --id PAGE_ID --body-format storage |
| page create | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call createPage --space DOCS --space-key DOCS --field title=T --field body=@body.md |
| page update | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call updatePage --id PAGE_ID --field title=T --field body=@body.md --confirm |
| page delete | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call deletePage --id PAGE_ID --confirm |
| page copy | B | survivor | Recursive source-tree copy; conditional parent/space handling and child loop. | — |
| page move | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call updatePage --id PAGE_ID --body @move.json --confirm |
| page versions | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call getPageVersions --id PAGE_ID --all |
| page restore | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call restoreContentVersion --id PAGE_ID --body @version.json |
| page blog get | C | dropped | Rich-text transform belongs to tags. | api call getBlogPostById --id BLOG_ID --body-format storage |
| page blog create | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call createBlogPost --space DOCS --space-key DOCS --field title=T --field body=@body.md |
| permission page get | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call getRestrictions --id PAGE_ID |
| permission page add | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call addRestrictions --id PAGE_ID --body @restrictions.json |
| permission page remove | B | survivor | Remove user/group restrictions across selected operation types; loop. | — |
| permission space get | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call getSpacePermissionsAssignments --id SPACE_ID --all |
| permission space add | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call addPermissionToSpace --space-key KEY --body @permission.json |
| permission space remove | B | survivor | Resolve matching subject grants then delete matching grants; decision and loop. | — |
| property list | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call getPageContentProperties --page-id PAGE_ID --all |
| property get | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call getPageContentPropertiesById --page-id PAGE_ID --property-id PROPERTY_ID |
| property set | B | survivor | Update-or-create decision after property lookup. | — |
| property delete | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call deletePagePropertyById --page-id PAGE_ID --property-id PROPERTY_ID |
| search cql | A | dropped | Single indexed operation. | api call searchByCQL --cql 'space=DOCS' --all |
| search content | A | dropped | Single indexed operation. | api call searchByCQL --cql 'space=DOCS AND text~"TEXT"' --all |
| search validate | A | dropped | Single indexed operation. | api call searchByCQL --cql 'QUERY' --limit 1 |
| search suggest | D | survivor | Core cache, diagnostic, autocomplete or local history affordance; retain shape. | — |
| search export | C | survivor | CSV projection/serialization has no tag. | — |
| search stream-export | C | survivor | Streaming file export/CSV serialization has no tag. | — |
| search history list | D | survivor | Core cache, diagnostic, autocomplete or local history affordance; retain shape. | — |
| search history search | D | survivor | Core cache, diagnostic, autocomplete or local history affordance; retain shape. | — |
| search history show | D | survivor | Core cache, diagnostic, autocomplete or local history affordance; retain shape. | — |
| search history clear | D | survivor | Core cache, diagnostic, autocomplete or local history affordance; retain shape. | — |
| search history export | D | survivor | Core cache, diagnostic, autocomplete or local history affordance; retain shape. | — |
| search history cleanup | D | survivor | Core cache, diagnostic, autocomplete or local history affordance; retain shape. | — |
| search interactive | A | dropped | Single indexed operation. | api call searchByCQL --cql 'QUERY' |
| space list | A | dropped | Single indexed operation. | api call getSpaces --all |
| space get | A | dropped | Single indexed operation. | api call getSpaces --keys KEY |
| space create | A | dropped | Single indexed operation. | api call createSpace --body @space.json |
| space update | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call updateSpace --space-key KEY --body @space.json |
| space delete | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call deleteSpace --space-key KEY |
| space content | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call getPagesInSpace --id SPACE_ID --all |
| space settings | A | dropped | Single indexed operation. | api call getSpaces --keys KEY |
| template list | B | survivor | Conditional aggregation of global/space templates or blueprints; retain source selection and merged report. | — |
| template get | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call getContentTemplate --content-template-id TEMPLATE_ID |
| template create | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call createContentTemplate --body @template.json |
| template update | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call updateContentTemplate --body @template.json |
| template create-from | B | survivor | Select template, create page then conditionally add labels. | — |
| watch page | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call addContentWatcher --content-id PAGE_ID |
| watch unwatch-page | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call removeContentWatcher --content-id PAGE_ID --x-atlassian-token no-check |
| watch space | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call addSpaceWatcher --space-key KEY --x-atlassian-token no-check For unwatch use api call removeSpaceWatch --space-key KEY --x-atlassian-token no-check. |
| watch status | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call getContentWatchStatus --content-id PAGE_ID |
| watch list | B | dropped | Only context/identity/version prerequisite reads, a confirmation preview, or a direct indexed replacement. | api call getWatchesForPage --id PAGE_ID |

## Deferred

- `jira create-from-page`: **the jira-as release ticket** identified by the briefing
  (no numeric ticket key supplied). Its Jira dependency and old implementation
  remain unchanged, outside the Surface survivor seam.

## Workflow behavior

`bulk label --cql 'space=DOCS' --add reviewed --dry-run` aliases the retained
`bulk label add` command; it is not an additional inventory row. Dry-run resolves
targets through Surface reads and prints each intended operation without writes.
An apply run sends one operation per selected item. Bulk checkpoints are versioned
JSON, replaced atomically after each completed item; resume checks command identity
and target selection, and failed items are retried rather than recorded as done.

`hierarchy reorder` reports a proposed order only. `bulk move` uses a parent-page
move operation; a cross-space request refuses because updatePage has no spaceId
update field. `template create-from --blueprint` refuses explicitly because the
pinned operations do not apply a blueprint; template/custom Markdown creation works.
`page copy` snapshots descendants before writing and refuses a destination within
the source subtree, so a recursive copy cannot grow itself indefinitely.

`CONFLUENCE_AS_TRANSPORT=simulation` selects the stateful engine transport without
credentials or HTTP. A process owns its in-memory store; independent CLI processes
start fresh. Python tests can inject one `SimulationStore` across successive argv
invocations to verify writes and later reads. Only the documented operation/CQL
subset is implemented; unsupported operations fail descriptively. It is not live
Confluence acceptance. See as-engine `docs/simulation.md` for fixtures and limits.

JAS-41 also adds missing comment write rich-text descriptors for
createFooterComment, createInlineComment, updateFooterComment and updateInlineComment,
and version descriptors for updateFooterComment, updateInlineComment and
updatePagePropertyById. These are additive actions in the new rename overlay.
