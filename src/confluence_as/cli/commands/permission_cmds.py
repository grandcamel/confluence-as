"""Permission-removal survivor commands on the generic operation surface."""

from __future__ import annotations

import json
from typing import Any

import click
from as_engine.surface import Surface

from confluence_as.cli.cli_utils import resolve_output_default
from confluence_as.cli.legacy import command_errors
from confluence_as.engine import create_surface


def _surface() -> Surface:
    return create_surface()


def _rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    return (
        [x for x in value.get("results", []) if isinstance(x, dict)]
        if isinstance(value, dict)
        else []
    )


def _out(value: Any, output: str) -> None:
    click.echo(json.dumps(value, sort_keys=True) if output == "json" else str(value))


def _group_id(surface: Surface, name: str) -> str:
    groups = _rows(
        surface.call("searchGroups", {"query": name, "limit": 200}, all_pages=True).body
    )
    exact = [x for x in groups if x.get("name") == name]
    if len(exact) != 1:
        raise click.UsageError(
            f"Group must resolve uniquely to an actual groupId: {name}"
        )
    identifier = exact[0].get("id") or exact[0].get("groupId")
    if not identifier:
        raise click.UsageError(f"Group response lacks groupId: {name}")
    return str(identifier)


@click.group()
def permission() -> None:
    """Manage page restrictions and space permissions."""


@permission.group(name="page")
def page_permission() -> None:
    pass


@page_permission.command("remove")
@click.argument("page_id")
@click.option("--user")
@click.option("--group", "group_name")
@click.option("--operation", type=click.Choice(["read", "update"]), required=True)
@click.option("--all", "remove_all", is_flag=True)
@click.option(
    "--output",
    "-o",
    type=click.Choice(["text", "json"]),
    default=None,
    callback=resolve_output_default,
)
@command_errors
def remove_page_restriction(
    page_id: str,
    user: str | None,
    group_name: str | None,
    operation: str,
    remove_all: bool,
    output: str,
) -> None:
    """Remove selected principals, or replace one operation's restriction set."""
    if not (user or group_name or remove_all):
        raise click.UsageError("Specify --user, --group, or --all")
    surface = _surface()
    page = surface.call("getPageById", {"id": int(page_id)}).body
    if remove_all:
        current = surface.call("getRestrictions", {"id": page_id}).body
        rows = _rows(current)
        kept = [x for x in rows if x.get("operation") != operation]
        surface.call("updateRestrictions", {"id": page_id}, {"results": kept})
        removed = ["all"]
    else:
        removed = []
        if user:
            surface.call(
                "removeUserFromContentRestriction",
                {"id": page_id, "operationKey": operation, "accountId": user},
            )
            removed.append(user)
        if group_name:
            group_id = _group_id(surface, group_name)
            surface.call(
                "removeGroupFromContentRestriction",
                {"id": page_id, "operationKey": operation, "groupId": group_id},
            )
            removed.append(group_id)
    _out(
        {
            "page": {"id": page_id, "title": page.get("title")},
            "operation": operation,
            "removed": removed,
        },
        output,
    )


@permission.group(name="space")
def space_permission() -> None:
    pass


@space_permission.command("remove")
@click.argument("space_key")
@click.option("--permission-id", "permission_id")
@click.option("--user")
@click.option("--group", "group_name")
@click.option("--operation")
@click.option(
    "--output",
    "-o",
    type=click.Choice(["text", "json"]),
    default=None,
    callback=resolve_output_default,
)
@command_errors
def remove_space_permission(
    space_key: str,
    permission_id: str | None,
    user: str | None,
    group_name: str | None,
    operation: str | None,
    output: str,
) -> None:
    """Remove a permission directly or after matching its actual assignment."""
    if not permission_id and not user and not group_name:
        raise click.UsageError("Specify --permission-id, --user, or --group")
    if (user or group_name) and not operation:
        raise click.UsageError("--operation is required with --user or --group")
    surface = _surface()
    spaces = _rows(surface.call("getSpaces", {"keys": [space_key]}).body)
    if len(spaces) != 1:
        raise click.UsageError(f"Space not found or ambiguous: {space_key}")
    space = spaces[0]
    removed: list[str] = []
    if permission_id:
        surface.call(
            "removePermission", {"spaceKey": space_key, "id": int(permission_id)}
        )
        removed.append(permission_id)
    else:
        group_id = _group_id(surface, group_name) if group_name else None
        assignments = _rows(
            surface.call(
                "getSpacePermissionsAssignments",
                {"id": int(space["id"])},
                all_pages=True,
            ).body
        )
        for assignment in assignments:
            principal = assignment.get("principal", {})
            actual = assignment.get("operation", {}).get("key")
            wanted = user or group_id
            if actual == operation and principal.get("id") == wanted:
                identifier = str(assignment["id"])
                surface.call(
                    "removePermission", {"spaceKey": space_key, "id": int(identifier)}
                )
                removed.append(identifier)
    _out(
        {
            "space": {"key": space_key, "id": space.get("id")},
            "removedPermissions": removed,
            "count": len(removed),
        },
        output,
    )
