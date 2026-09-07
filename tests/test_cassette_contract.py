"""Generic Surface argv contracts from a recorded local fake HTTP service.

All tests are integration-marked, but never live-marked, so normal CI runs them.
The fixture is synthetic: it is not evidence of compatibility with a live site.
"""

from __future__ import annotations

import base64
import json
import socket
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests
import responses
from as_engine.errors import SurfaceError
from as_engine.responder import Responder
from click.testing import CliRunner

from confluence_as.cli.main import cli
from confluence_as.config_manager import ConfigManager
from confluence_as.engine import create_surface

pytestmark = pytest.mark.integration
CASSETTE = Path(__file__).parent / "cassettes/generic-surface.json"
SITE = "https://cassette-private-site.invalid"
EMAIL = "cassette-private-email@example.invalid"
TOKEN = "cassette-test-token+/=DO-NOT-PERSIST"
ACCOUNT = "cassette-private-account-id"
CLOUD = "cassette-private-cloud-id"
BASIC = base64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
SECRETS = (SITE, EMAIL, TOKEN, ACCOUNT, CLOUD, BASIC, "cassette-private-cookie")
PAGE_BODY = {
    "spaceId": "5",
    "title": "Cassette example",
    "body": {"representation": "storage", "value": "<p>Offline contract</p>"},
}
UPDATE_BODY = {**PAGE_BODY, "id": "10", "version": {"number": 2}, "status": "current"}


def record_local_fixture(path, monkeypatch):
    """Real HTTPTransport request serialization, intercepted by responses locally."""
    monkeypatch.setenv("CONFLUENCE_AS_TRANSPORT", "http")
    monkeypatch.setenv("CONFLUENCE_AS_RECORD", str(path))
    monkeypatch.delenv("CONFLUENCE_AS_CASSETTE", raising=False)
    config = Mock()
    config.get_credentials.return_value = {
        "url": SITE + "/wiki/",
        "email": EMAIL,
        "api_token": TOKEN,
    }
    config.get_api_config.return_value = {"max_retries": 0}
    config.get_scope_config.return_value = {
        "scope_allowlist": ("DOCS",),
        "scope_allow_site": False,
    }
    monkeypatch.setattr(ConfigManager, "get_instance", lambda: config)
    page = {
        "id": "10",
        "status": "current",
        "title": PAGE_BODY["title"],
        "spaceId": "5",
        "authorId": ACCOUNT,
        "version": {"number": 1, "createdAt": "2026-09-01T00:00:00Z"},
        "body": {"storage": PAGE_BODY["body"]},
        "owner": {"accountId": ACCOUNT, "email": EMAIL},
        "cloudId": CLOUD,
        "_links": {"base": SITE, "webui": "/spaces/5/pages/10"},
        "echo": TOKEN + " " + BASIC,
    }
    page_metadata = {"id": "10", "spaceId": "5", "version": {"number": 1}}
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Basic " + BASIC,
        "Set-Cookie": "cassette-private-cookie",
    }
    surface = create_surface()
    with responses.RequestsMock() as wire:
        wire.get(
            SITE + "/wiki/api/v2/spaces?ids=5",
            json={"results": [{"id": "5", "key": "DOCS"}]},
            headers=headers,
        )
        wire.get(
            SITE + "/wiki/api/v2/spaces?keys=DOCS",
            json={"results": [{"id": "5", "key": "DOCS"}]},
            headers=headers,
        )
        wire.get(
            SITE + "/wiki/api/v2/pages?space-id=5&limit=5",
            json={"results": [page], "_links": {"base": SITE}},
            headers=headers,
        )
        wire.get(SITE + "/wiki/api/v2/pages/10", json=page_metadata, headers=headers)
        wire.post(SITE + "/wiki/api/v2/pages", json=page, status=201, headers=headers)
        wire.put(
            SITE + "/wiki/api/v2/pages/10",
            json={**page, "version": {"number": 2}},
            headers=headers,
        )
        wire.get(
            SITE + "/wiki/api/v2/pages/404",
            json={"message": "Page not found"},
            status=404,
            headers=headers,
        )
        wire.get(
            SITE + "/wiki/api/v2/pages?space-id=5&limit=7",
            json={"message": "Page not found"},
            status=404,
            headers=headers,
        )
        assert (
            surface.call("getPages", {"space-id": [5], "limit": 5}).body["results"][0]["id"]
            == "10"
        )
        assert surface.call("getPageById", {"id": 10}).body["id"] == "10"
        assert surface.call("createPage", {}, PAGE_BODY, scope_argv_identity="DOCS").status == 201
        assert (
            surface.call("updatePage", {"id": 10}, UPDATE_BODY).body["version"][
                "number"
            ]
            == 2
        )
        with pytest.raises(SurfaceError) as error:
            surface.call("getPageById", {"id": 404})
        assert error.value.code == 4
        with pytest.raises(SurfaceError) as error:
            surface.call("getPages", {"space-id": [5], "limit": 7})
        assert error.value.code == 5
        assert len(wire.calls) == 13
        assert all(
            call.request.headers["Authorization"] == "Basic " + BASIC
            for call in wire.calls
        )
        assert json.loads(wire.calls[6].request.body) == PAGE_BODY
        assert json.loads(wire.calls[9].request.body) == UPDATE_BODY


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Scope settings are safe for playback; credential reads are never allowed."""
    def denied(*args, **kwargs):
        raise AssertionError("cassette contract attempted network or credential access")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    config = Mock()
    config.get_scope_config.return_value = {
        "scope_allowlist": ("DOCS",),
        "scope_allow_site": False,
    }
    config.get_credentials.side_effect = denied
    monkeypatch.setattr(ConfigManager, "get_credentials", denied)
    monkeypatch.setattr(ConfigManager, "get_instance", lambda: config)
    monkeypatch.setenv("CONFLUENCE_AS_TRANSPORT", "cassette")
    monkeypatch.setenv("CONFLUENCE_AS_CASSETTE", str(CASSETTE))
    monkeypatch.delenv("CONFLUENCE_AS_RECORD", raising=False)


def invoke(*args, input=None):
    return CliRunner().invoke(cli, ["api", *args], input=input)


def test_recorded_fake_service_scrubs_all_secrets_and_matches_committed_fixture(
    tmp_path, monkeypatch
):
    path = tmp_path / "recorded.json"
    record_local_fixture(path, monkeypatch)
    raw = path.read_text()
    for secret in SECRETS:
        assert secret not in raw
    assert path.read_bytes() == CASSETTE.read_bytes()
    monkeypatch.delenv("CONFLUENCE_AS_RECORD")
    monkeypatch.setenv("CONFLUENCE_AS_TRANSPORT", "cassette")
    monkeypatch.setenv("CONFLUENCE_AS_CASSETTE", str(path))
    result = invoke("call", "getPages", "--space-id", "5", "--limit", "5")
    assert (
        result.exit_code == 0 and json.loads(result.stdout)["results"][0]["id"] == "10"
    )


@pytest.mark.parametrize(
    "name,args,body,expected",
    [
        ("getPages", ["--space-id", "5", "--limit", "5"], None, "results"),
        ("getPageById", ["--id", "10"], None, "id"),
        ("createPage", ["--space", "DOCS"], PAGE_BODY, "id"),
        ("updatePage", ["--id", "10", "--confirm"], UPDATE_BODY, "version"),
    ],
)
def test_cassette_call_verbs_replay_offline(monkeypatch, name, args, body, expected):
    def denied(*args, **kwargs):
        raise AssertionError("playback must not reach requests")

    monkeypatch.setattr(requests.Session, "send", denied)
    result = invoke(
        "call",
        name,
        *args,
        *(["--body", "-"] if body else []),
        input=json.dumps(body) if body else None,
    )
    assert result.exit_code == 0 and result.stderr == "", result.output
    assert expected in json.loads(result.stdout)


def test_cassette_error_and_miss_are_structured_offline():
    result = invoke("call", "getPageById", "--id", "404")
    assert result.exit_code == 4 and result.stdout == "", result.output
    error = json.loads(result.stderr)
    assert error["status"] is None
    assert "scope identity 404" in error["messages"][0]
    assert "HTTP 404" not in error["messages"][0]
    assert "Page not found" not in error["messages"][0]
    result = invoke("call", "getPages", "--space-id", "5", "--limit", "7")
    assert result.exit_code == 5 and json.loads(result.stderr)["status"] == 404
    assert json.loads(result.stderr)["messages"] == ["Page not found"]
    result = invoke("call", "getPages", "--space-id", "5", "--limit", "6")
    assert result.exit_code == 2 and "cassette miss: getPages" in result.stderr


def test_all_generic_surface_discovery_verbs_with_cassette_transport():
    result = invoke("search", "page", "--format", "json")
    assert result.exit_code == 0 and any(
        row["operationId"] == "getPages" for row in json.loads(result.stdout)
    )
    result = invoke("describe", "getPages", "--format", "json")
    assert (
        result.exit_code == 0 and json.loads(result.stdout)["operationId"] == "getPages"
    )
    result = invoke("topics", "--format", "json")
    assert result.exit_code == 0 and isinstance(json.loads(result.stdout), list)


@pytest.mark.parametrize(
    "mode,cassette,record,message",
    [
        ("cassette", None, None, "requires CONFLUENCE_AS_CASSETTE"),
        ("cassette", "fake.json", "out.json", "requires http"),
        ("responder", None, "out.json", "requires http"),
        ("http", "fake.json", None, "requires cassette"),
    ],
)
def test_contradictory_settings_fail_before_configuration(
    monkeypatch, mode, cassette, record, message
):
    monkeypatch.setenv("CONFLUENCE_AS_TRANSPORT", mode)
    for name, value in (
        ("CONFLUENCE_AS_CASSETTE", cassette),
        ("CONFLUENCE_AS_RECORD", record),
    ):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    result = invoke("call", "getPages", "--space-id", "5")
    assert result.exit_code == 2 and message in result.stderr


def test_responder_still_works_without_credentials(monkeypatch):
    def seeded_responder(index, *, status=200):
        responder = Responder(index, status=status)
        responder.seed("getSpaces", [{"results": [{"id": "5", "key": "DOCS"}]}])
        responder.seed("getPages", [{"results": [{"id": "10", "body": {"storage": {"representation": "storage", "value": "<p>Offline contract</p>"}}}]}])
        return responder

    monkeypatch.setattr("confluence_as.engine.Responder", seeded_responder)
    monkeypatch.delenv("CONFLUENCE_AS_CASSETTE")
    monkeypatch.setenv("CONFLUENCE_AS_TRANSPORT", "responder")
    result = invoke("call", "getPages", "--space-id", "5")
    assert result.exit_code == 0 and "results" in json.loads(result.stdout)
