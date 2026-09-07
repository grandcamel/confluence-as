"""API argv acceptance against the responder; all HTTP intercepted or forbidden."""

from __future__ import annotations

import json
from dataclasses import replace
from unittest.mock import Mock

import pytest
import requests
import responses
from as_engine.responder import Responder
from click.testing import CliRunner

from confluence_as.cli.main import cli
from confluence_as.engine import create_surface


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("CONFLUENCE_AS_TRANSPORT", "responder")

    def forbidden(*args, **kwargs):
        raise AssertionError("HTTP attempted by argv responder test")

    monkeypatch.setattr(requests.Session, "send", forbidden)


def invoke(*args, input=None):
    return CliRunner().invoke(cli, ["api", *args], input=input)


def test_get_pages_alias_schema_and_alternate_formats():
    for name in ("getPages", "get-pages"):
        result = invoke("call", name, "--limit", "5")
        assert result.exit_code == 0 and result.stderr == "", result.output
        assert json.loads(result.stdout)["results"][0]["status"] == "current"
    for format in ("table", "markdown"):
        result = invoke("call", "getPages", "--format", format)
        assert result.exit_code == 0 and "results" in result.stdout


@pytest.mark.parametrize(
    "flags",
    [
        ("--limit", "notanumber"),
        ("--limit", "true"),
        ("--limit", "0"),
        ("--limit", "251"),
        ("--sort", "wrong"),
        ("--status", "wrong"),
        ("--unknown", "5"),
        ("--limit",),
        ("--format", "wrong"),
    ],
)
def test_invalid_parameters_never_reach_responder(monkeypatch, flags):
    sent = Mock(side_effect=AssertionError("invalid request sent"))
    monkeypatch.setattr(Responder, "call", sent)
    result = invoke("call", "get-pages", *flags)
    assert result.exit_code == 2 and result.stdout == "", result.output
    error = json.loads(result.stderr)
    assert error["operation"] == "getPages" and error["status"] is None
    assert error["messages"] and set(error) == {
        "status",
        "messages",
        "operation",
        "note",
    }
    sent.assert_not_called()


def test_parameters_arrays_boolean_required_and_spec_limit(monkeypatch):
    calls = []
    original = Responder.call

    def record(self, operation, parameters, body):
        calls.append((operation.operationId, parameters, body))
        return original(self, operation, parameters, body)

    monkeypatch.setattr(Responder, "call", record)
    result = invoke(
        "call",
        "getPages",
        "--id",
        "[1,2]",
        "--id",
        "3",
        "--space-id",
        "4,5",
        "--limit",
        "5",
    )
    assert result.exit_code == 0, result.output
    assert calls[-1][1] == {"id": [1, 2, 3], "space-id": [4, 5], "limit": 5}
    assert len(calls) == 1
    result = invoke(
        "call",
        "createPage",
        "--embedded",
        "false",
        "--private",
        "true",
        "--field",
        'spaceId="1"',
    )
    assert result.exit_code == 0, result.output
    assert calls[-1][1] == {"embedded": False, "private": True}
    assert invoke("call", "getPageById").exit_code == 2


def test_body_stdin_file_fields_and_validation(monkeypatch, tmp_path):
    bodies = []
    original = Responder.call

    def record(self, operation, parameters, body):
        bodies.append(body)
        return original(self, operation, parameters, body)

    monkeypatch.setattr(Responder, "call", record)
    body = {
        "spaceId": "5",
        "title": "Test",
        "body": {"value": "<p>x</p>", "representation": "storage"},
    }
    file = tmp_path / "body.json"
    file.write_text(json.dumps(body))
    for source, stdin in (("@" + str(file), None), ("-", json.dumps(body))):
        result = invoke("call", "createPage", "--body", source, input=stdin)
        assert result.exit_code == 0, result.output
        assert bodies[-1] == body
    result = invoke(
        "call",
        "createPage",
        "--field",
        'spaceId="5"',
        "--field",
        "body.value=<p>x</p>",
        "--field",
        "body.representation=storage",
    )
    assert result.exit_code == 0, result.output
    assert bodies[-1]["body"] == body["body"]
    assert (
        invoke(
            "call", "createPage", "--field", 'spaceId="5"', "--validate-body"
        ).exit_code
        == 0
    )
    before = len(bodies)
    result = invoke(
        "call", "createPage", "--body", "-", "--validate-body", input='{"spaceId":5}'
    )
    assert (
        result.exit_code == 2 and "spaceId" in result.stderr and len(bodies) == before
    )
    for stdin in ("oops", "{"):
        result = invoke("call", "createPage", "--body", "-", input=stdin)
        assert (
            result.exit_code == 2
            and json.loads(result.stderr)["operation"] == "createPage"
        )


@pytest.mark.parametrize(
    "status,code",
    [(400, 2), (401, 3), (403, 4), (404, 5), (409, 7), (429, 6), (500, 6)],
)
def test_forced_errors(status, code):
    result = invoke("--respond-with", str(status), "call", "getPages", "--limit", "5")
    assert result.exit_code == code and result.stdout == "", result.output
    assert json.loads(result.stderr) == {
        "status": status,
        "messages": [f"Responder forced HTTP {status}"],
        "operation": "getPages",
        "note": None,
    }


def test_400_triggers_body_check_but_normal_call_does_not():
    assert invoke("call", "createPage", "--body", "-", input="{}").exit_code == 0
    failure = invoke(
        "--respond-with", "400", "call", "createPage", "--body", "-", input="{}"
    )
    assert failure.exit_code == 2
    assert "body.spaceId: is required" in json.loads(failure.stderr)["messages"]


def test_discovery_search_describe_topics_and_dynamic_help():
    result = invoke("search", "page")
    assert result.exit_code == 0 and all(
        x in result.stdout
        for x in ("operationId", "method", "path", "summary", "getPages")
    )
    result = invoke("search", "PaGe", "--format", "json")
    assert result.exit_code == 0 and any(
        row["operationId"] == "getPages" for row in json.loads(result.stdout)
    )
    result = invoke("describe", "createPage")
    assert result.exit_code == 0 and "`spaceId`: string (required)" in result.stdout
    assert "--embedded" in result.stdout and "scope" in result.stdout
    assert json.loads(invoke("describe", "createPage", "--format", "json").stdout)[
        "body"
    ]
    result = invoke("call", "getPages", "--help")
    assert (
        result.exit_code == 0
        and "--space-id" in result.stdout
        and "--limit" in result.stdout
    )
    assert {"adf", "paging", "risk", "scope"} <= set(invoke("topics").stdout.splitlines())
    assert json.loads(invoke("topics", "--format", "json").stdout) == invoke("topics").stdout.splitlines()


def test_lower_tier_and_standard_deprecation():
    result = invoke("describe", "searchByCQL", "--format", "json")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["path"].startswith("/wiki/rest/api/")
    surface = create_surface()
    op = next(
        op
        for _, idx in surface.indexes.primary()
        for op in idx.operations.values()
        if op.deprecated
    )
    assert (
        json.loads(invoke("describe", op.operationId, "--format", "json").stdout)[
            "deprecated"
        ]
        is True
    )
    args = ["call", op.operationId]
    for p in op.parameters:
        if p["required"]:
            args.extend(["--" + p["name"], "1"])
    result = invoke(*args)
    assert result.exit_code == 0 and "deprecated" in result.stderr, result.output
    assert json.loads(invoke("search", op.operationId, "--format", "json").stdout) == []
    assert (
        len(
            json.loads(
                invoke(
                    "search", op.operationId, "--include-deprecated", "--format", "json"
                ).stdout
            )
        )
        == 1
    )


def test_enrichment_note_topic_and_replacement_through_argv(monkeypatch):
    from confluence_as import engine

    original = engine.ProductIndexes

    def enriched(directory):
        indexes = original(directory)
        primary = indexes.get("v2")
        old = primary.operations["getPages"]
        primary.operations["getPages"] = replace(
            old,
            extensions={
                "x-as-note": "Example gotcha",
                "x-as-topic": "pages",
                "x-as-deprecation": {"replacement": "getNewPages"},
            },
        )
        return indexes

    monkeypatch.setattr(engine, "ProductIndexes", enriched)
    assert {"pages", "adf", "risk"} <= set(invoke("topics").stdout.splitlines())
    assert "getNewPages" in invoke("call", "getPages").stderr
    result = invoke("--respond-with", "400", "call", "getPages")
    assert json.loads(result.stderr.splitlines()[-1])["note"] == "Example gotcha"


@pytest.mark.parametrize(
    "args,code",
    [
        (("describe", "missing"), 5),
        (("search",), 2),
        (("describe",), 2),
        (("bad-command",), 2),
        (("--bad-option",), 2),
    ],
)
def test_usage_failures_are_json(args, code):
    result = invoke(*args)
    assert result.exit_code == code and result.stdout == "", result.output
    assert json.loads(result.stderr)["messages"]


def test_product_http_routing_config_and_domain_mapping(monkeypatch):
    from as_engine.errors import SurfaceError

    from confluence_as.config_manager import ConfigManager

    # Replace send only with responses interception, never permit real HTTP.
    config = Mock()
    config.get_credentials.return_value = {
        "url": "https://offline.invalid/wiki/",
        "email": "test@example.invalid",
        "api_token": "test-only",
    }
    config.get_api_config.return_value = {"timeout": 9, "max_retries": 0}
    monkeypatch.setattr(ConfigManager, "get_instance", lambda: config)
    surface = create_surface(transport="http")
    with responses.RequestsMock() as wire:
        # responses intercepts HTTPAdapter.send; remove the stricter test guard only inside it.
        monkeypatch.setattr(requests.Session, "send", ORIGINAL_SEND)
        wire.get(
            "https://offline.invalid/wiki/api/v2/pages?limit=5",
            json={"results": [{"id": "10"}]},
        )
        assert surface.call("getPages", {"limit": "5"}).body == {
            "results": [{"id": "10"}]
        }
        wire.get(
            "https://offline.invalid/wiki/rest/api/search?cql=type%3Dpage",
            json={"results": []},
        )
        assert surface.call("searchByCQL", {"cql": "type=page"}).body == {"results": []}
        wire.get(
            "https://offline.invalid/wiki/api/v2/pages",
            status=403,
            json={"message": "No permission"},
        )
        with pytest.raises(SurfaceError) as caught:
            surface.call("getPages", {})
        assert caught.value.code == 4 and "No permission" in caught.value.messages


ORIGINAL_SEND = requests.Session.send


def test_string_array_numeric_values_preserved():
    result = invoke("call", "getSpaces", "--keys", "123")
    assert result.exit_code == 0, result.output
    result = invoke("call", "getPages", "--id", "[broken")
    assert result.exit_code == 2 and "Invalid JSON array" in result.stderr
