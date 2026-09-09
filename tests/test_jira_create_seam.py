"""The cross-product command sends a Jira Operation to the engine transport."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from as_engine import transport as engine_transport  # type: ignore[import-untyped]
from as_engine.transport import Response  # type: ignore[import-untyped]
from click.testing import CliRunner

from confluence_as import ValidationError
from confluence_as.cli.commands import jira_cmds
from confluence_as.cli.main import cli


@pytest.fixture
def seam(monkeypatch):
    calls = []
    state = SimpleNamespace(
        response=Response(201, {"key": "SBX-2", "id": "22"}), closed=False
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
            return state.response

    monkeypatch.setattr(engine_transport, "HTTPTransport", TransportDouble)

    def no_http(*args, **kwargs):
        pytest.fail("raw HTTP must never run in a transport-seam test")

    monkeypatch.setattr(requests, "post", no_http)
    monkeypatch.setattr(requests.sessions.Session, "request", no_http)
    page = {
        "id": "123",
        "title": "Example page",
        "body": {"storage": {"value": "<p>Example body</p>"}},
        "version": {"number": 4},
    }
    client = Mock()
    client.get.return_value = page
    monkeypatch.setattr(jira_cmds, "get_client_from_context", lambda ctx: client)
    # Inert fixture config only; this factory never constructs an HTTP client.
    config = {"url": "https://example.invalid", "email": "fixture", "token": "fixture"}
    monkeypatch.setattr(jira_cmds, "_get_jira_client_config", lambda *args: config)
    return state, calls, client, config


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
    assert client.get.call_count == 2
    client.put.assert_called_once_with(
        "/api/v2/pages/123",
        json_data={
            "id": "123",
            "title": "Example page",
            "body": {
                "representation": "storage",
                "value": "<p>Example body</p>\n<!-- JIRA-LINK: SBX-2 -->",
            },
            "version": {"number": 5},
        },
        operation="link page to new issue",
    )
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
    assert client.get.call_count == 1
    client.put.assert_not_called()


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
    assert client.get.call_count == 1
    client.put.assert_not_called()
