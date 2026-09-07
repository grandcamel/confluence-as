"""Credential-free help built from product commands and enriched operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click
from as_engine.help import (
    TOPICS,
    document,
    first_paragraph,
    group_document,
    group_examples_document,
    level0,
    render_help,
    topic_document,
    topics_document,
)
from as_engine.index import OperationIndex

from confluence_as.engine import create_surface


def surface_map() -> dict[str, Any]:
    template = Path(__file__).parents[2] / "help_level0.md"
    return level0(template.read_text(encoding="utf-8"))


def _groups(root: click.Group, ctx: click.Context) -> dict[str, list[tuple[str, str]]]:
    groups = {}
    for name in root.list_commands(ctx):
        command = root.get_command(ctx, name)
        if isinstance(command, click.Group):
            groups[name] = [
                (f"{name} {verb}", child.get_short_help_str(limit=160))
                for verb in command.list_commands(ctx)
                if (child := command.get_command(ctx, verb)) is not None
            ]
    return groups


@click.command("help")
@click.argument("subject", required=False)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["markdown", "json"]),
    default="markdown",
)
@click.option("--examples", is_flag=True)
@click.option("--tier", type=click.Choice(["v2", "v1"]), default=None)
@click.option("--offset", type=click.IntRange(min=0), default=0)
@click.pass_context
def help_command(
    ctx: click.Context,
    subject: str | None,
    output_format: str,
    examples: bool,
    tier: str | None,
    offset: int,
) -> None:
    """Show the surface map, a command group, or an enrichment topic."""
    if subject is None and examples:
        subject = "api"
    if subject is None:
        value = surface_map()
    else:
        surface = create_surface(transport="responder")
        indexes = (
            [(tier, surface.indexes.get(tier))]
            if tier
            else [("v1", surface.indexes.get("v1"))]
            if subject == "search"
            else surface.indexes.primary()
        )
        index = OperationIndex(
            {key: op for _, part in indexes for key, op in part.operations.items()},
            {
                key: schema
                for _, part in indexes
                for key, schema in part.schemas.items()
            },
        )
        root = ctx.find_root().command
        assert isinstance(root, click.Group)
        try:
            if subject == "topics":
                value = topics_document(index)
            elif subject in TOPICS or subject in surface.topics():
                value = topic_document(index, subject, examples=examples, offset=offset)
            elif examples:
                value = group_examples_document(index, subject, offset=offset)
            else:
                value = group_document(
                    index, subject, _groups(root, ctx), offset=offset
                )
        except ValueError as exc:
            raise click.UsageError(str(exc)) from exc
    click.echo(render_help(value, output_format))


def wrapper_document(
    command: click.Command, name: str, *, full: bool, examples: bool
) -> dict[str, Any]:
    prose = command.help or ""
    if examples:
        marker = "Examples:"
        example_text = prose.partition(marker)[2].strip()
        return document(
            3,
            name + " examples",
            [{"text": example_text or "No examples supplied by this wrapper."}],
        )
    parameters = []
    for parameter in command.params:
        if isinstance(parameter, click.Option):
            spelling = ", ".join(parameter.opts)
            summary = parameter.help or ""
        else:
            spelling = parameter.name or "argument"
            summary = "argument"
        parameters.append(
            f"`{spelling}`: {summary}" + (" (required)" if parameter.required else "")
        )
    return document(
        2,
        name,
        [
            {"text": prose.strip() if full else first_paragraph(prose)},
            {"title": "Parameters", "items": parameters},
            {
                "text": "Use --help --full for the complete description; --examples for examples."
            },
        ],
    )


class HelpGroup(click.Group):
    """Resolve wrapper help before running any configuration or command callbacks."""

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        # API owns its dynamic operation flags. Standard root/group help stays Click.
        if (
            args
            and args[0] not in {"api", "help"}
            and ("--help" in args or "--examples" in args)
        ):
            command: click.Command = self
            names = []
            remaining = list(args)
            while remaining and isinstance(command, click.Group):
                child = command.get_command(ctx, remaining[0])
                if child is None:
                    break
                names.append(remaining.pop(0))
                command = child
            if names and not isinstance(command, click.Group):
                output_format = "markdown"
                for position, arg in enumerate(remaining):
                    if arg == "--format" and position + 1 < len(remaining):
                        output_format = remaining[position + 1]
                    elif arg.startswith("--format="):
                        output_format = arg.split("=", 1)[1]
                if output_format not in {"markdown", "json"}:
                    raise click.UsageError("help format must be markdown or json")
                value = wrapper_document(
                    command,
                    " ".join(names),
                    full="--full" in remaining,
                    examples="--examples" in remaining,
                )
                click.echo(render_help(value, output_format))
                ctx.exit()
        return super().parse_args(ctx, args)
