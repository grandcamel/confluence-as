"""Surface-only checks for administration, permission, and ops survivors."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests
from as_engine.index import ProductIndexes
from as_engine.simulation import SimulationStore
from as_engine.surface import Surface
from as_engine.transport import Response
from click.testing import CliRunner

from confluence_as import ConfluenceError
from confluence_as.cli.commands import admin_cmds, ops_cmds, permission_cmds
from confluence_as.cli.helpers import get_current_user_space_operations
from confluence_as.cli.main import cli
from confluence_as.engine import create_surface


class GrantTransport:
    def __init__(self, *, identity=True, groups=None, grants=None):
        self.identity, self.groups, self.grants = identity, groups, grants

    def response(self, name):
        if name == "getSpaces":
            return Response(
                200, {"results": [{"id": "55", "key": "DOCS", "name": "Docs"}]}
            )
        value = {
            "getCurrentUser": self.identity,
            "getGroupMembershipsForUser": self.groups,
            "getSpacePermissionsAssignments": self.grants,
        }[name]
        if value is None:
            raise ConfluenceError("unreadable")
        return Response(200, value)

    def call(self, operation, _params, _body):
        return self.response(operation.operationId)


class LegacyGrantClient:
    def __init__(self, transport):
        self.transport = transport

    def get(self, path, **_kwargs):
        name = {
            "/rest/api/user/current": "getCurrentUser",
            "/rest/api/user/memberof": "getGroupMembershipsForUser",
        }[path]
        return self.transport.response(name).body

    def paginate(self, path, **_kwargs):
        name = {
            "/api/v2/spaces/55/permissions": "getSpacePermissionsAssignments",
        }[path]
        body = self.transport.response(name).body
        return body.get("results", []) if isinstance(body, dict) else body


@pytest.mark.parametrize(
    ("identity", "groups", "grants", "expected"),
    [
        (
            {"accountId": "me", "displayName": "Me"},
            {"results": []},
            {
                "results": [
                    {
                        "operation": {"key": "read", "targetType": "space"},
                        "principal": {"type": "user", "id": "other"},
                    }
                ]
            },
            False,
        ),
        (
            {"accountId": "me", "displayName": "Me"},
            {"results": []},
            {
                "results": [
                    {
                        "operation": {"key": "read", "targetType": "space"},
                        "principal": {"type": "role", "id": "x"},
                    }
                ]
            },
            None,
        ),
        (
            {"accountId": "me", "displayName": "Me"},
            {"results": [], "totalSize": 2},
            {
                "results": [
                    {
                        "operation": {"key": "read", "targetType": "space"},
                        "principal": {"type": "group", "id": "unknown"},
                    }
                ]
            },
            None,
        ),
        (None, {"results": []}, {"results": []}, None),
        ({"accountId": "me", "displayName": "Me"}, {"results": []}, None, None),
    ],
)
def test_admin_grant_derivation_matches_legacy_helper(
    monkeypatch, identity, groups, grants, expected
):
    transport = GrantTransport(identity=identity, groups=groups, grants=grants)
    indexes = ProductIndexes(Path(__file__).parents[1] / "src/confluence_as/_generated")
    surface = Surface(
        indexes,
        lambda _document, _index: transport,
        scope_allowlist=("DOCS",),
        scope_allow_site=True,
        scope_resolution_rules={
            "v2:getSpacePermissionsAssignments": (("id",),),
            "v2:getSpaces": (("keys",), ("ids",)),
        },
    )
    monkeypatch.setattr(admin_cmds, "_surface", lambda: surface)
    result = CliRunner().invoke(
        cli, ("admin", "permissions", "check", "--space", "DOCS", "--output", "json")
    )
    assert result.exit_code == 0, result.output
    actual = {
        item["operation"]: item["has_permission"]
        for item in json.loads(result.output)["permissions"]
    }
    legacy = get_current_user_space_operations(LegacyGrantClient(transport), "55")[
        "operations"
    ]
    assert actual == legacy
    assert actual["read"] is expected


@pytest.mark.parametrize(
    ("groups", "expected_read", "read_text"),
    [(None, None, "Unknown"), ({"results": []}, False, "No")],
)
@pytest.mark.parametrize(
    ("space_fields", "space_name"),
    [({"name": "Docs"}, "Docs"), ({"name": None}, None), ({}, "DOCS")],
)
def test_admin_membership_failure_preserves_partial_grants_and_space_name(
    monkeypatch, groups, expected_read, read_text, space_fields, space_name
):
    transport = GrantTransport(
        identity={"accountId": "me", "displayName": "Me"},
        groups=groups,
        grants={
            "results": [
                {
                    "operation": {"key": "read", "targetType": "space"},
                    "principal": {"type": "group", "id": "unknown"},
                },
                {
                    "operation": {"key": "create", "targetType": "page"},
                    "principal": {"type": "user", "id": "me"},
                },
                {
                    "operation": {"key": "update", "targetType": "page"},
                    "principal": {"type": "user", "id": "other"},
                },
            ]
        },
    )
    original = transport.response

    def response(name):
        if name == "getSpaces":
            return Response(
                200, {"results": [{"id": "55", "key": "DOCS", **space_fields}]}
            )
        return original(name)

    monkeypatch.setattr(transport, "response", response)
    indexes = ProductIndexes(Path(__file__).parents[1] / "src/confluence_as/_generated")
    surface = Surface(
        indexes,
        lambda _document, _index: transport,
        scope_allowlist=("DOCS",),
        scope_allow_site=True,
        scope_resolution_rules={
            "v2:getSpacePermissionsAssignments": (("id",),),
            "v2:getSpaces": (("keys",), ("ids",)),
        },
    )
    monkeypatch.setattr(admin_cmds, "_surface", lambda: surface)
    runner = CliRunner()
    arguments = ["admin", "permissions", "check", "--space", "DOCS", "--output"]
    result = runner.invoke(cli, [*arguments, "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    permissions = {
        item["operation"]: item["has_permission"] for item in payload["permissions"]
    }
    assert payload["space"] == {"key": "DOCS", "name": space_name}
    assert permissions["read"] is expected_read
    assert permissions["create"] is True
    assert permissions["edit"] is False
    text = runner.invoke(cli, [*arguments, "text"])
    assert text.exit_code == 0, text.output
    assert text.stdout.splitlines()[0] == f"Permission Check: {space_name} (DOCS)"
    assert {f"  read: {read_text}", "  create: Yes", "  edit: No"} <= set(
        text.stdout.splitlines()
    )


def test_affordances_use_surface_and_local_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("CONFLUENCE_ALLOWED_SPACES", "DOCS")
    monkeypatch.setenv("CONFLUENCE_ALLOW_SITE_OPERATIONS", "true")
    monkeypatch.setenv("CONFLUENCE_CACHE_DIR", str(tmp_path))
    store = SimulationStore()
    store.space_permissions["55"] = [
        {
            "id": "1",
            "operation": {"key": "read", "targetType": "space"},
            "principal": {"type": "user", "id": "sim-user"},
        }
    ]
    surface = create_surface(transport="simulation", store=store)
    for module in (admin_cmds, permission_cmds):
        monkeypatch.setattr(module, "_surface", lambda: surface)
    monkeypatch.setattr(ops_cmds, "create_surface", lambda: surface)
    monkeypatch.setattr(
        requests.Session,
        "send",
        lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("HTTP bypass")),
    )
    runner = CliRunner()
    results = []
    for args in (
        ("admin", "permissions", "check", "--space", "DOCS", "--output", "json"),
        (
            "permission",
            "page",
            "remove",
            "1",
            "--all",
            "--operation",
            "read",
            "--output",
            "json",
        ),
        (
            "permission",
            "space",
            "remove",
            "DOCS",
            "--permission-id",
            "1",
            "--output",
            "json",
        ),
        ("ops", "cache-warm", "--spaces", "--output", "json"),
        ("ops", "cache-status", "--output", "json"),
        ("ops", "cache-clear", "--force", "--output", "json"),
        ("ops", "health-check", "--output", "json"),
        ("ops", "rate-limit-status", "--output", "json"),
        ("ops", "api-diagnostics", "--output", "json"),
    ):
        result = runner.invoke(cli, args)
        assert result.exit_code == 0, result.output
        results.append(result)
    import json

    assert json.loads(results[3].output)["warmed"]
    assert json.loads(results[4].output)["totalEntries"] > 0
    assert json.loads(results[5].output)["cleared"] > 0
    after_clear = runner.invoke(cli, ("ops", "cache-status", "--output", "json"))
    assert after_clear.exit_code == 0, after_clear.output
    assert json.loads(after_clear.output)["totalEntries"] == 0
    assert (
        runner.invoke(
            cli,
            ("ops", "health-check", "--endpoint", "getCurrentUser", "--output", "json"),
        ).exit_code
        == 0
    )
    write_probe = runner.invoke(
        cli, ("ops", "health-check", "--endpoint", "updatePage", "--output", "json")
    )
    assert write_probe.exit_code != 0
    assert store.calls


def test_page_remove_scope_refusal_is_json_and_sends_no_write(monkeypatch):
    store = SimulationStore()
    surface = create_surface(transport="simulation", store=store)
    surface.scope_allowlist = ("OTHER",)
    monkeypatch.setattr(permission_cmds, "_surface", lambda: surface)
    result = CliRunner().invoke(
        cli,
        (
            "permission",
            "page",
            "remove",
            "1",
            "--all",
            "--operation",
            "read",
            "--output",
            "json",
        ),
    )
    assert result.exit_code == 4, result.output
    assert json.loads(result.stderr)["operation"] == "getPageById"
    assert "updateRestrictions" not in [name for name, _params, _body in store.calls]
