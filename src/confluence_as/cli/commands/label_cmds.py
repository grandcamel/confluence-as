"""Label management commands - CLI-only implementation."""

from __future__ import annotations

import click

from confluence_as import (
    ValidationError,
    engine,
    format_json,
    format_table,
    print_success,
    validate_limit,
    validate_space_key,
)
from confluence_as.cli.cli_utils import (
    resolve_output_default,
)
from confluence_as.cli.legacy import command_errors as handle_errors


@click.group()
def label() -> None:
    """Manage content labels."""
    pass


@label.command(name="popular")
@click.option("--space", "-s", help="Limit to specific space")
@click.option("--limit", "-l", type=int, default=25, help="Maximum labels to return")
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
def list_popular_labels(
    ctx: click.Context,
    space: str | None,
    limit: int,
    output: str,
) -> None:
    """List popular labels."""
    if space:
        space = validate_space_key(space)

    limit = validate_limit(limit, max_value=100)

    client = engine.create_surface()

    # Use v1 API for label statistics

    if space:
        # Get space info first
        spaces = list(client.call("getSpaces", {"keys": [space]}, all_pages=True).body)
        if not spaces:
            raise ValidationError(f"Space not found: {space}")

        # Get labels from space pages
        # Note: This is a simplified implementation
        # A full implementation would aggregate labels from space content
        cql = f'space = "{space}" AND type = page'
        results = list(
            client.call(
                "searchByCQL",
                {"cql": cql, "expand": "content.metadata.labels", "limit": 100},
                all_pages=True,
            ).body
        )

        # Aggregate labels
        label_counts: dict[str, int] = {}
        for r in results:
            content = r.get("content", {})
            labels = content.get("metadata", {}).get("labels", {}).get("results", [])
            for label_item in labels:
                name = label_item.get("name", "")
                if name:
                    label_counts[name] = label_counts.get(name, 0) + 1

        # Sort by count
        sorted_labels = sorted(label_counts.items(), key=lambda x: x[1], reverse=True)[
            :limit
        ]
        labels = [{"name": name, "count": count} for name, count in sorted_labels]
    else:
        # Without space filter, we need to use a different approach
        # Get labels from recent content
        results = list(
            client.call(
                "searchByCQL",
                {
                    "cql": "type = page",
                    "expand": "content.metadata.labels",
                    "limit": 200,
                },
                all_pages=True,
            ).body
        )

        label_counts = {}
        for r in results:
            content = r.get("content", {})
            labels_data = (
                content.get("metadata", {}).get("labels", {}).get("results", [])
            )
            for label_item in labels_data:
                name = label_item.get("name", "")
                if name:
                    label_counts[name] = label_counts.get(name, 0) + 1

        sorted_labels = sorted(label_counts.items(), key=lambda x: x[1], reverse=True)[
            :limit
        ]
        labels = [{"name": name, "count": count} for name, count in sorted_labels]

    if output == "json":
        click.echo(
            format_json(
                {
                    "space": space,
                    "labels": labels,
                    "count": len(labels),
                }
            )
        )
    else:
        click.echo("\nPopular Labels")
        if space:
            click.echo(f"Space: {space}")
        click.echo(f"{'=' * 60}\n")

        if not labels:
            click.echo("No labels found.")
        else:
            data = []
            for lbl in labels:
                data.append(
                    {
                        "name": lbl["name"],
                        "count": lbl["count"],
                    }
                )

            click.echo(
                format_table(
                    data,
                    columns=["name", "count"],
                    headers=["Label", "Count"],
                )
            )

    if output != "json":
        print_success(f"Found {len(labels)} popular label(s)")
