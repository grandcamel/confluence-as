"""Offline argv coverage for Confluence paging and prerequisite tags."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests
from as_engine.index import ProductIndexes
from as_engine.responder import Responder
from as_engine.surface import Surface
from as_engine.transport import Response
from click.testing import CliRunner

from confluence_as.cli.main import cli


@pytest.fixture
def responder_surface(monkeypatch):
    """Use packaged indexes with one inspectable responder for every CLI call."""
    indexes = ProductIndexes(Path(__file__).parents[1] / "src/confluence_as/_generated")
    responder = Responder(indexes.get("v2"))
    surface = Surface(indexes, lambda _document, _index: responder)
    monkeypatch.setattr(
        "confluence_as.cli.commands.api_cmds.create_surface", lambda **_kwargs: surface
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("HTTP attempted by paging argv test")

    monkeypatch.setattr(requests.Session, "send", forbidden)
    return responder


def invoke(*args):
    return CliRunner().invoke(cli, ["api", "call", *args])


def page(start: int, size: int, *, next_link: str | None = None):
    value = {"results": [{"id": str(i)} for i in range(start, start + size)]}
    if next_link:
        value["_links"] = {"next": next_link}
    return value


def create_fields(*extra: str):
    return (
        "createPage",
        "--field",
        'title="Example"',
        "--field",
        "body.value=<p>x</p>",
        "--field",
        "body.representation=storage",
        *extra,
    )


def test_default_page_and_parameter_limit_are_separate(responder_surface):
    result = invoke("getPages", "--limit", "5")
    assert result.exit_code == 0, result.output
    assert responder_surface.requests == [("getPages", {"limit": 5}, None)]

    responder_surface.requests.clear()
    responder_surface.seed("getPages", [page(0, 1)])
    result = invoke("getPages", "--all", "--parameter-limit", "7")
    assert result.exit_code == 0, result.output
    assert responder_surface.requests == [("getPages", {"limit": 7}, None)]

    assert "--all aggregates pages" in invoke("getPages", "--help").stdout
    assert "--space-key VALUE" in invoke("createPage", "--help").stdout
    assert "--version INTEGER" in invoke("updatePage", "--help").stdout


def test_all_pages_caps_aggregate_and_reports_count(responder_surface):
    responder_surface.seed(
        "getPages",
        [
            page(0, 100, next_link="/api/v2/pages?cursor=next"),
            page(100, 100),
        ],
    )
    result = invoke("getPages", "--all", "--parameter-limit", "100", "--limit", "120")
    assert result.exit_code == 0, result.output
    assert len(json.loads(result.stdout)) == 120
    assert result.stderr.rstrip().endswith("count=120")
    assert responder_surface.requests == [
        ("getPages", {"limit": 100}, None),
        ("getPages", {"limit": 100, "cursor": "next"}, None),
    ]


def test_alias_lookup_supplies_id_and_explicit_id_bypasses_it(responder_surface):
    responder_surface.seed("getSpaces", [{"results": [{"key": "DOCS", "id": "55"}]}])
    result = invoke(*create_fields("--space-key", "DOCS"))
    assert result.exit_code == 0, result.output
    assert responder_surface.requests[0] == ("getSpaces", {"keys": ["DOCS"]}, None)
    assert responder_surface.requests[1][0] == "createPage"
    assert responder_surface.requests[1][2]["spaceId"] == "55"

    responder_surface.requests.clear()
    result = invoke(*create_fields("--field", 'spaceId="66"'))
    assert result.exit_code == 0, result.output
    assert len(responder_surface.requests) == 1
    assert responder_surface.requests[0][:2] == ("createPage", {})
    assert responder_surface.requests[0][2]["spaceId"] == "66"


def test_alias_and_explicit_id_conflict_before_transport(responder_surface):
    result = invoke(*create_fields("--field", 'spaceId="66"', "--space-key", "DOCS"))
    assert result.exit_code == 2, result.output
    assert responder_surface.requests == []


def test_current_and_draft_versions_avoid_unnecessary_reads(responder_surface):
    responder_surface.seed("getPageById", [{"version": {"number": 7}}])
    result = invoke("updatePage", "--confirm", "--id", "9", "--field", 'title="Current"')
    assert result.exit_code == 0, result.output
    assert responder_surface.requests[0] == ("getPageById", {"id": 9}, None)
    assert responder_surface.requests[1][0] == "updatePage"
    assert responder_surface.requests[1][2]["version"]["number"] == 8

    responder_surface.requests.clear()
    result = invoke(
        "updatePage", "--confirm", "--id", "9", "--field", 'title="Draft"', "--field", "status=draft"
    )
    assert result.exit_code == 0, result.output
    assert [request[0] for request in responder_surface.requests] == ["updatePage"]
    assert responder_surface.requests[0][2]["version"]["number"] == 1


def test_explicit_version_avoids_read_and_conflict_is_not_retried(responder_surface):
    result = invoke("updatePage", "--confirm", "--id", "9", "--field", 'title="Explicit"', "--version", "12")
    assert result.exit_code == 0, result.output
    assert [request[0] for request in responder_surface.requests] == ["updatePage"]
    assert responder_surface.requests[0][2]["version"]["number"] == 12

    responder_surface.requests.clear()
    responder_surface.seed("getPageById", [{"version": {"number": 7}}])
    responder_surface.seed("updatePage", [Response(status=409, body={"code": 7, "message": "conflict"})])
    result = invoke("updatePage", "--confirm", "--id", "9", "--field", 'title="Conflict"')
    assert result.exit_code == 7, result.output
    assert json.loads(result.stderr)["status"] == 409
    assert [request[0] for request in responder_surface.requests].count("updatePage") == 1
