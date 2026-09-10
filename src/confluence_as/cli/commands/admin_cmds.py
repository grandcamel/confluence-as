"""Administrative survivor commands on the generic operation surface."""

from __future__ import annotations

from typing import Any

import click
from as_engine.surface import Surface

from confluence_as.cli.cli_utils import resolve_output_default
from confluence_as.cli.legacy import command_errors
from confluence_as.engine import create_surface

_GRANTS = {
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


def _rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    return (
        [x for x in value.get("results", []) if isinstance(x, dict)]
        if isinstance(value, dict)
        else []
    )


def _surface() -> Surface:
    return create_surface()


@click.group()
def admin() -> None:
    """Confluence administration affordances."""


@admin.group(name="permissions")
def admin_permissions() -> None:
    """Permission diagnostics."""


@admin_permissions.command("check")
@click.option("--space", "space_key", "-s", required=True)
@click.option("--only-missing", is_flag=True)
@click.option(
    "--output",
    "-o",
    type=click.Choice(["text", "json"]),
    default=None,
    callback=resolve_output_default,
)
@command_errors
def check_permissions(space_key: str, only_missing: bool, output: str) -> None:
    """Derive Yes, No, or Unknown from actual grants and membership."""
    surface = _surface()
    spaces = _rows(surface.call("getSpaces", {"keys": [space_key]}).body)
    if len(spaces) != 1:
        raise click.UsageError(f"Space not found or ambiguous: {space_key}")
    space = spaces[0]
    try:
        user = surface.call("getCurrentUser", {}).body
    except Exception:
        user = None
    account = user.get("accountId") if isinstance(user, dict) else None
    groups: list[dict[str, Any]] = []
    groups_known = False
    if account:
        try:
            membership = surface.call(
                "getGroupMembershipsForUser", {"accountId": account, "limit": 200}
            ).body
            groups = _rows(membership)
            groups_known = not (
                isinstance(membership, dict)
                and (
                    membership.get("_links", {}).get("next")
                    or membership.get("totalSize", len(groups)) > len(groups)
                    or membership.get("size", len(groups)) > len(groups)
                )
            )
        except Exception:
            # Failed or incomplete membership cannot establish group absence.
            groups_known = False
    try:
        grants = _rows(
            surface.call(
                "getSpacePermissionsAssignments",
                {"id": int(space["id"])},
            ).body
        )
    except Exception:
        grants = None
    group_ids = {
        str(x.get("id") or x.get("groupId"))
        for x in groups
        if x.get("id") or x.get("groupId")
    }
    result = []
    for name, (key, target) in _GRANTS.items():
        value: bool | None = False if grants is not None and account else None
        for grant in grants or []:
            operation, principal = (
                grant.get("operation", {}),
                grant.get("principal", {}),
            )
            if operation.get("key") != key or operation.get("targetType") != target:
                continue
            if principal.get("type") == "user":
                if principal.get("id") == account:
                    value = True
                    break
                continue
            if principal.get("type") == "group":
                if str(principal.get("id")) in group_ids:
                    value = True
                    break
                if not groups_known:
                    value = None
            elif value is False:
                value = None
        result.append({"operation": name, "has_permission": value})
    space_name = space.get("name", space_key)
    payload = {
        "user": user.get("displayName") if isinstance(user, dict) else "Unknown",
        "space": {"key": space_key, "name": space_name},
        "groups": [x.get("name", x.get("id")) for x in groups],
        "permissions": result,
    }
    if output == "json":
        click.echo(__import__("json").dumps(payload, sort_keys=True))
    else:
        click.echo(f"Permission Check: {space_name} ({space_key})")
        for item in result:
            if not only_missing or item["has_permission"] is not True:
                click.echo(
                    f"  {item['operation']}: {'Yes' if item['has_permission'] is True else 'No' if item['has_permission'] is False else 'Unknown'}"
                )
