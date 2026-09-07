"""Thin Click adapter for the shared operation surface."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from dataclasses import replace
from typing import Any
from urllib.parse import quote

import click
from as_engine.errors import SurfaceError
from as_engine.help import describe_document, examples_document, render_help
from as_engine.output import render_output
from as_engine.params import alias_flags, body_errors, build_body, validate_parameters
from as_engine.surface import Surface, parse_call_flags

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


def _call_help(operation: Any) -> str:
    """Describe enrichment flags that are available for this operation."""
    lines = [
        "Call options: --body @file|-; --field path=value (repeatable); "
        "--validate-body; --format json|table|markdown.",
        "Arrays: repeat the flag or use a JSON array; booleans: true|false.",
    ]
    tags = operation.extensions
    if "x-as-paging" in tags:
        lines.append(
            "Paging: --all aggregates pages; with --all, --limit is the total item cap; "
            "--parameter-limit sets each response page size."
        )
    aliases = tags.get("x-as-prerequisites", [])
    if isinstance(aliases, list):
        names = [entry.get("alias") for entry in aliases if isinstance(entry, dict)]
        names = [name for name in names if isinstance(name, str) and name]
        if names:
            lines.append(
                "Aliases: " + "; ".join(f"--{name} VALUE" for name in names) + "."
            )
    if "x-as-version" in tags:
        lines.append("Version: --version INTEGER overrides tagged version enrichment.")
    return "\n".join(lines)


def _preview(
    operation: Any,
    index: Any,
    parameters: dict[str, Any],
    body: Any,
    options: dict[str, Any],
) -> dict[str, Any]:
    """Validate local inputs without running lookups, guards or creating a transport."""
    from types import SimpleNamespace

    from as_engine.transforms.values import MISSING, set_target, target_value

    if options["all_pages"] and "x-as-paging" not in operation.extensions:
        raise ValueError("operation has no declared paging contract")
    rules = alias_flags(operation)
    aliases = options["aliases"]
    deferred = {
        rules[key]["target"]["name"]
        for key in aliases
        if rules[key]["target"].get("in") != "body"
    }
    partial = replace(
        operation,
        parameters=[
            {**p, "required": False} if p["name"] in deferred else p
            for p in operation.parameters
        ],
    )
    checked = validate_parameters(partial, parameters, index.schemas)
    payload = deepcopy(body)
    context = SimpleNamespace(
        body=payload, parameters=checked, operation=operation, index=index
    )
    for alias in aliases:
        if target_value(context, rules[alias]["target"]) is not MISSING:
            raise ValueError(f"conflicting id and --{alias}")
    version_tag = operation.extensions.get("x-as-version")
    if options["version"] is not None:
        # Apply only the supplied local value; never read the current version.
        if target_value(context, version_tag["target"]) is not MISSING:
            raise ValueError("conflicting --version and body version")
        set_target(context, version_tag["target"], options["version"])
        payload = context.body
    if options["validate_body"]:
        problems = body_errors(operation, payload, index.schemas)
        if problems:
            raise ValueError("; ".join(problems))
    path = operation.path
    for p in operation.parameters:
        if p["in"] == "path" and p["name"] in checked:
            path = path.replace(
                "{" + p["name"] + "}", quote(str(checked[p["name"]]), safe="")
            )
    result = {
        "dry_run": True,
        "operationId": operation.operationId,
        "risk": operation.extensions["x-as-risk"],
        "method": operation.method,
        "path": path,
        "parameters": checked,
        "body": payload,
    }
    if aliases:
        result["unresolved_aliases"] = dict(aliases)
    if version_tag is not None and options["version"] is None:
        result["version_requirement"] = (
            "An absent version is resolved only after --confirm."
        )
    return result


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
            "[--validate-body] [--confirm] [--format json|table|markdown]\n"
            "Use api call OPERATION --help for parameter flags."
        )
        return
    name = arguments[0]
    surface = _surface(ctx)
    _, index, operation = surface.resolve(name)
    try:
        parameters, options = parse_call_flags(operation, arguments[1:])
        if options["help"] or options["examples"]:
            value = (
                examples_document(operation)
                if options["examples"]
                else describe_document(surface.describe(name, full=options["full"]))
            )
            help_format = (
                options["format"]
                if "--format" in arguments
                or any(arg.startswith("--format=") for arg in arguments)
                else "markdown"
            )
            if not options["examples"]:
                value["sections"].append({"text": _call_help(operation)})
            click.echo(render_help(value, help_format))
            return
        body = build_body(options["body"], options["field"], sys.stdin)
        risk = operation.extensions.get("x-as-risk", "safe")
        if risk not in ("safe", "destructive", "irreversible"):
            raise ValueError("x-as-risk must be safe, destructive or irreversible")
        if risk != "safe" and not options["confirm"]:
            click.echo(
                render_output(_preview(operation, index, parameters, body, options))
            )
            return
        response = surface.call(
            name,
            parameters,
            body,
            validate_body=options["validate_body"],
            all_pages=options["all_pages"],
            limit=options["limit"],
            aliases=options["aliases"],
            version=options["version"],
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
@click.option("--full", is_flag=True)
@click.option("--examples", is_flag=True)
@click.argument("operation")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["markdown", "json"]),
    default="markdown",
)
@click.pass_context
def describe(
    ctx: click.Context, operation: str, output_format: str, full: bool, examples: bool
) -> None:
    """Show parameters, body outline, scope, notes and deprecation."""
    surface = _surface(ctx)
    _, _, op = surface.resolve(operation)
    value = (
        examples_document(op)
        if examples
        else describe_document(surface.describe(operation, full=full))
    )
    click.echo(render_help(value, output_format))


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
