"""Shared helper functions for CLI commands."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from confluence_as import ConfluenceError, ValidationError

if TYPE_CHECKING:
    from pathlib import Path


def get_space_by_key(client: Any, space_key: str) -> dict[str, Any]:
    """Get space details by space key.

    Args:
        client: Confluence API client
        space_key: Space key to look up

    Returns:
        Space data dictionary

    Raises:
        ValidationError: If space not found
    """
    spaces = list(
        client.paginate(
            "/api/v2/spaces", params={"keys": space_key}, operation="get space"
        )
    )
    if not spaces:
        raise ValidationError(f"Space not found: {space_key}")
    return cast(dict[str, Any], spaces[0])


def get_space_id(client: Any, space_key: str) -> str:
    """Get space ID from space key.

    Args:
        client: Confluence API client
        space_key: Space key to look up

    Returns:
        Space ID string

    Raises:
        ValidationError: If space not found
    """
    return cast(str, get_space_by_key(client, space_key)["id"])


def read_file_content(file_path: Path) -> str:
    """Read content from a file.

    Args:
        file_path: Path to the file

    Returns:
        File content as string

    Raises:
        ValidationError: If file not found
    """
    if not file_path.exists():
        raise ValidationError(f"File not found: {file_path}")
    return file_path.read_text(encoding="utf-8")


def is_markdown_file(file_path: Path) -> bool:
    """Check if file is a Markdown file.

    Args:
        file_path: Path to check

    Returns:
        True if file has .md or .markdown extension
    """
    return file_path.suffix.lower() in (".md", ".markdown")


# Operations reported by permission diagnostics, mapped to the space
# permission grant (operation key, target type) that authorizes each one.
SPACE_OPERATION_GRANTS: dict[str, tuple[str, str]] = {
    "read": ("read", "space"),
    "create": ("create", "page"),
    "edit": ("update", "page"),
    "delete": ("delete", "page"),
    "comment": ("create", "comment"),
    "export": ("export", "space"),
    "administer": ("administer", "space"),
    "archive": ("archive", "page"),
    "restrict_content": ("restrict_content", "space"),
}


def get_current_user_space_operations(client: Any, space_id: str) -> dict[str, Any]:
    """Compute which space operations the current user is actually granted.

    Results are derived from the space's permission grants combined with the
    current user's identity and group memberships — nothing is assumed. Each
    operation resolves to True (an explicit user grant, or a grant to one of
    the user's groups), False (grants were readable and none apply), or None
    (unknown: a probe call failed, or the only applicable grants use
    principals whose membership cannot be resolved here, such as roles).

    Args:
        client: Confluence API client
        space_id: Space ID whose permission grants are checked

    Returns:
        Dict with keys:
        - "account_id": current user's account ID, or None if unavailable
        - "display_name": current user's display name, or None
        - "groups": list of {"id", "name"} dicts for the user's groups
        - "operations": mapping of operation name -> True | False | None
    """
    account_id: str | None = None
    display_name: str | None = None
    groups: list[dict[str, Any]] = []
    groups_known = False

    try:
        current_user = client.get(
            "/rest/api/user/current", operation="get current user"
        )
        account_id = current_user.get("accountId")
        display_name = current_user.get("displayName")
    except ConfluenceError:
        account_id = None

    if account_id:
        try:
            member_of = client.get(
                "/rest/api/user/memberof",
                params={"accountId": account_id, "limit": 200},
                operation="get user groups",
            )
            results = member_of.get("results", [])
            groups = [
                {"id": group.get("id"), "name": group.get("name", "")}
                for group in results
            ]
            # Only a provably complete listing lets a group grant count as a
            # definitive "No": if the response signals more pages (a next
            # link, or size/totalSize beyond what was returned), unmatched
            # group grants must resolve to Unknown instead.
            size = member_of.get("size", len(results))
            total = member_of.get("totalSize", size)
            has_next = bool(member_of.get("_links", {}).get("next"))
            groups_known = not has_next and total <= len(results)
        except ConfluenceError:
            groups = []

    grants: list[dict[str, Any]] | None
    try:
        grants = list(
            client.paginate(
                f"/api/v2/spaces/{space_id}/permissions",
                operation="get space permissions",
            )
        )
    except ConfluenceError:
        grants = None

    if grants is None or account_id is None:
        return {
            "account_id": account_id,
            "display_name": display_name,
            "groups": groups,
            "operations": dict.fromkeys(SPACE_OPERATION_GRANTS),
        }

    group_ids = {group["id"] for group in groups if group.get("id")}
    operations: dict[str, bool | None] = {}
    for op, (key, target_type) in SPACE_OPERATION_GRANTS.items():
        granted: bool | None = False
        for grant in grants:
            operation = grant.get("operation", {})
            if operation.get("key") != key or operation.get("targetType") != (
                target_type
            ):
                continue
            principal = grant.get("principal", {})
            principal_type = principal.get("type")
            principal_id = principal.get("id")
            if principal_type == "user":
                # A grant to a different user says nothing about this user.
                if principal_id == account_id:
                    granted = True
                    break
            elif principal_type == "group":
                if principal_id in group_ids:
                    granted = True
                    break
                if not groups_known:
                    granted = None
            elif granted is False:
                # Role or other principal types: membership can't be resolved
                granted = None
        operations[op] = granted

    return {
        "account_id": account_id,
        "display_name": display_name,
        "groups": groups,
        "operations": operations,
    }
