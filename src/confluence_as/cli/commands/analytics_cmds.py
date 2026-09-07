"""Analytics commands - CLI-only implementation."""

from __future__ import annotations

from datetime import datetime, timedelta

import click

from confluence_as import (
    engine,
    format_json,
    print_success,
    validate_space_key,
)
from confluence_as.cli.cli_utils import (
    resolve_output_default,
)
from confluence_as.cli.legacy import command_errors as handle_errors


@click.group()
def analytics() -> None:
    """View content analytics."""
    pass


@analytics.command(name="space")
@click.argument("space_key")
@click.option("--days", type=int, help="Limit to content from last N days")
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
def get_space_analytics(
    ctx: click.Context,
    space_key: str,
    days: int | None,
    output: str,
) -> None:
    """Get analytics for a space.

    Shows space statistics including page count, recent activity,
    and contributor information.
    """
    space_key = validate_space_key(space_key)

    client = engine.create_surface()

    # Get space info
    spaces = client.call("getSpaces", {"keys": [space_key]}).body["results"]
    if len(spaces) != 1:
        raise ValueError("Expected one matching space")
    space = spaces[0]
    space_name = space.get("name", space_key)
    space_id = space.get("id")

    # Build date filter
    date_filter = ""
    if days:
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        date_filter = f" AND lastmodified >= {cutoff_date}"

    # Get content counts
    page_cql = f'space = "{space_key}" AND type = page{date_filter}'
    blog_cql = f'space = "{space_key}" AND type = blogpost{date_filter}'

    # Count pages
    list(client.call("searchByCQL", {"cql": page_cql, "limit": 1}, all_pages=True).body)

    # We need to get the total from the search response differently
    # Let's collect samples to estimate
    page_results = []
    for p in client.call(
        "searchByCQL", {"cql": page_cql, "limit": 25}, all_pages=True
    ).body:
        page_results.append(p)
        if len(page_results) >= 200:  # Cap for performance
            break

    blog_results = []
    for b in client.call(
        "searchByCQL", {"cql": blog_cql, "limit": 25}, all_pages=True
    ).body:
        blog_results.append(b)
        if len(blog_results) >= 100:
            break

    # Get recent activity (last 10 modified items)
    recent_cql = f'space = "{space_key}" ORDER BY lastmodified desc'
    recent_items = []
    for item in client.call(
        "searchByCQL", {"cql": recent_cql, "limit": 10}, all_pages=True
    ).body:
        recent_items.append(item)
        if len(recent_items) >= 10:
            break

    # Collect unique contributors
    contributors: set[str] = set()
    for item in page_results + blog_results:
        content = item.get("content", item)
        by = content.get("lastModified", {})
        if isinstance(by, dict) and "by" in by:
            contributors.add(by["by"].get("displayName", "Unknown"))

    analytics_data = {
        "space": {"key": space_key, "name": space_name, "id": space_id},
        "pageCount": len(page_results),
        "blogCount": len(blog_results),
        "totalContent": len(page_results) + len(blog_results),
        "contributorCount": len(contributors),
        "recentItems": recent_items[:10],
    }

    if days:
        analytics_data["dateRange"] = f"Last {days} days"

    if output == "json":
        click.echo(format_json(analytics_data))
    else:
        click.echo(f"\nSpace Analytics: {space_name} ({space_key})")
        if days:
            click.echo(f"Date Range: Last {days} days")
        click.echo(f"{'=' * 60}\n")

        click.echo("Content Summary:")
        click.echo(f"  Pages: {len(page_results)}+")
        click.echo(f"  Blog Posts: {len(blog_results)}+")
        click.echo(f"  Total: {len(page_results) + len(blog_results)}+")
        click.echo(f"  Contributors: {len(contributors)}")

        if recent_items:
            click.echo("\nRecent Activity:")
            for item in recent_items[:5]:
                content = item.get("content", item)
                title = content.get("title", "Untitled")[:40]
                content_type = content.get("type", "page")
                click.echo(f"  - [{content_type}] {title}")

    if output != "json":
        print_success(f"Retrieved analytics for space {space_key}")
