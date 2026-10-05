"""The cross-product command sends a Jira Operation to the engine transport."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
import requests
from as_engine import transport as engine_transport  # type: ignore[import-untyped]
from as_engine.transport import Response  # type: ignore[import-untyped]
from click.testing import CliRunner

from confluence_as import ValidationError, engine
from confluence_as.cli import cli_utils
from confluence_as.cli.commands import jira_cmds
from confluence_as.cli.main import cli
from confluence_as.config_manager import ConfigManager


@pytest.fixture
def seam(monkeypatch):
    calls = []
    state = SimpleNamespace(
        response=Response(201, {"key": "SBX-2", "id": "22"}),
        closed=False,
        reads=0,
        read_status=200,
        update_status=200,
        space_key="DOCS",
        space_after_jira=None,
        events=[],
        confluence_calls=[],
    )

    class TransportDouble:
        def __init__(self, base_url, **kwargs):
            state.base_url = base_url
            state.options = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *args):
            state.closed = True

        def call(self, operation, parameters, body):
            calls.append((operation, parameters, body))
            state.events.append("createIssue")
            if state.space_after_jira:
                state.space_key = state.space_after_jira
            return state.response

    monkeypatch.setattr(engine_transport, "HTTPTransport", TransportDouble)

    def no_http(*args, **kwargs):
        pytest.fail("raw HTTP must never run in a transport-seam test")

    monkeypatch.setattr(cli_utils, "get_client_from_context", no_http)
    monkeypatch.setattr(cli_utils, "get_confluence_client", no_http)
    monkeypatch.setattr(requests.Session, "send", no_http)
    monkeypatch.setattr(requests, "post", no_http)
    monkeypatch.setattr(requests.sessions.Session, "request", no_http)
    page = {
        "id": "123",
        "spaceId": "55",
        "title": "Example page",
        "body": {"storage": {"value": "<p>Example body</p>"}},
        "version": {"number": 4},
    }
    state.page = page
    state.latest_page = deepcopy(page)

    class ConfluenceTransport:
        def call(self, operation, parameters, body):
            name = operation.operationId
            resolution = bool(operation.extensions.get("x-as-resolution-read"))
            state.confluence_calls.append((name, parameters, body, resolution))
            state.events.append(("resolution:" if resolution else "") + name)
            if name == "getSpaces":
                return Response(
                    200, {"results": [{"id": "55", "key": state.space_key}]}
                )
            if name == "getPageById":
                if resolution:
                    return Response(200, {"id": "123", "spaceId": "55"})
                state.reads += 1
                if state.reads == 2 and state.read_status != 200:
                    return Response(state.read_status, {"message": "page read failed"})
                return Response(
                    200, state.page if state.reads == 1 else state.latest_page
                )
            assert name == "updatePage"
            return Response(state.update_status, {"message": "page update result"})

    monkeypatch.setattr(ConfigManager, "_find_claude_dir", lambda _: None)
    ConfigManager.reset_instance()
    monkeypatch.setenv("CONFLUENCE_ALLOWED_SPACES", "DOCS")
    monkeypatch.delenv("CONFLUENCE_ALLOW_SITE_OPERATIONS", raising=False)
    client = engine.create_surface(transport="responder")
    client.transport_factory = lambda *_: ConfluenceTransport()
    monkeypatch.setattr(engine, "create_surface", lambda **_: client)
    # Inert fixture config only; this factory never constructs an HTTP client.
    config = {"url": "https://example.invalid", "email": "fixture", "token": "fixture"}
    monkeypatch.setattr(jira_cmds, "_get_jira_client_config", lambda *args: config)
    yield state, calls, client, config
    ConfigManager.reset_instance()


@pytest.mark.parametrize("status", [200, 201])
@pytest.mark.parametrize("output", ["json", "text"])
def test_create_from_page_uses_operation_transport(seam, status, output):
    state, calls, client, config = seam
    state.response = Response(status, {"key": "SBX-2", "id": "22"})
    result = CliRunner().invoke(
        cli,
        [
            "jira",
            "create-from-page",
            "123",
            "--project",
            "sbx",
            "--type",
            "Bug",
            "--priority",
            "High",
            "--assignee",
            "account-1",
            "--output",
            output,
        ],
    )
    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    operation, parameters, body = calls[0]
    assert (operation.operationId, operation.method, operation.path) == (
        "createIssue",
        "POST",
        "/rest/api/3/issue",
    )
    assert operation.request_media_types == ["application/json"]
    assert parameters == {}
    assert body == {
        "fields": {
            "project": {"key": "SBX"},
            "summary": "Example page",
            "description": "Example body",
            "issuetype": {"name": "Bug"},
            "priority": {"name": "High"},
            "assignee": {"accountId": "account-1"},
        }
    }
    assert state.base_url == config["url"]
    assert state.options["auth"] == (config["email"], config["token"])
    assert state.options["timeout"] == 30
    assert state.options["max_retries"] == 0
    assert state.closed
    assert state.reads == 2
    operations = [call[:3] for call in state.confluence_calls if not call[3]]
    assert operations[:2] == [
        ("getPageById", {"id": 123, "body-format": "storage"}, None),
        ("getPageById", {"id": 123, "body-format": "storage"}, None),
    ]
    assert operations[2:] == [
        (
            "updatePage",
            {"id": 123},
            {
                "id": "123",
                "title": "Example page",
                "body": {
                    "representation": "storage",
                    "value": "<p>Example body</p>\n<!-- JIRA-LINK: SBX-2 -->",
                },
                "version": {"number": 5},
            },
        )
    ]
    assert state.events.index("getPageById") < state.events.index("createIssue")
    assert "Created JIRA issue SBX-2 from page 123" in result.output
    if output == "json":
        assert '"key": "SBX-2"' in result.output
        assert '"url": "https://example.invalid/browse/SBX-2"' in result.output
    else:
        assert "JIRA Issue Created from Confluence Page" in result.output
        assert "Project: sbx" in result.output


def test_create_failure_does_not_link_page(seam):
    state, calls, client, _ = seam
    state.response = Response(400, "invalid issue")
    result = CliRunner().invoke(
        cli, ["jira", "create-from-page", "123", "--project", "SBX"]
    )
    assert result.exit_code == 1
    assert "Failed to create JIRA issue: 400 - invalid issue" in result.output
    assert len(calls) == 1
    assert state.closed
    assert state.reads == 1
    assert "updatePage" not in state.events


def test_http_error_mapper_preserves_bounded_error_text():
    response = SimpleNamespace(status_code=403, text="x" * 600)
    with pytest.raises(ValidationError) as error:
        jira_cmds._jira_create_error(response, "createIssue")
    assert str(error.value) == "Failed to create JIRA issue: 403 - " + "x" * 500


def test_missing_created_key_does_not_link_page(seam):
    state, calls, client, _ = seam
    state.response = Response(201, {"id": "22"})
    result = CliRunner().invoke(
        cli, ["jira", "create-from-page", "123", "--project", "SBX"]
    )
    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    assert state.closed
    assert state.reads == 1
    assert "updatePage" not in state.events


@pytest.mark.parametrize("allowlist", [None, "", "OTHER"])
def test_scope_refusal_precedes_jira_creation(seam, monkeypatch, allowlist):
    state, calls, _, _ = seam
    if allowlist is None:
        monkeypatch.delenv("CONFLUENCE_ALLOWED_SPACES")
    else:
        monkeypatch.setenv("CONFLUENCE_ALLOWED_SPACES", allowlist)
    result = CliRunner().invoke(
        cli, ["jira", "create-from-page", "123", "--project", "SBX"]
    )
    assert result.exit_code == 4, result.output
    assert result.stdout == ""
    error = json.loads(result.stderr)
    assert error["operation"] == "getPageById"
    assert "allowlist=" in error["messages"][0]
    assert calls == []
    assert state.reads == 0
    assert all(call[3] for call in state.confluence_calls)
    if not allowlist:
        assert state.confluence_calls == []


def test_storage_and_latest_version_survive_round_trip(seam):
    state, _, _, _ = seam
    storage = '<ac:structured-macro ac:name="toc"/><p>new &amp; existing</p>'
    state.latest_page.update(
        title="Concurrent title",
        body={"storage": {"value": storage}},
        version={"number": 9},
    )
    result = CliRunner().invoke(
        cli, ["jira", "create-from-page", "123", "--project", "SBX"]
    )
    assert result.exit_code == 0, result.output
    update = [call for call in state.confluence_calls if call[0] == "updatePage"]
    assert len(update) == 1
    assert update[0][2]["version"] == {"number": 10}
    assert update[0][2]["title"] == "Concurrent title"
    assert update[0][2]["body"] == {
        "representation": "storage",
        "value": storage + "\n<!-- JIRA-LINK: SBX-2 -->",
    }


def test_existing_marker_skips_update(seam):
    state, calls, _, _ = seam
    state.latest_page["body"]["storage"]["value"] += "\n<!-- JIRA-LINK: SBX-2 -->"
    result = CliRunner().invoke(
        cli, ["jira", "create-from-page", "123", "--project", "SBX"]
    )
    assert result.exit_code == 0, result.output
    assert len(calls) == 1
    assert state.reads == 2
    assert "updatePage" not in state.events


@pytest.mark.parametrize("status", [403, 409, 500])
def test_jira_created_page_update_failed_reports_partial_outcome_without_retry(
    seam, status
):
    state, calls, _, _ = seam
    state.update_status = status
    result = CliRunner().invoke(
        cli, ["jira", "create-from-page", "123", "--project", "SBX", "--output", "json"]
    )
    assert result.exit_code != 0
    assert result.stdout == ""
    error = json.loads(result.stderr)
    assert error["status"] == status
    assert error["operation"] == "updatePage"
    assert "JIRA issue SBX-2 was created" in error["messages"][0]
    assert "Do not repeat create-from-page" in error["messages"][0]
    assert len(calls) == 1
    assert state.reads == 2
    assert state.events.count("updatePage") == 1


@pytest.mark.parametrize("failure", ["read", "scope"])
def test_post_create_read_failure_does_not_update_or_repeat_jira(seam, failure):
    state, calls, _, _ = seam
    if failure == "read":
        state.read_status = 404
    else:
        state.space_after_jira = "OTHER"
    result = CliRunner().invoke(
        cli, ["jira", "create-from-page", "123", "--project", "SBX"]
    )
    assert result.exit_code != 0
    error = json.loads(result.stderr)
    assert error["operation"] == "getPageById"
    assert "JIRA issue SBX-2 was created" in error["messages"][0]
    assert len(calls) == 1
    assert "updatePage" not in state.events
