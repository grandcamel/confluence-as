"""Reviewed inventory, zero-send migrations, and actual wrapper command coverage."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import click
import pytest
import requests
from as_engine.index import ProductIndexes
from click.testing import CliRunner

from confluence_as import engine
from confluence_as.cli.legacy import MigrationGroup, records, register
from confluence_as.cli.main import cli

ROOT = Path(__file__).parents[1]
ROWS = json.loads((ROOT / "tests/wrapper_verbs.json").read_text())
DROPPED = [row for row in ROWS if row["decision"] == "dropped"]


def compiled_records():
    indexes = ProductIndexes(ROOT / "src/confluence_as/_generated")
    return records([indexes.get("v2"), indexes.get("v1")])


def test_reviewed_count_matches_compiled_renames_docs_and_argv_tree():
    assert len(ROWS) == 108
    assert Counter(row["decision"] for row in ROWS) == {
        "survivor": 36,
        "dropped": 70,
        "deferred": 2,
    }
    assert Counter(row["classification"] for row in ROWS) == {
        "A": 27,
        "B": 63,
        "C": 6,
        "D": 12,
    }
    expected = {row["verb"] for row in ROWS}
    assert len(expected) == 108
    leaves = set()

    def walk(group, path=()):
        ctx = click.Context(group)
        for name in group.list_commands(ctx):
            if not path and name in {"api", "help"}:
                continue
            command = group.get_command(ctx, name)
            if isinstance(command, click.Group):
                walk(command, (*path, name))
            else:
                leaves.add(" ".join((*path, name)))

    walk(cli)
    assert leaves == expected
    actual = compiled_records()
    assert len(actual) == 70
    assert {
        e["group"] + " " + e["verb"]: (e["invocation"], e["operation"]) for e in actual
    } == {row["verb"]: (row["replacement"], row["operation"]) for row in DROPPED}
    lines = (ROOT / "docs/wrapper-verbs.md").read_text().splitlines()
    doc_rows = [
        line.split(" | ")[0][2:]
        for line in lines
        if line.startswith("| ") and line.split(" | ")[0][2:] in expected
    ]
    assert len(doc_rows) == 108 and set(doc_rows) == expected


@pytest.mark.parametrize("row", DROPPED, ids=[row["verb"] for row in DROPPED])
def test_every_removed_verb_fails_with_actionable_json_and_zero_sends(monkeypatch, row):
    def forbidden(*_args, **_kwargs):
        pytest.fail("migration attempted to create a Surface or send HTTP")

    monkeypatch.setattr(engine, "create_surface", forbidden)
    monkeypatch.setattr(requests.Session, "send", forbidden)
    result = CliRunner().invoke(
        cli, [*row["verb"].split(), "old-id", "--obsolete-option", "old-value"]
    )
    assert result.exit_code == 2, (row["verb"], result.output, result.exception)
    assert result.stdout == ""
    value = json.loads(result.stderr)
    assert set(value) == {"status", "messages", "operation", "note"}
    assert value["status"] is None
    assert value["operation"] == row["operation"]
    assert value["messages"] == ["Use " + row["replacement"]]


def test_create_refusal_and_bare_group_are_useful_without_configuration(monkeypatch):
    monkeypatch.delenv("CONFLUENCE_ALLOWED_SPACES", raising=False)
    create = CliRunner().invoke(
        cli, ["page", "create", "--space", "DOCS", "--title", "T"]
    )
    assert create.exit_code == 2 and create.stdout == ""
    assert json.loads(create.stderr)["operation"] == "createPage"
    for group in ("page", "space", "comment", "watch"):
        bare = CliRunner().invoke(cli, [group])
        assert bare.exit_code in (0, 2) and "api call" in bare.output
    help_result = CliRunner().invoke(cli, ["page", "get", "--help"])
    assert help_result.exit_code == 0 and "api call getPageById" in help_result.stdout


def test_product_neutral_registration_validates_shape_collisions_and_notes():
    operation = SimpleNamespace(
        operationId="fetchWidget",
        extensions={
            "x-as-note": "Shared note",
            "x-as-legacy-verbs": [
                {
                    "group": "widget nested",
                    "verb": "get",
                    "invocation": "tool api call fetchWidget",
                }
            ],
        },
    )
    index = SimpleNamespace(operations={"fetchWidget": operation})
    entries = records([index])
    assert entries[0]["note"] == "Shared note"
    root = MigrationGroup("tool")
    register(root, entries)
    result = CliRunner().invoke(root, ["widget", "nested", "get", "--unused"])
    assert (
        result.exit_code == 2
        and json.loads(result.stderr)["operation"] == "fetchWidget"
    )
    with pytest.raises(ValueError, match="conflicts"):
        register(root, entries)
    with pytest.raises(ValueError, match="duplicate"):
        records([index, index])
    operation.extensions["x-as-legacy-verbs"] = [
        {"group": "widget", "verb": "", "invocation": "x"}
    ]
    with pytest.raises(ValueError, match="invalid"):
        records([index])


def test_comment_and_property_missing_tags_are_present_with_exact_lookup_operations():
    index = ProductIndexes(ROOT / "src/confluence_as/_generated").get("v2")
    for operation in (
        "createFooterComment",
        "createInlineComment",
        "updateFooterComment",
        "updateInlineComment",
    ):
        assert index.operations[operation].extensions["x-as-richtext"][0][
            "request"
        ] == {"path": "/body", "shape": "envelope"}
    for operation, lookup in {
        "updateFooterComment": "getFooterCommentById",
        "updateInlineComment": "getInlineCommentById",
        "updatePagePropertyById": "getPageContentPropertiesById",
    }.items():
        version = index.operations[operation].extensions["x-as-version"]
        assert version["operationId"] == lookup
        assert (
            version["responsePath"] == "/version/number" and version["increment"] == 1
        )


@pytest.mark.parametrize(
    "name,parameters",
    [
        ("createFooterComment", {}),
        ("createInlineComment", {}),
        ("updateFooterComment", {"comment-id": 10}),
        ("updateInlineComment", {"comment-id": 10}),
    ],
)
def test_new_comment_tags_convert_markdown_and_inject_update_version(name, parameters):
    from as_engine.transport import Response

    calls = []

    class CommentTransport:
        def call(self, operation, params, body):
            calls.append((operation.operationId, params, body))
            if operation.operationId in (
                "getFooterCommentById",
                "getInlineCommentById",
            ):
                return Response(200, {"id": "10", "version": {"number": 7}})
            return Response(200, body)

    surface = engine.create_surface(transport="responder")
    surface.transport_factory = lambda *_: CommentTransport()
    result = surface.call(name, parameters, {"body": "# Comment"})
    assert result.status == 200
    assert calls[-1][2]["body"] == {
        "representation": "storage",
        "value": "<h1>Comment</h1>",
    }
    if name.startswith("update"):
        assert calls[-1][2]["version"]["number"] == 8
        assert len(calls) == 2
    else:
        assert len(calls) == 1
