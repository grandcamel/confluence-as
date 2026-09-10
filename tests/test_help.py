"""Help argv snapshots and risk behavior against the responder, never HTTP."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import requests
from as_engine.help import CAPS, TOPICS, render_help, token_estimate
from as_engine.responder import Responder
from as_engine.transport import Response
from click.testing import CliRunner

from confluence_as.cli.commands.help_cmds import help_command
from confluence_as.cli.main import cli


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("CONFLUENCE_AS_TRANSPORT", "responder")

    def forbidden(*args, **kwargs):
        raise AssertionError("HTTP attempted by help tests")

    monkeypatch.setattr(requests.Session, "send", forbidden)


CASES = {
    "level0": ([], "level0"),
    "group": (["help", "api"], "group"),
    "topic": (["help", "adf"], "topic"),
    "paging": (["help", "paging"], "topic"),
    "level2": (["api", "describe", "deletePage"], "level2"),
    "level3": (["api", "describe", "createPage", "--examples"], "level3"),
    "topics": (["help", "topics"], "topics"),
    "wrapper": (["page", "get", "--help"], "level2"),
}


@pytest.mark.parametrize("name", CASES)
def test_golden_help_and_token_cap(name):
    argv, cap = CASES[name]
    result = CliRunner().invoke(cli, argv)
    assert result.exit_code == 0 and result.stderr == "", result.output
    path = Path(__file__).parent / "golden/help" / (name + ".md")
    if os.environ.get("UPDATE_HELP_GOLDEN") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(result.stdout)
    assert result.stdout == path.read_text()
    assert token_estimate(result.stdout) <= CAPS[cap]


def test_bare_help_and_json_have_the_same_content():
    runner = CliRunner()
    bare = runner.invoke(cli, [])
    help_result = runner.invoke(cli, ["help"])
    assert bare.stdout == help_result.stdout
    value = json.loads(runner.invoke(cli, ["help", "--format", "json"]).stdout)
    assert render_help(value) + "\n" == bare.stdout


def test_standalone_help_rejects_a_non_group_root():
    result = CliRunner().invoke(help_command, ["api"])
    assert result.exit_code == 2, result.output
    assert result.stdout == ""
    assert "Error: Help requires a root command group" in result.stderr
    # The supervisor's separate normal/-O probe must check these outcomes with
    # if/raise control flow: Python -O strips test assertions too.


@pytest.mark.parametrize("name", ["group", "topic", "level2", "level3", "wrapper"])
def test_each_help_level_json_roundtrips_to_exact_markdown(name):
    runner = CliRunner()
    args = CASES[name][0]
    markdown = runner.invoke(cli, args)
    result = runner.invoke(cli, [*args, "--format", "json"])
    assert result.exit_code == 0, result.output
    assert render_help(json.loads(result.stdout)) + "\n" == markdown.stdout


def test_every_seed_topic_is_bounded():
    for topic in TOPICS:
        result = CliRunner().invoke(cli, ["help", topic])
        assert result.exit_code == 0, result.output
        assert token_estimate(result.stdout) <= CAPS["topic"], topic
        assert "No entries tagged" not in result.stdout, topic


def test_risky_call_previews_zero_sends_and_confirm_sends_once(monkeypatch):
    calls = []
    original = Responder.call

    def record(self, operation, parameters, body):
        calls.append((operation.operationId, parameters, body))
        return original(self, operation, parameters, body)

    monkeypatch.setattr(Responder, "call", record)
    # JAS-39 landed after this test was written: a confirmed deletePage now passes the
    # scope guard, which needs an allowlist and answers for its two metadata resolution reads.
    monkeypatch.setenv("CONFLUENCE_ALLOWED_SPACES", "DOCS")
    resolution = {
        "getPageById": {"id": "123", "spaceId": "55"},
        "getSpaces": {"results": [{"id": "55", "key": "DOCS"}]},
    }

    def record_with_resolution(self, operation, parameters, body):
        calls.append((operation.operationId, parameters, body))
        if operation.operationId in resolution:
            return Response(200, resolution[operation.operationId])
        return original(self, operation, parameters, body)

    monkeypatch.setattr(Responder, "call", record_with_resolution)
    args = ["api", "call", "deletePage", "--id", "123"]
    runner = CliRunner()
    result = runner.invoke(cli, args)
    assert result.exit_code == 0 and result.stderr == "", result.output
    assert json.loads(result.stdout) == {
        "dry_run": True,
        "operationId": "deletePage",
        "risk": "irreversible",
        "method": "DELETE",
        "path": "/pages/123",
        "parameters": {"id": 123},
        "body": None,
    }
    assert calls == []
    result = runner.invoke(cli, [*args, "--confirm"])
    assert result.exit_code == 0, result.output
    # two metadata resolution reads (JAS-39), then exactly one operation send
    assert [name for name, _, _ in calls[:-1]] == ["getPageById", "getSpaces"]
    assert calls[-1] == ("deletePage", {"id": 123}, None)


def test_destructive_preview_never_runs_version_lookup_or_transport_factory(
    monkeypatch,
):
    from confluence_as.cli.commands import api_cmds
    from confluence_as.engine import create_surface

    surface = create_surface(transport="responder")

    def forbidden(*args, **kwargs):
        raise AssertionError("preview constructed transport")

    surface.transport_factory = forbidden
    monkeypatch.setattr(api_cmds, "create_surface", lambda **kwargs: surface)
    result = CliRunner().invoke(
        cli, ["api", "call", "updatePage", "--id", "123", "--field", "title=Preview"]
    )
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["dry_run"] is True and body["risk"] == "destructive"
    assert body["body"] == {"title": "Preview"} and "version_requirement" in body


@pytest.mark.parametrize("arguments", [["--id", "bad"], []])
def test_invalid_delete_parameters_fail_without_sending(monkeypatch, arguments):
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid preview sent")

    monkeypatch.setattr(Responder, "call", forbidden)
    result = CliRunner().invoke(cli, ["api", "call", "deletePage", *arguments])
    assert result.exit_code == 2 and result.stdout == ""
    assert json.loads(result.stderr)["operation"] == "deletePage"


def test_lower_tier_search_and_space_deletion_are_discoverable():
    runner = CliRunner()
    result = runner.invoke(cli, ["help", "search"])
    assert result.exit_code == 0 and "searchByCQL" in result.stdout, result.output
    result = runner.invoke(cli, ["help", "risk", "--tier", "v1"])
    assert result.exit_code == 0 and "space" in result.stdout.lower(), result.output


def test_wrapper_full_and_examples_do_not_execute_command():
    runner = CliRunner()
    result = runner.invoke(cli, ["page", "get", "--help", "--full"])
    assert result.exit_code == 0 and "page get" in result.stdout
    examples = runner.invoke(cli, ["page", "get", "--examples"])
    assert examples.exit_code == 0 and "examples" in examples.stdout
    assert token_estimate(examples.stdout) <= CAPS["level3"]


def test_every_primary_operation_detail_and_example_fits_its_cap():
    from as_engine.help import examples_document, operation_document

    from confluence_as.engine import create_surface

    for _, index in create_surface(transport="responder").indexes.primary():
        for operation in index.operations.values():
            detail = render_help(operation_document(operation, index)) + "\n"
            examples = render_help(examples_document(operation)) + "\n"
            assert token_estimate(detail) <= CAPS["level2"], operation.operationId
            assert token_estimate(examples) <= CAPS["level3"], operation.operationId


def test_preview_applies_explicit_version_without_lookups(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("preview sent")

    monkeypatch.setattr(Responder, "call", forbidden)
    result = CliRunner().invoke(
        cli,
        [
            "api",
            "call",
            "updatePage",
            "--id",
            "123",
            "--version",
            "7",
            "--field",
            "title=Preview",
        ],
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["body"]["version"] == {"number": 7}


def test_dynamic_call_help_json_has_identical_content():
    runner = CliRunner()
    args = ["api", "call", "getPages", "--help"]
    markdown = runner.invoke(cli, args)
    result = runner.invoke(cli, [*args, "--format", "json"])
    assert result.exit_code == 0, result.output
    assert render_help(json.loads(result.stdout)) + "\n" == markdown.stdout


def test_help_examples_uses_index_entries_at_level_three():
    runner = CliRunner()
    result = runner.invoke(cli, ["help", "api", "--examples", "--format", "json"])
    assert result.exit_code == 0, result.output
    value = json.loads(result.stdout)
    assert value["level"] == 3
    assert "api call createPage" in render_help(value)
    default = runner.invoke(cli, ["help", "--examples"])
    assert render_help(value) + "\n" == default.stdout
    assert token_estimate(default.stdout) <= CAPS["level3"]


def test_full_description_restores_vendored_later_paragraphs():
    runner = CliRunner()
    default = runner.invoke(cli, ["api", "describe", "getPages", "--format", "json"])
    full = runner.invoke(
        cli, ["api", "describe", "getPages", "--full", "--format", "json"]
    )
    source = json.loads(
        (
            Path(__file__).parents[1]
            / "src/confluence_as/specs/confluence-openapi-v2.json"
        ).read_text()
    )
    original = source["paths"]["/pages"]["get"]["description"]
    assert json.loads(full.stdout)["description"] == original
    assert len(json.loads(default.stdout)["description"]) < len(original)
