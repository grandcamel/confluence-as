"""Thin Click adapter for the shared operation surface."""

from __future__ import annotations

import json
import sys
from typing import Any

import click
from as_engine.errors import SurfaceError
from as_engine.output import render_output
from as_engine.params import build_body
from as_engine.surface import Surface, describe_markdown, parse_call_flags

from confluence_as.engine import create_surface


def _fail(error: SurfaceError) -> None:
    click.echo(json.dumps(error.as_dict(), ensure_ascii=False), err=True)
    raise click.exceptions.Exit(error.code)


class APIGroup(click.Group):
    """Keep Click usage failures in the API group's JSON error contract."""

    def invoke(self, ctx: click.Context) -> Any:
        try:
            return super().invoke(ctx)
        except SurfaceError as exc:
            _fail(exc)
        except click.ClickException as exc:
            _fail(SurfaceError(None, [exc.format_message()], code=2))
        except (ValueError, OSError) as exc:
            _fail(SurfaceError(None, [str(exc)], code=2))

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        try:
            return super().parse_args(ctx, args)
        except click.ClickException as exc:
            _fail(SurfaceError(None, [exc.format_message()], code=2))
        return []


@click.group(cls=APIGroup)
@click.option(
    "--transport", type=click.Choice(["http", "responder"]), default=None, hidden=True
)
@click.option("--respond-with", type=int, default=200, hidden=True)
@click.pass_context
def api(ctx: click.Context, transport: str | None, respond_with: int) -> None:
    """Call or discover indexed API operations.

    Parameters use spec-derived flags. Call bodies use --body @file, --body -,
    or repeated --field path=value. Use describe for operation details.
    """
    ctx.ensure_object(dict)
    ctx.obj["api_surface"] = create_surface(
        transport=transport, respond_with=respond_with
    )


def _surface(ctx: click.Context) -> Surface:
    return ctx.obj["api_surface"]


@api.command(
    "call", context_settings={"ignore_unknown_options": True}, add_help_option=False
)
@click.argument("arguments", nargs=-1, type=click.UNPROCESSED)
@click.pass_context
def call(ctx: click.Context, arguments: tuple[str, ...]) -> None:
    """Call OPERATION with its spec-derived flags; --help after OPERATION lists them."""
    if not arguments:
        raise SurfaceError(None, ["Missing operationId"], code=2)
    if arguments == ("--help",):
        click.echo(
            "api call OPERATION [--parameter value] [--body @file|-] [--field path=value] "
            "[--validate-body] [--format json|table|markdown]\n"
            "Use api call OPERATION --help for parameter flags."
        )
        return
    name = arguments[0]
    surface = _surface(ctx)
    _, _, operation = surface.resolve(name)
    try:
        parameters, options = parse_call_flags(operation, arguments[1:])
        if options["help"]:
            click.echo(describe_markdown(surface.describe(name)))
            click.echo(
                "\nCall options: --body @file|-; --field path=value (repeatable); "
                "--validate-body; --format json|table|markdown.\n"
                "Arrays: repeat the flag or use a JSON array; booleans: true|false."
            )
            return
        body = build_body(options["body"], options["field"], sys.stdin)
        response = surface.call(
            name,
            parameters,
            body,
            validate_body=options["validate_body"],
            warn=lambda message: click.echo(message, err=True),
        )
        click.echo(render_output(response.body, options["format"]))
    except ValueError as exc:
        raise SurfaceError(
            None,
            [str(exc)],
            operation.operationId,
            operation.extensions.get("x-as-note"),
            code=2,
        ) from exc


@api.command("search")
@click.argument("words", nargs=-1, required=True)
@click.option("--include-deprecated", is_flag=True)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "markdown", "json"]),
    default="table",
)
@click.pass_context
def search(
    ctx: click.Context,
    words: tuple[str, ...],
    include_deprecated: bool,
    output_format: str,
) -> None:
    """Find primary operations by ID, summary, tag, path or note."""
    rows = _surface(ctx).search(words, include_deprecated=include_deprecated)
    click.echo(
        render_output(rows, output_format, ["operationId", "method", "path", "summary"])
    )


@api.command("describe")
@click.argument("operation")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["markdown", "json"]),
    default="markdown",
)
@click.pass_context
def describe(ctx: click.Context, operation: str, output_format: str) -> None:
    """Show parameters, body outline, scope, notes and deprecation."""
    value = _surface(ctx).describe(operation)
    click.echo(
        render_output(value) if output_format == "json" else describe_markdown(value)
    )


@api.command("topics")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["markdown", "json"]),
    default="markdown",
)
@click.pass_context
def topics(ctx: click.Context, output_format: str) -> None:
    """List topics supplied by enrichment."""
    values = _surface(ctx).topics()
    click.echo(
        render_output(values)
        if output_format == "json"
        else "\n".join(values) or "No topics available."
    )
