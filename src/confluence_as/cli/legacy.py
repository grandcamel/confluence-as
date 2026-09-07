"""Register migration-only commands from any product's compiled operation indexes."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

import click


def records(indexes: Iterable[Any]) -> list[dict[str, Any]]:
    """Read validated rename records without creating a Surface or transport."""
    result = []
    seen = set()
    for index in indexes:
        for operation in index.operations.values():
            entries = operation.extensions.get("x-as-legacy-verbs", [])
            if not isinstance(entries, list):
                raise ValueError("x-as-legacy-verbs must be an array")
            for entry in entries:
                if not isinstance(entry, dict) or not all(
                    isinstance(entry.get(key), str) and entry[key].strip()
                    for key in ("group", "verb", "invocation")
                ):
                    raise ValueError("invalid legacy verb record")
                key = (entry["group"], entry["verb"])
                if key in seen:
                    raise ValueError(f"duplicate legacy verb: {' '.join(key)}")
                seen.add(key)
                result.append(
                    {
                        **entry,
                        "operation": operation.operationId,
                        "note": entry.get(
                            "note", operation.extensions.get("x-as-note")
                        ),
                    }
                )
    return result


class MigrationGroup(click.Group):
    """A removed group still shows actionable replacement hints."""

    def __init__(self, *args: Any, **kwargs: Any):
        kwargs.setdefault("invoke_without_command", True)
        kwargs.setdefault("no_args_is_help", False)
        kwargs.setdefault("callback", self.show_migrations)
        super().__init__(*args, **kwargs)

    @staticmethod
    @click.pass_context
    def show_migrations(ctx: click.Context) -> None:
        if ctx.invoked_subcommand is None:
            click.echo(ctx.get_help())


def _stub(entry: dict[str, Any]) -> click.Command:
    def fail(**_: Any) -> None:
        click.echo(
            json.dumps(
                {
                    "status": None,
                    "messages": [f"Use {entry['invocation']}"],
                    "operation": entry["operation"],
                    "note": entry["note"],
                },
                ensure_ascii=False,
            ),
            err=True,
        )
        raise click.exceptions.Exit(2)

    return click.Command(
        entry["verb"],
        callback=fail,
        help=f"Removed legacy verb. Use {entry['invocation']}",
        short_help=f"Use {entry['invocation']}",
        context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
    )


def register(
    root: click.Group, entries: Iterable[dict[str, Any]], *, prefix: str = ""
) -> None:
    """Install stubs beneath root; prefix permits lazy loading one product group."""
    for entry in entries:
        path = entry["group"].split()
        if prefix:
            if path[0] != prefix:
                continue
            path = path[1:]
        parent = root
        for name in path:
            child = parent.commands.get(name)
            if child is None:
                child = MigrationGroup(name, help=f"Migration hints for {name}.")
                parent.add_command(child)
            if not isinstance(child, click.Group):
                raise ValueError(f"legacy group conflicts with command: {name}")
            parent = child
        if entry["verb"] in parent.commands:
            raise ValueError(
                f"legacy stub conflicts with surviving command: {entry['verb']}"
            )
        parent.add_command(_stub(entry))


def command_errors(function: Any) -> Any:
    """Keep wrapper failures in the same JSON error contract as generic calls."""
    from functools import wraps

    @wraps(function)
    def invoke(*args: Any, **kwargs: Any) -> Any:
        from as_engine.errors import SurfaceError

        try:
            return function(*args, **kwargs)
        except SurfaceError as exc:
            click.echo(json.dumps(exc.as_dict(), ensure_ascii=False), err=True)
            raise SystemExit(exc.code) from exc
        except (ValueError, OSError) as exc:
            click.echo(
                json.dumps(
                    {
                        "status": None,
                        "messages": [str(exc)],
                        "operation": None,
                        "note": None,
                    }
                ),
                err=True,
            )
            raise SystemExit(2) from exc

    return invoke
