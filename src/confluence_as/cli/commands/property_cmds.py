"""Content property commands - CLI-only implementation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from confluence_as import (
    ValidationError,
    engine,
    format_json,
    handle_errors,
    print_success,
    validate_page_id,
)
from confluence_as.cli.cli_utils import resolve_output_default
from confluence_as.cli.legacy import command_errors


@click.group(name="property")
def property_cmd() -> None:
    """Manage content properties (custom metadata)."""
    pass


@property_cmd.command(name="set")
@click.argument("page_id")
@click.argument("key")
@click.option("--value", "-v", help="Property value (string or JSON)")
@click.option(
    "--file",
    "-f",
    "file_path",
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    help="Read value from JSON file",
)
@click.option(
    "--update", is_flag=True, help="Update existing property (fetches current version)"
)
@click.option("--version", type=int, help="Explicit version number for update")
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
def set_property(
    ctx: click.Context,
    page_id: str,
    key: str,
    value: str | None,
    file_path: Path | None,
    update: bool,
    version: int | None,
    output: str,
) -> None:
    """Set a property value."""
    page_id = validate_page_id(page_id)

    if not value and not file_path:
        raise ValidationError("Either --value or --file is required")
    if value and file_path:
        raise ValidationError("Cannot specify both --value and --file")

    if not key:
        raise ValidationError("Property key is required")

    surface = engine.create_surface()
    page = surface.call("getPageById", {"id": page_id}, raw=True).body
    page_title = page.get("title", "Unknown")

    # Parse value
    if file_path:
        content = file_path.read_text(encoding="utf-8")
        try:
            property_value = json.loads(content)
        except json.JSONDecodeError:
            property_value = content
    else:
        # Try to parse as JSON first
        try:
            property_value = json.loads(value or "")
        except json.JSONDecodeError:
            property_value = value

    # Build property data for v2 API
    property_data: dict[str, Any] = {
        "key": key,
        "value": property_value,
    }

    properties = surface.call(
        "getPageContentProperties", {"page-id": page_id}, all_pages=True
    ).body
    existing = next((item for item in properties if item.get("key") == key), None)
    if existing is None:
        result = surface.call(
            "createPageProperty", {"page-id": page_id}, property_data
        ).body
    else:
        result = surface.call(
            "updatePagePropertyById",
            {"page-id": page_id, "property-id": existing["id"]},
            property_data,
            version=version,
        ).body

    if output == "json":
        click.echo(
            format_json(
                {
                    "page": {"id": page_id, "title": page_title},
                    "property": result,
                }
            )
        )
    else:
        click.echo("\nProperty set successfully")
        click.echo(f"  Page: {page_title} ({page_id})")
        click.echo(f"  Key: {key}")
        click.echo(f"  Version: {result.get('version', {}).get('number', 'N/A')}")

        value_preview = result.get("value", {})
        if isinstance(value_preview, dict):
            value_preview = json.dumps(value_preview)[:100]
        click.echo(f"  Value: {str(value_preview)[:100]}")

    action = "Updated" if update else "Set"
    if output != "json":
        print_success(f"{action} property '{key}' on page {page_id}")
