"""Template commands - CLI-only implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from confluence_as import (
    ValidationError,
    engine,
    format_json,
    format_table,
    handle_errors,
    print_success,
    validate_limit,
    validate_space_key,
)
from confluence_as.cli.cli_utils import resolve_output_default
from confluence_as.cli.legacy import command_errors


@click.group()
def template() -> None:
    """Manage page templates."""
    pass


@template.command(name="list")
@click.option("--space", "-s", help="Limit to specific space")
@click.option(
    "--type",
    "-t",
    "template_type",
    type=click.Choice(["page", "blogpost"]),
    help="Template type (page or blogpost)",
)
@click.option("--blueprints", is_flag=True, help="List blueprints instead of templates")
@click.option(
    "--limit", "-l", type=int, default=100, help="Maximum templates to return"
)
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
def list_templates(
    ctx: click.Context,
    space: str | None,
    template_type: str | None,
    blueprints: bool,
    limit: int,
    output: str,
) -> None:
    """List available templates."""
    if space:
        space = validate_space_key(space)

    limit = validate_limit(limit, max_value=250)

    surface = engine.create_surface()

    if blueprints:
        params: dict[str, Any] = {"limit": min(limit, 25)}
        if space:
            params["spaceKey"] = space
        templates = surface.call(
            "getBlueprintTemplates", params, all_pages=True, limit=limit
        ).body
    else:
        params = {"limit": min(limit, 25)}
        if space:
            params["spaceKey"] = space
        templates = surface.call(
            "getContentTemplates", params, all_pages=True, limit=limit
        ).body
    if template_type:
        templates = [
            t for t in templates if t.get("templateType", "").lower() == template_type
        ]

    if output == "json":
        click.echo(
            format_json(
                {
                    "space": space,
                    "type": "blueprints" if blueprints else "templates",
                    "templates": templates,
                    "count": len(templates),
                }
            )
        )
    else:
        title = "Blueprints" if blueprints else "Templates"
        click.echo(f"\n{title}")
        if space:
            click.echo(f"Space: {space}")
        click.echo(f"{'=' * 60}\n")

        if not templates:
            click.echo(f"No {title.lower()} found.")
        else:
            data = []
            for tmpl in templates:
                data.append(
                    {
                        "id": tmpl.get("templateId", tmpl.get("id", ""))[:20],
                        "name": tmpl.get("name", tmpl.get("title", ""))[:35],
                        "type": tmpl.get("templateType", "page")[:10],
                        "space": tmpl.get("_expandable", {}).get("space", "global")[
                            -10:
                        ],
                    }
                )

            click.echo(
                format_table(
                    data,
                    columns=["id", "name", "type", "space"],
                    headers=["ID", "Name", "Type", "Space"],
                )
            )

    if output != "json":
        print_success(f"Found {len(templates)} template(s)")


@template.command(name="create-from")
@click.option("--template", "template_id", help="Template ID to use")
@click.option(
    "--blueprint",
    "blueprint_id",
    help="Blueprint ID to use (alternative to --template)",
)
@click.option("--space", "-s", required=True, help="Space key for the new page")
@click.option("--title", required=True, help="Title for the new page")
@click.option("--parent-id", help="Parent page ID")
@click.option("--labels", help="Comma-separated labels to add")
@click.option("--content", help="Custom content (overrides template)")
@click.option(
    "--file",
    "content_file",
    type=click.Path(exists=True, path_type=Path),  # type: ignore[type-var]
    help="File with custom content",
)
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
def create_from_template(
    ctx: click.Context,
    template_id: str | None,
    blueprint_id: str | None,
    space: str,
    title: str,
    parent_id: str | None,
    labels: str | None,
    content: str | None,
    content_file: Path | None,
    output: str,
) -> None:
    """Create a page from a template."""
    space = validate_space_key(space)

    if not template_id and not blueprint_id:
        raise ValidationError("Either --template or --blueprint is required")
    if template_id and blueprint_id:
        raise ValidationError("Cannot specify both --template and --blueprint")
    if blueprint_id:
        raise ValueError(
            "Blueprint application is not supported by an indexed operation"
        )
    if content and content_file:
        raise ValidationError("Cannot specify both --content and --file")

    surface = engine.create_surface()

    # Get template content if not overriding
    body_content = content
    stored_body = False
    if content_file:
        body_content = content_file.read_text(encoding="utf-8")

    if not body_content:
        if template_id:
            tmpl = surface.call(
                "getContentTemplate", {"contentTemplateId": template_id}
            ).body
            storage = tmpl.get("body", {}).get("storage", {})
            body_content = {
                "representation": "storage",
                "value": storage.get("value", "") if isinstance(storage, dict) else "",
            }
            stored_body = True

    # Build page data for v2 API
    page_data: dict[str, Any] = {
        "title": title,
        "status": "current",
        "body": body_content
        if not stored_body
        else body_content or {"representation": "storage", "value": ""},
    }

    if parent_id:
        page_data["parentId"] = parent_id

    # Create page
    result = surface.call(
        "createPage",
        {},
        page_data,
        aliases={"space-key": space},
        scope_argv_identity=space,
        raw=True,
    ).body

    new_page_id = result.get("id")

    # Add labels if specified
    if labels and new_page_id:
        label_list = [{"name": lbl.strip()} for lbl in labels.split(",") if lbl.strip()]
        if label_list:
            surface.call("addLabelsToContent", {"id": new_page_id}, label_list)

    if output == "json":
        click.echo(
            format_json(
                {
                    "page": result,
                    "templateId": template_id,
                    "blueprintId": blueprint_id,
                }
            )
        )
    else:
        click.echo("\nPage created from template")
        click.echo(f"  ID: {new_page_id}")
        click.echo(f"  Title: {title}")
        click.echo(f"  Space: {space}")
        if template_id:
            click.echo(f"  Template: {template_id}")
        if blueprint_id:
            click.echo(f"  Blueprint: {blueprint_id}")

    if output != "json":
        print_success(f"Created page '{title}' from template in space {space}")
