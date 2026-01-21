# PRD: CLI Client Pattern Refactoring

## Problem Statement

The JIRA and Confluence CLI libraries have inconsistent client instantiation patterns that create unnecessary HTTP connections and defeat the purpose of the shared context client pattern.

### Current State (JIRA)

1. `get_client_from_context(ctx)` exists in `cli_utils.py` to provide shared client access
2. `main.py` registers a cleanup callback expecting clients stored in `ctx.obj["_client"]`
3. **However**, implementation functions (e.g., `_get_issue_impl()`) create their own clients via `with get_jira_client() as client:`
4. Result: Two clients created per command - one unused in context, one used in implementation

### Current State (Confluence)

1. `get_client_from_context(ctx)` exists in `cli_utils.py`
2. **However**, all 100 occurrences in CLI commands call `get_confluence_client()` directly
3. Result: New client created for every command, context pattern unused

## Goals

1. **Single client per CLI invocation** - One HTTP session shared across all operations
2. **Consistent pattern** - All CLI code follows the same client access pattern
3. **Proper resource cleanup** - Client closed reliably at CLI exit
4. **Backward compatibility** - Implementation functions still usable standalone
5. **Testability** - Easy to inject mock clients via context

## Technical Approach

### Chosen Solution: Optional Client Parameter Pattern

Implementation functions accept an optional `client` parameter. When provided, use it; otherwise create one via context manager for standalone use.

```python
def _get_issue_impl(issue_key: str, client: JiraClient | None = None) -> dict:
    """Get a JIRA issue.

    Args:
        issue_key: Issue key (e.g., "PROJ-123")
        client: Optional JiraClient. If None, creates one internally.
    """
    if client is not None:
        return client.get_issue(issue_key)

    with get_jira_client() as client:
        return client.get_issue(issue_key)
```

CLI commands pass the context client:

```python
@issue.command(name="get")
@click.pass_context
def get_issue(ctx, issue_key):
    client = get_client_from_context(ctx)
    result = _get_issue_impl(issue_key, client=client)
    click.echo(format_issue(result))
```

### Why This Approach

| Approach | Pros | Cons |
|----------|------|------|
| **Optional client param** (chosen) | Backward compatible, testable, flexible | More parameters |
| Remove context pattern entirely | Simpler | More connections, harder to test |
| Require client param always | Cleanest API | Breaking change for standalone use |

## Scope

### JIRA Assistant Skills Lib

**Files to modify:** 14 CLI command files + cli_utils.py

| File | Occurrences | Notes |
|------|-------------|-------|
| `cli/commands/admin_cmds.py` | 56 | Largest file |
| `cli/commands/jsm_cmds.py` | 46 | |
| `cli/commands/agile_cmds.py` | 20 | |
| `cli/commands/collaborate_cmds.py` | 15 | |
| `cli/commands/search_cmds.py` | 15 | |
| `cli/commands/lifecycle_cmds.py` | 14 | |
| `cli/commands/relationships_cmds.py` | 10 | |
| `cli/commands/time_cmds.py` | 9 | |
| `cli/commands/issue_cmds.py` | 7 | |
| `cli/commands/bulk_cmds.py` | 5 | |
| `cli/commands/dev_cmds.py` | 5 | |
| `cli/commands/fields_cmds.py` | 4 | |
| `cli/commands/ops_cmds.py` | 2 | |
| `cli/cli_utils.py` | 1 | Definition |
| **Total** | **209** | |

### Confluence Assistant Skills Lib

**Files to modify:** 16 CLI command files

| File | Occurrences |
|------|-------------|
| `cli/commands/admin_cmds.py` | 16 |
| `cli/commands/page_cmds.py` | 10 |
| `cli/commands/space_cmds.py` | 7 |
| `cli/commands/search_cmds.py` | 7 |
| `cli/commands/bulk_cmds.py` | 6 |
| `cli/commands/comment_cmds.py` | 6 |
| `cli/commands/permission_cmds.py` | 6 |
| `cli/commands/attachment_cmds.py` | 5 |
| `cli/commands/hierarchy_cmds.py` | 5 |
| `cli/commands/jira_cmds.py` | 5 |
| `cli/commands/label_cmds.py` | 5 |
| `cli/commands/template_cmds.py` | 5 |
| `cli/commands/watch_cmds.py` | 5 |
| `cli/commands/analytics_cmds.py` | 4 |
| `cli/commands/ops_cmds.py` | 4 |
| `cli/commands/property_cmds.py` | 4 |
| **Total** | **100** |

## Implementation Steps

### Phase 1: JIRA Library (Do First - More Complex)

#### Step 1.1: Update cli_utils.py
- Ensure `get_client_from_context()` properly creates and caches client
- Add type hints for `JiraClient`

#### Step 1.2: Update main.py cleanup
- Verify cleanup callback properly closes context client
- Add logging for debugging

#### Step 1.3: Update implementation functions (per file)
For each `_*_impl()` function:
1. Add `client: JiraClient | None = None` parameter
2. Add conditional: if client provided, use it; else create with context manager
3. Update docstring

#### Step 1.4: Update CLI command functions (per file)
For each `@*.command()` function:
1. Add `@click.pass_context` decorator if missing
2. Add `ctx: click.Context` as first parameter if missing
3. Get client via `client = get_client_from_context(ctx)`
4. Pass `client=client` to implementation function

#### Step 1.5: Run tests and fix any failures

### Phase 2: Confluence Library

Same steps as Phase 1, adapted for Confluence patterns.

## Code Transformation Examples

### Before (JIRA issue_cmds.py)

```python
@issue.command(name="get")
@click.argument("issue_key")
@handle_cli_errors
def get_issue(issue_key: str) -> None:
    """Get issue details."""
    result = _get_issue_impl(issue_key)
    click.echo(format_json(result))


def _get_issue_impl(issue_key: str) -> dict:
    issue_key = validate_issue_key(issue_key)
    with get_jira_client() as client:
        return client.get_issue(issue_key)
```

### After

```python
@issue.command(name="get")
@click.argument("issue_key")
@click.pass_context
@handle_cli_errors
def get_issue(ctx: click.Context, issue_key: str) -> None:
    """Get issue details."""
    client = get_client_from_context(ctx)
    result = _get_issue_impl(issue_key, client=client)
    click.echo(format_json(result))


def _get_issue_impl(
    issue_key: str,
    client: JiraClient | None = None,
) -> dict:
    """Get issue details.

    Args:
        issue_key: Issue key (e.g., "PROJ-123")
        client: Optional JiraClient instance. If None, creates one internally.

    Returns:
        Issue data dictionary
    """
    issue_key = validate_issue_key(issue_key)

    if client is not None:
        return client.get_issue(issue_key)

    with get_jira_client() as client:
        return client.get_issue(issue_key)
```

### Before (Confluence ops_cmds.py)

```python
@ops.command(name="health-check")
@handle_errors
def health_check() -> None:
    """Test API connectivity."""
    client = get_confluence_client()
    user = client.get("/rest/api/user/current")
    click.echo(f"Connected as {user.get('displayName')}")
```

### After

```python
@ops.command(name="health-check")
@click.pass_context
@handle_errors
def health_check(ctx: click.Context) -> None:
    """Test API connectivity."""
    client = get_client_from_context(ctx)
    user = client.get("/rest/api/user/current")
    click.echo(f"Connected as {user.get('displayName')}")
```

## Testing Strategy

### Unit Tests
- Mock `get_client_from_context()` to return mock client
- Verify implementation functions work with and without client parameter
- Test that client is reused across multiple operations

### Integration Tests
- Run CLI commands and verify single client created
- Check cleanup callback is invoked

### Manual Testing
```bash
# Test single command
jira-as issue get PROJ-123

# Test multiple subcommands (should reuse client)
jira-as issue get PROJ-123
jira-as issue list --project PROJ

# Test with verbose logging to verify single client
JIRA_DEBUG=1 jira-as issue get PROJ-123
```

## Rollback Plan

If issues arise:
1. Revert commits
2. Implementation functions still work standalone (backward compatible)
3. No data changes - purely code refactoring

## Success Criteria

1. All existing tests pass
2. Only one client instance created per CLI invocation (verified via logging)
3. Client properly closed at CLI exit
4. No performance regression
5. Code review passes

## Estimated Effort

| Task | JIRA | Confluence | Total |
|------|------|------------|-------|
| Update cli_utils.py | 0.5h | 0.5h | 1h |
| Update implementation functions | 4h | 2h | 6h |
| Update CLI commands | 4h | 2h | 6h |
| Testing & fixes | 2h | 1h | 3h |
| **Total** | **10.5h** | **5.5h** | **16h** |

## Commands for Claude Code Session

Start with:
```
Fix the CLI client pattern in jira-assistant-skills-lib following the PRD in CLI_CLIENT_PATTERN_PRD.md.
Start with issue_cmds.py as a reference implementation, then proceed file by file.
Run tests after each file to catch regressions early.
```

## References

- JIRA cli_utils.py: `src/jira_assistant_skills_lib/cli/cli_utils.py`
- JIRA main.py: `src/jira_assistant_skills_lib/cli/main.py`
- Confluence cli_utils.py: `src/confluence_assistant_skills_lib/cli/cli_utils.py`
- Splunk pattern (reference): `src/splunk_assistant_skills_lib/cli/cli_utils.py`
