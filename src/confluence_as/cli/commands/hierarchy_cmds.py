"""Hierarchy management commands - CLI-only implementation."""

from __future__ import annotations

from typing import Any

import click

from confluence_as import (
    ValidationError,
    engine,
    format_json,
    format_table,
    handle_errors,
    print_success,
    validate_page_id,
)
from confluence_as.cli.cli_utils import resolve_output_default
from confluence_as.cli.legacy import command_errors


@click.group()
def hierarchy() -> None:
    """Navigate content hierarchy."""
    pass


@hierarchy.command(name="tree")
@click.argument("page_id")
@click.option(
    "--max-depth", "-d", type=int, help="Maximum depth to traverse (default: unlimited)"
)
@click.option("--stats", is_flag=True, help="Show tree statistics")
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
def get_page_tree(
    ctx: click.Context,
    page_id: str,
    max_depth: int | None,
    stats: bool,
    output: str,
) -> None:
    """Display page tree structure."""
    page_id = validate_page_id(page_id)

    surface = engine.create_surface()
    page = surface.call("getPageById", {"id": page_id}, raw=True).body
    page_title = page.get("title", "Unknown")

    # Build tree structure
    def build_tree(parent_id: str, current_depth: int = 0) -> list[dict[str, Any]]:
        if max_depth is not None and current_depth >= max_depth:
            return []

        tree = []
        children = surface.call("getChildPages", {"id": parent_id}, all_pages=True).body
        for child in children:
            node = {
                "id": child.get("id", ""),
                "title": child.get("title", ""),
                "depth": current_depth + 1,
                "children": build_tree(child["id"], current_depth + 1),
            }
            tree.append(node)
        return tree

    tree = build_tree(page_id)

    # Calculate stats if requested
    tree_stats = None
    if stats:

        def count_nodes(nodes: list[dict[str, Any]]) -> tuple[int, int]:
            total = len(nodes)
            max_d = 0
            for node in nodes:
                children = node.get("children", [])
                if children:
                    child_count, child_depth = count_nodes(children)
                    total += child_count
                    max_d = max(max_d, child_depth)
            return total, max_d + 1 if nodes else 0

        total_pages, max_tree_depth = count_nodes(tree)
        tree_stats = {
            "totalPages": total_pages,
            "maxDepth": max_tree_depth,
            "rootChildren": len(tree),
        }

    if output == "json":
        result: dict[str, Any] = {
            "root": {"id": page_id, "title": page_title},
            "tree": tree,
        }
        if tree_stats:
            result["stats"] = tree_stats
        click.echo(format_json(result))
    else:
        click.echo(f"\nPage Tree: {page_title} ({page_id})")
        click.echo(f"{'=' * 60}\n")

        def print_tree(nodes: list[dict[str, Any]], prefix: str = "") -> None:
            for i, node in enumerate(nodes):
                is_last = i == len(nodes) - 1
                connector = "└── " if is_last else "├── "
                click.echo(f"{prefix}{connector}{node['title']} ({node['id']})")

                children = node.get("children", [])
                if children:
                    extension = "    " if is_last else "│   "
                    print_tree(children, prefix + extension)

        click.echo(f"{page_title} (root)")
        print_tree(tree)

        if tree_stats:
            click.echo(f"\n{'=' * 60}")
            click.echo("Statistics:")
            click.echo(f"  Total pages: {tree_stats['totalPages']}")
            click.echo(f"  Max depth: {tree_stats['maxDepth']}")
            click.echo(f"  Root children: {tree_stats['rootChildren']}")

    if output != "json":
        print_success("Tree generated successfully")


@hierarchy.command(name="reorder")
@click.argument("parent_id")
@click.argument("order", required=False)
@click.option("--reverse", is_flag=True, help="Reverse current order")
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
def reorder_children(
    ctx: click.Context,
    parent_id: str,
    order: str | None,
    reverse: bool,
    output: str,
) -> None:
    """Reorder child pages under a parent.

    ORDER is a comma-separated list of child page IDs in the desired order.
    If not provided, children will be sorted alphabetically by title.

    Examples:
        confluence hierarchy reorder 12345 "111,222,333"
        confluence hierarchy reorder 12345 --reverse
    """
    parent_id = validate_page_id(parent_id)

    surface = engine.create_surface()
    page = surface.call("getPageById", {"id": parent_id}, raw=True).body
    page_title = page.get("title", "Unknown")

    # Get current children
    children = surface.call("getChildPages", {"id": parent_id}, all_pages=True).body

    if not children:
        raise ValidationError(f"No child pages found under {page_title}")

    # Determine new order
    if order:
        # Use provided order
        order_ids = [id.strip() for id in order.split(",")]

        # Validate all IDs exist
        child_ids = {c["id"] for c in children}
        invalid_ids = [id for id in order_ids if id not in child_ids]
        if invalid_ids:
            raise ValidationError(f"Invalid child IDs: {', '.join(invalid_ids)}")

        # Add any missing IDs at the end
        missing_ids = [c["id"] for c in children if c["id"] not in order_ids]
        final_order = order_ids + missing_ids
    else:
        # Sort alphabetically or reverse
        sorted_children = sorted(children, key=lambda c: c.get("title", "").lower())
        if reverse:
            sorted_children.reverse()
        final_order = [c["id"] for c in sorted_children]

    # Apply reordering using v1 API (v2 doesn't have reorder endpoint)
    # Note: The v1 API endpoint for reordering is:
    # PUT /rest/api/content/{id}/child/page/move
    # However, this requires specific positioning operations

    # For now, we'll report the new order - actual reordering
    # requires multiple API calls with position operations
    reordered = []
    for page_id_item in final_order:
        for child in children:
            if child["id"] == page_id_item:
                reordered.append(child)
                break

    if output == "json":
        click.echo(
            format_json(
                {
                    "parent": {"id": parent_id, "title": page_title},
                    "newOrder": [
                        {"id": c["id"], "title": c["title"]} for c in reordered
                    ],
                }
            )
        )
    else:
        click.echo(f"\nNew order for children of: {page_title} ({parent_id})")
        click.echo(f"{'=' * 60}\n")

        data = []
        for i, child in enumerate(reordered, 1):
            data.append(
                {
                    "position": i,
                    "id": child.get("id", ""),
                    "title": child.get("title", "")[:40],
                }
            )

        click.echo(
            format_table(
                data,
                columns=["position", "id", "title"],
                headers=["#", "ID", "Title"],
            )
        )

        click.echo("\nNote: Use Confluence UI to apply actual reordering.")

    if output != "json":
        print_success(f"Calculated new order for {len(reordered)} child page(s)")
