"""Scope policy exercised through argv and the ordinary recorded transport seam."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests
from as_engine.index import ProductIndexes
from as_engine.responder import Responder
from as_engine.transport import Response
from click.testing import CliRunner

from confluence_as.cli.main import cli
from confluence_as.config_manager import ConfigManager


@pytest.fixture
def scoped(monkeypatch):
    from confluence_as import engine

    class Recorded(Responder):
        def __init__(self, index):
            super().__init__(index)
            self.roles = []

        def call(self, operation, parameters, body):
            self.roles.append(
                "resolution"
                if operation.extensions.get("x-as-resolution-read")
                else "operation"
            )
            return super().call(operation, parameters, body)

    indexes = ProductIndexes(Path(__file__).parents[1] / "src/confluence_as/_generated")
    responder = Recorded(indexes.get("v2"))
    # JAS-38: explicit well-formed success bodies replace synthetic rich-text maps.
    responder.seed("createPage", [{"id": "123", "body": {"storage": {
        "representation": "storage", "value": "<p>Fixture</p>"
    }}}] * 2)
    monkeypatch.setattr(engine, "Responder", lambda *_args, **_kwargs: responder)
    monkeypatch.setattr(ConfigManager, "_find_claude_dir", lambda _self: None)
    ConfigManager.reset_instance()
    monkeypatch.setenv("CONFLUENCE_AS_TRANSPORT", "responder")
    monkeypatch.setenv("CONFLUENCE_ALLOWED_SPACES", "DOCS")
    monkeypatch.delenv("CONFLUENCE_ALLOW_SITE_OPERATIONS", raising=False)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("HTTP attempted in scope argv test")

    monkeypatch.setattr(requests.Session, "request", forbidden)
    yield responder
    ConfigManager.reset_instance()


def invoke(*args, env=None, input=None):
    return CliRunner().invoke(cli, ["api", "call", *args], env=env, input=input)


def create(*args):
    return ("createPage", "--field", 'spaceId="55"', "--field", "title=T", *args)


def assert_refusal(result, operation):
    assert result.exit_code == 4, (result.output, result.exception)
    assert result.stdout == ""
    error = json.loads(result.stderr)
    assert error["status"] is None and error["operation"] == operation
    assert operation in error["messages"][0] and "allowlist=" in error["messages"][0]
    return error


@pytest.mark.parametrize("flags", [(), ("--space", "ENG"), ("--space", "")])
def test_body_missing_or_disallowed_argv_sends_nothing(scoped, flags):
    assert_refusal(invoke(*create(*flags)), "createPage")
    assert scoped.requests == []


def test_body_id_must_match_resolved_key(scoped):
    scoped.seed("getSpaces", [{"results": [{"id": "99", "key": "DOCS"}]}])
    assert_refusal(invoke(*create("--space", "DOCS")), "createPage")
    assert scoped.requests == [("getSpaces", {"keys": ["DOCS"]}, None)]
    assert scoped.roles == ["resolution"]


def test_body_matching_argv_one_lookup_then_one_mutation(scoped):
    scoped.seed("getSpaces", [{"results": [{"id": "55", "key": "DOCS"}]}])
    scoped.seed("createPage", [{"id": "123"}])
    result = invoke(*create("--space", "DOCS"))
    assert result.exit_code == 0 and json.loads(result.stdout) == {"id": "123"}, (
        result.output
    )
    assert result.stderr == ""
    assert scoped.requests == [
        ("getSpaces", {"keys": ["DOCS"]}, None),
        ("createPage", {}, {"spaceId": "55", "title": "T"}),
    ]
    assert scoped.roles == ["resolution", "operation"]


def test_body_file_and_alias_require_same_explicit_space(scoped, tmp_path):
    body = tmp_path / "request.json"
    body.write_text('{"spaceId":"55","title":"T"}')
    scoped.seed("getSpaces", [{"results": [{"id": "55", "key": "DOCS"}]}] * 2)
    assert (
        invoke("createPage", "--space", "DOCS", "--body", "@" + str(body)).exit_code
        == 0
    )
    assert scoped.requests[-1][2] == {"spaceId": "55", "title": "T"}
    result = invoke(
        "createPage", "--space", "DOCS", "--space-key", "DOCS", "--field", "title=T"
    )
    assert result.exit_code == 0, result.output
    assert scoped.requests[-1][2] == {"spaceId": "55", "title": "T"}
    before = len(scoped.requests)
    assert_refusal(
        invoke("createPage", "--space", "DOCS", "--space-key", "ENG"), "createPage"
    )
    assert len(scoped.requests) == before


def test_page_outside_scope_two_metadata_reads_no_operation(scoped):
    scoped.seed("getPageById", [{"id": "123", "spaceId": "66"}])
    scoped.seed("getSpaces", [{"results": [{"id": "66", "key": "ENG"}]}])
    assert_refusal(
        invoke("getPageById", "--id", "123", "--body-format", "storage"), "getPageById"
    )
    assert scoped.requests == [
        ("getPageById", {"id": 123}, None),
        ("getSpaces", {"ids": [66]}, None),
    ]
    assert scoped.roles == ["resolution", "resolution"]


def test_allowed_page_sends_original_content_option_only_after_resolution(scoped):
    scoped.seed(
        "getPageById",
        [
            {"id": "123", "spaceId": "55"},
            {"id": "123", "body": {"storage": {"value": "<p>T</p>"}}},
        ],
    )
    scoped.seed("getSpaces", [{"results": [{"id": "55", "key": "DOCS"}]}])
    result = invoke("getPageById", "--id", "123", "--body-format", "storage")
    assert result.exit_code == 0 and json.loads(result.stdout)["body"]["storage"]["value"] == "T", result.output
    assert scoped.roles == ["resolution", "resolution", "operation"]
    assert scoped.requests[0][1] == {"id": 123}
    assert scoped.requests[-1][1] == {"id": 123, "body-format": "storage"}


def test_site_default_refusal_and_explicit_configuration(scoped):
    assert_refusal(invoke("getSpaces"), "getSpaces")
    assert scoped.requests == []
    scoped.seed("getSpaces", [{"results": []}])
    result = invoke("getSpaces", env={"CONFLUENCE_ALLOW_SITE_OPERATIONS": "1"})
    assert result.exit_code == 0 and json.loads(result.stdout) == {"results": []}, (
        result.output
    )
    assert scoped.requests == [("getSpaces", {}, None)] and scoped.roles == [
        "operation"
    ]


def test_list_requires_filter_and_checks_every_space(scoped):
    assert_refusal(invoke("getPages"), "getPages")
    assert scoped.requests == []
    scoped.seed(
        "getSpaces",
        [{"results": [{"id": "55", "key": "DOCS"}, {"id": "66", "key": "ENG"}]}],
    )
    assert_refusal(invoke("getPages", "--space-id", "55,66"), "getPages")
    assert scoped.requests == [("getSpaces", {"ids": [55, 66]}, None)]
    assert scoped.roles == ["resolution"]


def test_space_id_resolves_with_get_spaces_not_self_recursion(scoped):
    scoped.seed("getSpaces", [{"results": [{"id": "55", "key": "DOCS"}]}])
    scoped.seed("getSpaceById", [{"id": "55", "key": "DOCS"}])
    result = invoke("getSpaceById", "--id", "55")
    assert result.exit_code == 0, result.output
    assert scoped.requests == [
        ("getSpaces", {"ids": [55]}, None),
        ("getSpaceById", {"id": 55}, None),
    ]
    assert scoped.roles == ["resolution", "operation"]


@pytest.mark.parametrize(
    "response",
    [
        {"results": []},
        {"results": [{"id": "55", "key": "ENG"}]},
        {"results": [{"id": "55", "key": "DOCS"}, {"id": "66", "key": "DOCS"}]},
        {
            "results": [{"id": "55", "key": "DOCS"}],
            "_links": {"next": "/spaces?cursor=more"},
        },
        Response(503, {"message": "unavailable"}),
    ],
)
def test_unproven_lookup_never_mutates(scoped, response):
    scoped.seed("getSpaces", [response])
    assert_refusal(invoke(*create("--space", "DOCS")), "createPage")
    assert scoped.roles == ["resolution"]


def test_scope_policy_absence_is_default_deny_and_does_not_affect_discovery(scoped):
    assert_refusal(
        invoke("getPageById", "--id", "123", env={"CONFLUENCE_ALLOWED_SPACES": ""}),
        "getPageById",
    )
    assert scoped.requests == []
    result = CliRunner().invoke(
        cli, ["api", "describe", "createPage", "--format", "json"]
    )
    assert result.exit_code == 0 and "x-as-scope" in result.stdout
    assert scoped.requests == []


def test_settings_file_policy_and_environment_precedence(scoped, monkeypatch):
    config = ConfigManager.get_instance()
    config.config["confluence"].update(
        {"allowed_spaces": " DOCS, ENG,DOCS ", "allow_site_operations": True}
    )
    monkeypatch.delenv("CONFLUENCE_ALLOWED_SPACES")
    assert config.get_scope_config() == {
        "scope_allowlist": ("DOCS", "ENG"),
        "scope_allow_site": True,
    }
    monkeypatch.setenv("CONFLUENCE_ALLOWED_SPACES", "")
    monkeypatch.setenv("CONFLUENCE_ALLOW_SITE_OPERATIONS", "false")
    assert config.get_scope_config() == {
        "scope_allowlist": (),
        "scope_allow_site": False,
    }


def test_acceptance_transcript(scoped):
    cases = [
        ("getPageById", "--id", "123"),
        create(),
        create("--space", "ENG"),
        create("--space", "DOCS"),
        ("getSpaces",),
        ("getSpaces",),
    ]
    for number, args in enumerate(cases):
        scoped.requests.clear()
        scoped.roles.clear()
        scoped.seed("getPageById", [{"id": "123", "spaceId": "66"}])
        scoped.seed(
            "getSpaces",
            [{"results": [{"id": "66", "key": "ENG"}]}]
            if number == 0
            else [{"results": [{"id": "55", "key": "DOCS"}]}],
        )
        scoped.seed("createPage", [{"id": "123"}])
        env = {"CONFLUENCE_ALLOW_SITE_OPERATIONS": "1"} if number == 5 else None
        result = invoke(*args, env=env)
        assert result.exit_code == (0 if number in (3, 5) else 4), result.output
        print(
            json.dumps(
                {
                    "argv": ["api", "call", *args],
                    "env": {"CONFLUENCE_ALLOWED_SPACES": "DOCS", **(env or {})},
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit": result.exit_code,
                    "request_count": len(scoped.requests),
                    "roles": scoped.roles,
                    "requests": scoped.requests,
                },
                ensure_ascii=False,
            )
        )


def test_missing_body_identity_refuses_before_any_send(scoped):
    assert_refusal(
        invoke("createPage", "--space", "DOCS", "--body", "-", input="{}"), "createPage"
    )
    assert scoped.requests == []
