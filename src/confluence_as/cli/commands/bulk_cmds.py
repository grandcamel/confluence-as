"""Bulk wrapper verbs implemented solely through the generic operation surface."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn

import click
from as_engine.surface import Surface

from confluence_as.engine import create_surface

CHECKPOINT_VERSION = 1


def _surface() -> Surface:
    return create_surface()


def _json(value: Any) -> None:
    click.echo(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _fail(message: str) -> NoReturn:
    raise click.UsageError(message)


def _labels(value: str) -> list[str]:
    result = [x.strip() for x in value.split(",") if x.strip()]
    if not result:
        _fail("At least one label is required")
    return result


def _search(surface: Surface, cql: str, maximum: int) -> list[dict[str, Any]]:
    response = surface.call(
        "searchByCQL",
        {"cql": cql, "limit": min(maximum, 25)},
        all_pages=True,
        limit=maximum,
    )
    body = response.body
    rows = (
        body
        if isinstance(body, list)
        else body.get("results", [])
        if isinstance(body, dict)
        else []
    )
    return [row.get("content", row) for row in rows if isinstance(row, dict)]


def _checkpoint(
    path: Path, command: str, arguments: dict[str, Any], targets: list[str]
) -> dict[str, Any]:
    if path.exists():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _fail(f"Invalid checkpoint: {exc}")
        if not isinstance(value, dict) or value.get("version") != CHECKPOINT_VERSION:
            _fail("Unsupported checkpoint version")
        if value.get("command") != command or value.get("arguments") != arguments:
            _fail("Checkpoint command identity does not match this invocation")
        original, done, failures = (
            value.get("targets"),
            value.get("done"),
            value.get("failures"),
        )
        if (
            not isinstance(original, list)
            or not isinstance(done, list)
            or not isinstance(failures, dict)
            or not all(isinstance(item, str) for item in [*original, *done])
            or len(set(original)) != len(original)
            or len(set(done)) != len(done)
            or not set(done) <= set(original)
            or not all(isinstance(key, str) and key in original for key in failures)
        ):
            _fail("Malformed checkpoint targets, done IDs, or failures")
        current = set(targets)
        original_set = set(original)
        unresolved = original_set - set(done)
        if not current <= original_set or not unresolved <= current:
            _fail("Checkpoint targets do not match unresolved targets")
        return value
    return {
        "version": CHECKPOINT_VERSION,
        "command": command,
        "arguments": arguments,
        "targets": targets,
        "done": [],
        "failures": {},
    }


def _write_checkpoint(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _run(
    *,
    command: str,
    cql: str,
    maximum: int,
    dry_run: bool,
    yes: bool,
    checkpoint: Path | None,
    arguments: dict[str, Any],
    operations: list[str],
    details: dict[str, Any],
    mutate: Callable[[Surface, dict[str, Any]], object],
) -> None:
    surface = _surface()
    pages = _search(surface, cql, maximum)
    if dry_run:
        _json(
            {
                "dryRun": True,
                "command": command,
                "cql": cql,
                "operations": operations,
                "targets": [
                    {
                        "id": str(p.get("id")),
                        "title": p.get("title"),
                        "intendedOperations": operations,
                    }
                    for p in pages
                ],
                **details,
            }
        )
        return
    if not pages:
        _json(
            {"command": command, "total": 0, "success": 0, "failed": 0, "failures": []}
        )
        return
    if not yes and not click.confirm(
        f"Apply {command} to {len(pages)} page(s)?", default=False
    ):
        click.echo("Cancelled.")
        return
    targets = [str(p.get("id")) for p in pages]
    record = (
        _checkpoint(checkpoint, command, arguments, targets) if checkpoint else None
    )
    done = set(record["done"]) if record else set()
    failures: list[dict[str, str]] = []
    for page in pages:
        page_id = str(page.get("id"))
        if page_id in done:
            continue
        try:
            mutate(surface, page)
        except Exception as exc:
            failures.append(
                {"id": page_id, "title": str(page.get("title", "")), "error": str(exc)}
            )
            if record is not None and checkpoint is not None:
                record["failures"][page_id] = str(exc)
                _write_checkpoint(checkpoint, record)
            continue
        if record is not None and checkpoint is not None:
            record["done"].append(page_id)
            record["failures"].pop(page_id, None)
            _write_checkpoint(checkpoint, record)
    _json(
        {
            "command": command,
            "total": len(pages),
            "success": len(record["done"]) if record else len(pages) - len(failures),
            "failed": len(failures),
            "failures": failures,
        }
    )
    if failures:
        raise click.exceptions.Exit(1)


def _common(function):
    function = click.option("--checkpoint", type=click.Path(path_type=Path))(function)
    function = click.option("--resume", is_flag=True)(function)
    function = click.option("--yes", is_flag=True)(function)
    function = click.option("--dry-run", is_flag=True)(function)
    function = click.option(
        "--max-pages", type=click.IntRange(1, 1000), default=100, show_default=True
    )(function)
    return click.option("--cql", required=True)(function)


def _check_resume(path: Path | None, resume: bool) -> None:
    if resume and path is None:
        _fail("--resume requires --checkpoint")


@click.group()
def bulk() -> None:
    """Apply a decision and loop across CQL-selected pages."""


@bulk.group(invoke_without_command=True)
@click.option("--cql")
@click.option("--add")
@click.option("--remove")
@click.option("--dry-run", is_flag=True)
@click.option("--max-pages", type=click.IntRange(1, 1000), default=100)
@click.option("--checkpoint", type=click.Path(path_type=Path))
@click.option("--resume", is_flag=True)
@click.pass_context
def label(
    ctx: click.Context,
    cql: str | None,
    add: str | None,
    remove: str | None,
    dry_run: bool,
    max_pages: int,
    checkpoint: Path | None,
    resume: bool,
) -> None:
    """Add or remove labels; --add/--remove are compact aliases."""
    if ctx.invoked_subcommand is not None:
        return
    if not cql or bool(add) == bool(remove):
        _fail("Supply exactly one of --add and --remove with --cql")
    _check_resume(checkpoint, resume)
    _run_label(
        cql,
        add or remove or "",
        adding=bool(add),
        dry_run=dry_run,
        yes=True,
        maximum=max_pages,
        checkpoint=checkpoint,
    )


def _run_label(
    cql: str,
    labels: str,
    *,
    adding: bool,
    dry_run: bool,
    yes: bool,
    maximum: int,
    checkpoint: Path | None,
) -> None:
    names = _labels(labels)
    operation = "addLabelsToContent" if adding else "removeLabelFromContent"
    command = "bulk label add" if adding else "bulk label remove"

    def mutate(surface: Surface, page: dict[str, Any]) -> None:
        for name in names:
            if adding:
                surface.call(operation, {"id": str(page["id"])}, [{"name": name}])
            else:
                surface.call(operation, {"id": str(page["id"]), "label": name})

    _run(
        command=command,
        cql=cql,
        maximum=maximum,
        dry_run=dry_run,
        yes=yes,
        checkpoint=checkpoint,
        arguments={"cql": cql, "labels": names},
        operations=[operation],
        details={"labels": names},
        mutate=mutate,
    )


@label.command("add")
@_common
@click.option("--labels", "labels", "-l", required=True)
def bulk_label_add(
    cql: str,
    labels: str,
    dry_run: bool,
    yes: bool,
    max_pages: int,
    checkpoint: Path | None,
    resume: bool,
) -> None:
    _check_resume(checkpoint, resume)
    _run_label(
        cql,
        labels,
        adding=True,
        dry_run=dry_run,
        yes=yes,
        maximum=max_pages,
        checkpoint=checkpoint,
    )


@label.command("remove")
@_common
@click.option("--labels", "labels", "-l", required=True)
def bulk_label_remove(
    cql: str,
    labels: str,
    dry_run: bool,
    yes: bool,
    max_pages: int,
    checkpoint: Path | None,
    resume: bool,
) -> None:
    _check_resume(checkpoint, resume)
    _run_label(
        cql,
        labels,
        adding=False,
        dry_run=dry_run,
        yes=yes,
        maximum=max_pages,
        checkpoint=checkpoint,
    )


@bulk.command("delete")
@_common
def bulk_delete(
    cql: str,
    dry_run: bool,
    yes: bool,
    max_pages: int,
    checkpoint: Path | None,
    resume: bool,
) -> None:
    _check_resume(checkpoint, resume)
    _run(
        command="bulk delete",
        cql=cql,
        maximum=max_pages,
        dry_run=dry_run,
        yes=yes,
        checkpoint=checkpoint,
        arguments={"cql": cql},
        operations=["deletePage"],
        details={},
        mutate=lambda s, p: s.call("deletePage", {"id": int(p["id"])}),
    )


@bulk.command("move")
@_common
@click.option("--target-parent")
@click.option("--target-space")
def bulk_move(
    cql: str,
    dry_run: bool,
    yes: bool,
    max_pages: int,
    checkpoint: Path | None,
    resume: bool,
    target_parent: str | None,
    target_space: str | None,
) -> None:
    _check_resume(checkpoint, resume)
    if target_space:
        _fail(
            "--target-space is unavailable: indexed updatePage explicitly forbids cross-space moves"
        )
    if not target_parent:
        _fail("--target-parent is required")
    _run(
        command="bulk move",
        cql=cql,
        maximum=max_pages,
        dry_run=dry_run,
        yes=yes,
        checkpoint=checkpoint,
        arguments={"cql": cql, "target_parent": target_parent},
        operations=["movePage"],
        details={"targetParent": target_parent},
        mutate=lambda s, p: s.call(
            "movePage",
            {"pageId": str(p["id"]), "position": "append", "targetId": target_parent},
        ),
    )


@bulk.command("permission")
@_common
@click.option("--add-group")
@click.option("--remove-group")
@click.option("--add-user")
@click.option("--remove-user")
def bulk_permission(
    cql: str,
    dry_run: bool,
    yes: bool,
    max_pages: int,
    checkpoint: Path | None,
    resume: bool,
    add_group: str | None,
    remove_group: str | None,
    add_user: str | None,
    remove_user: str | None,
) -> None:
    _check_resume(checkpoint, resume)
    changes = {
        "addGroup": add_group,
        "removeGroup": remove_group,
        "addUser": add_user,
        "removeUser": remove_user,
    }
    if not any(changes.values()):
        _fail("Supply at least one permission change")
    operations = [
        n
        for n, v in (
            ("addGroupToContentRestrictionByGroupId", add_group),
            ("removeGroupFromContentRestriction", remove_group),
            ("addUserToContentRestriction", add_user),
            ("removeUserFromContentRestriction", remove_user),
        )
        if v
    ]

    def mutate(s: Surface, p: dict[str, Any]) -> None:
        base = {"id": str(p["id"]), "operationKey": "read"}
        if add_group:
            s.call(
                "addGroupToContentRestrictionByGroupId", {**base, "groupId": add_group}
            )
        if remove_group:
            s.call(
                "removeGroupFromContentRestriction", {**base, "groupId": remove_group}
            )
        if add_user:
            s.call("addUserToContentRestriction", {**base, "accountId": add_user})
        if remove_user:
            s.call(
                "removeUserFromContentRestriction", {**base, "accountId": remove_user}
            )

    _run(
        command="bulk permission",
        cql=cql,
        maximum=max_pages,
        dry_run=dry_run,
        yes=yes,
        checkpoint=checkpoint,
        arguments={"cql": cql, **changes},
        operations=operations,
        details={"changes": changes},
        mutate=mutate,
    )


@bulk.command("update")
@_common
@click.option("--title-prefix")
@click.option("--title-suffix")
def bulk_update(
    cql: str,
    dry_run: bool,
    yes: bool,
    max_pages: int,
    checkpoint: Path | None,
    resume: bool,
    title_prefix: str | None,
    title_suffix: str | None,
) -> None:
    _check_resume(checkpoint, resume)
    if not title_prefix and not title_suffix:
        _fail("Supply --title-prefix and/or --title-suffix")

    def mutate(s: Surface, p: dict[str, Any]) -> None:
        current = s.call("getPageById", {"id": int(p["id"])}).body
        title = (
            (title_prefix or "") + str(current.get("title", "")) + (title_suffix or "")
        )
        body = current.get("body") or {"representation": "storage", "value": ""}
        if isinstance(body, dict) and "storage" in body:
            body = body["storage"]
        s.call(
            "updatePage",
            {"id": int(p["id"])},
            {
                "id": str(p["id"]),
                "status": "current",
                "title": title,
                "body": body,
                "version": {
                    "number": int(current.get("version", {}).get("number", 1)) + 1
                },
            },
        )

    _run(
        command="bulk update",
        cql=cql,
        maximum=max_pages,
        dry_run=dry_run,
        yes=yes,
        checkpoint=checkpoint,
        arguments={
            "cql": cql,
            "titlePrefix": title_prefix,
            "titleSuffix": title_suffix,
        },
        operations=["getPageById", "updatePage"],
        details={"titlePrefix": title_prefix, "titleSuffix": title_suffix},
        mutate=mutate,
    )
