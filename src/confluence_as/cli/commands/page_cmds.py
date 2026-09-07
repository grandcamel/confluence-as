"""Page management commands - CLI-only implementation."""

from __future__ import annotations

from typing import Any

import click

from confluence_as import (
    ValidationError,
    engine,
    format_json,
    format_page,
    handle_errors,
    print_info,
    print_success,
    validate_page_id,
    validate_space_key,
    validate_title,
)
from confluence_as.cli.cli_utils import resolve_output_default
from confluence_as.cli.legacy import command_errors


def _copy_children(
    surface: Any,
    children: list[dict[str, Any]],
    target_parent_id: str,
    target_space_key: str,
    *,
    quiet: bool,
) -> None:
    """Copy an already-read source subtree without observing destination writes."""
    for child in children:
        child_title = child.get("title", "Untitled")
        child_copy_data = {
            "status": child.get("status", "current"),
            "title": child_title,
            "parentId": target_parent_id,
            "body": child.get("body", {}).get("storage", child.get("body", {})),
        }
        new_child = surface.call(
            "createPage",
            {},
            child_copy_data,
            aliases={"space-key": target_space_key},
            scope_argv_identity=target_space_key,
            raw=True,
        ).body

        if not quiet:
            print_info(f"  Copied child: {child_title}")
        _copy_children(
            surface,
            child["children"],
            new_child["id"],
            target_space_key,
            quiet=quiet,
        )


@click.group()
def page() -> None:
    """Manage Confluence pages and blog posts."""
    pass


@page.command(name="copy")
@click.argument("page_id")
@click.option("--title", "-t", help="New page title (default: 'Copy of [original]')")
@click.option("--space", "-s", help="Target space key")
@click.option("--parent", "-p", "parent_id", help="Target parent page ID")
@click.option("--include-children", is_flag=True, help="Copy child pages recursively")
@click.option(
    "--output",
    "-o",
    type=click.Choice(["text", "json"]),
    default=None,
    callback=resolve_output_default,
    help="Output format",
)
@click.pass_context
@handle_errors
@command_errors
def copy_page(
    ctx: click.Context,
    page_id: str,
    title: str | None,
    space: str | None,
    parent_id: str | None,
    include_children: bool,
    output: str,
) -> None:
    """Copy a Confluence page."""
    source_page_id = validate_page_id(page_id)

    if parent_id:
        parent_id = validate_page_id(parent_id, field_name="parent")

    surface = engine.create_surface()
    source_page = surface.call(
        "getPageById", {"id": source_page_id, "body-format": "storage"}, raw=True
    ).body

    source_title = source_page.get("title", "Untitled")
    source_space_id = source_page.get("spaceId")
    if not source_space_id:
        raise ValidationError("Source page has no space ID")

    if title:
        new_title = validate_title(title)
    else:
        new_title = f"Copy of {source_title}"

    source_space = surface.call("getSpaceById", {"id": source_space_id}).body
    target_space_key = source_space["key"]
    if space:
        target_space_key = validate_space_key(space)

    def snapshot(parent: str, seen: set[str] | None = None) -> list[dict[str, Any]]:
        seen = set() if seen is None else seen
        if parent in seen:
            raise ValidationError("Source hierarchy contains a cycle")
        seen.add(parent)
        result = []
        for child in surface.call("getChildPages", {"id": parent}, all_pages=True).body:
            full_child = surface.call(
                "getPageById", {"id": child["id"], "body-format": "storage"}, raw=True
            ).body
            result.append({**full_child, "children": snapshot(child["id"], seen)})
        return result

    source_tree = snapshot(source_page_id) if include_children or parent_id else []
    source_ids = {source_page_id}

    def add_ids(nodes: list[dict[str, Any]]) -> None:
        for node in nodes:
            source_ids.add(node["id"])
            add_ids(node["children"])

    add_ids(source_tree)
    if parent_id and parent_id in source_ids:
        raise ValidationError(
            "Target parent cannot be the source page or one of its descendants"
        )

    copy_data: dict[str, Any] = {
        "status": source_page.get("status", "current"),
        "title": new_title,
        "body": source_page.get("body", {}).get("storage", source_page.get("body", {})),
    }

    if parent_id:
        copy_data["parentId"] = parent_id

    if output != "json":
        print_info(f"Copying page '{source_title}' to '{new_title}'...")

    result = surface.call(
        "createPage",
        {},
        copy_data,
        aliases={"space-key": target_space_key},
        scope_argv_identity=target_space_key,
        raw=True,
    ).body

    if include_children:
        if output != "json":
            print_info("Copying child pages...")
        _copy_children(
            surface, source_tree, result["id"], target_space_key, quiet=output == "json"
        )

    if output == "json":
        click.echo(format_json(result))
    else:
        click.echo(format_page(result))

    if output != "json":
        print_success(f"Copied page to '{new_title}' with ID {result['id']}")


# Blog post commands
@page.group(name="blog")
def blog() -> None:
    """Manage blog posts."""
    pass
