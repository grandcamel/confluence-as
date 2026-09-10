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
    responder.seed(
        "createPage",
        [
            {
                "id": "123",
                "body": {
                    "storage": {"representation": "storage", "value": "<p>Fixture</p>"}
                },
            }
        ]
        * 2,
    )
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
    assert (
        result.exit_code == 0
        and json.loads(result.stdout)["body"]["storage"]["value"] == "T"
    ), result.output
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


# JAS-80: these argv cases require the supervisor's normal index regeneration.
_BLOG_RICHTEXT_NOTE = (
    "Tagged body fields accept Markdown or @file; storage is the default write "
    "representation. --representation atlas_doc_format writes stringified ADF. "
    "Reads render Markdown with lossless placeholders; --raw preserves stored "
    "bodies. Use the explicit body-format query parameter to request a read "
    "representation."
)


@pytest.fixture
def blog_scoped(scoped, monkeypatch):
    monkeypatch.setenv("CONFLUENCE_ALLOWED_SPACES", "SBX")
    return scoped


@pytest.fixture(params=["getBlogPostById", "deleteBlogPost"])
def blog_call(request):
    operation = request.param
    flags = (
        ("--confirm",)
        if operation == "deleteBlogPost"
        else ("--body-format", "storage")
    )
    return (operation, "--id", "123", *flags)


def assert_blog_error(result, operation, message, *, code=4):
    assert result.exit_code == code, (result.output, result.exception)
    assert result.stdout == ""
    assert json.loads(result.stderr) == {
        "status": None,
        "messages": [message],
        "operation": operation,
        "note": _BLOG_RICHTEXT_NOTE
        if operation in {"getBlogPostById", "getBlogPosts", "createBlogPost"}
        else (
            "Confluence organizes content in spaces, not Jira projects. Use getSpaces "
            "filters for space type and keys; api describe getSpaces lists the actual "
            "fields and enums."
            if operation == "getSpaces"
            else None
        ),
    }


def assert_blog_refusal(result, operation, reason, *, identity=123, allowed=("SBX",)):
    assert_blog_error(
        result,
        operation,
        f"{operation}: scope identity {identity!r}; "
        f"allowlist={json.dumps(list(allowed))}: {reason}",
    )


def test_blog_get_forwards_options_and_body_only_after_two_metadata_reads(blog_scoped):
    blog_scoped.seed(
        "getBlogPostById",
        [
            {"id": "123", "spaceId": "55"},
            {"id": "123", "body": {"storage": {"value": "<p>Blog</p>"}}},
        ],
    )
    blog_scoped.seed("getSpaces", [{"results": [{"id": "55", "key": "SBX"}]}])
    result = invoke(
        "getBlogPostById",
        "--id",
        "123",
        "--space",
        "SBX",
        "--body-format",
        "storage",
        "--version",
        "2",
        "--status",
        "historical",
        "--include-labels",
        "true",
        "--include-version",
        "false",
        "--get-draft",
        "true",
        "--body",
        "-",
        input='{"client":"payload"}',
    )
    assert result.exit_code == 0, (result.output, result.exception)
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "id": "123",
        "body": {"storage": {"value": "Blog"}},
    }
    assert blog_scoped.requests == [
        ("getBlogPostById", {"id": 123}, None),
        ("getSpaces", {"ids": [55]}, None),
        (
            "getBlogPostById",
            {
                "id": 123,
                "body-format": "storage",
                "version": 2,
                "status": ["historical"],
                "include-labels": True,
                "include-version": False,
                "get-draft": True,
            },
            {"client": "payload"},
        ),
    ]
    assert blog_scoped.roles == ["resolution", "resolution", "operation"]


def test_blog_confirmed_delete_preserves_options_after_two_metadata_reads(blog_scoped):
    blog_scoped.seed("getBlogPostById", [{"id": "123", "spaceId": "55"}])
    blog_scoped.seed("getSpaces", [{"results": [{"id": "55", "key": "SBX"}]}])
    blog_scoped.seed("deleteBlogPost", [Response(204, None)])
    result = invoke(
        "deleteBlogPost",
        "--id",
        "123",
        "--purge",
        "true",
        "--draft",
        "false",
        "--confirm",
    )
    assert result.exit_code == 0, (result.output, result.exception)
    assert result.stderr == ""
    assert json.loads(result.stdout) is None
    assert blog_scoped.requests == [
        ("getBlogPostById", {"id": 123}, None),
        ("getSpaces", {"ids": [55]}, None),
        ("deleteBlogPost", {"id": 123, "purge": True, "draft": False}, None),
    ]
    assert blog_scoped.roles == ["resolution", "resolution", "operation"]


def test_blog_unconfirmed_delete_is_only_a_no_io_preview(blog_scoped):
    result = invoke("deleteBlogPost", "--id", "123", "--purge", "true")
    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "dry_run": True,
        "operationId": "deleteBlogPost",
        "risk": "irreversible",
        "method": "DELETE",
        "path": "/blogposts/123",
        "parameters": {"id": 123, "purge": True},
        "body": None,
    }
    assert blog_scoped.requests == []
    assert blog_scoped.roles == []


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        pytest.param(
            None, "scope resolution requires exactly one matching identity", id="null"
        ),
        pytest.param(
            {}, "scope resolution requires exactly one matching identity", id="empty"
        ),
        pytest.param(
            {"spaceId": "55"},
            "scope resolution requires exactly one matching identity",
            id="missing-id",
        ),
        pytest.param(
            {"id": "999", "spaceId": "55"},
            "scope resolution requires exactly one matching identity",
            id="wrong-id",
        ),
        pytest.param(
            [{"id": "123", "spaceId": "55"}] * 2,
            "scope resolution requires exactly one matching identity",
            id="array-envelope",
        ),
        pytest.param(
            {"id": True, "spaceId": "55"},
            "missing or invalid scope identity",
            id="boolean-id",
        ),
        pytest.param(
            {"id": "123"}, "missing or invalid scope identity", id="missing-space"
        ),
        pytest.param(
            {"id": "123", "spaceId": None},
            "missing or invalid scope identity",
            id="null-space",
        ),
        pytest.param(
            {"id": "123", "spaceId": ""},
            "missing or invalid scope identity",
            id="empty-space",
        ),
        pytest.param(
            {"id": "123", "spaceId": True},
            "missing or invalid scope identity",
            id="boolean-space",
        ),
        pytest.param(
            {"id": "123", "spaceId": []},
            "missing or invalid scope identity",
            id="array-space",
        ),
        pytest.param(
            {"id": "123", "spaceId": {}},
            "missing or invalid scope identity",
            id="object-space",
        ),
        pytest.param(
            {"id": "123", "spaceId": "invalid"},
            "invalid parameter ids: must be an integer",
            id="noninteger-space",
        ),
        pytest.param(
            {
                "id": "123",
                "spaceId": "55",
                "_links": {"next": "/blogposts?cursor=more"},
            },
            "scope resolution result is incomplete",
            id="next",
        ),
        pytest.param(
            {"id": "123", "spaceId": "55", "cursor": "more"},
            "scope resolution result is incomplete",
            id="cursor",
        ),
        pytest.param(
            Response(404, {"message": "private metadata"}),
            "scope resolution could not establish membership",
            id="404",
        ),
        pytest.param(
            Response(500, {"message": "private metadata"}),
            "scope resolution could not establish membership",
            id="500",
        ),
        pytest.param(
            Response(503, {"message": "private metadata"}),
            "scope resolution could not establish membership",
            id="503",
        ),
    ],
)
def test_blog_unproven_blog_metadata_stops_after_first_read(
    blog_scoped, blog_call, response, reason
):
    blog_scoped.seed("getBlogPostById", [response])
    assert_blog_refusal(invoke(*blog_call), blog_call[0], reason)
    assert blog_scoped.requests == [("getBlogPostById", {"id": 123}, None)]
    assert blog_scoped.roles == ["resolution"]


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        pytest.param(
            {}, "scope resolution result is not an array", id="missing-results"
        ),
        pytest.param(
            {"results": {}},
            "scope resolution result is not an array",
            id="object-results",
        ),
        pytest.param(
            {"results": []},
            "scope resolution requires exactly one matching identity",
            id="empty-results",
        ),
        pytest.param(
            {"results": [{"id": "99", "key": "SBX"}]},
            "scope resolution requires exactly one matching identity",
            id="wrong-id",
        ),
        pytest.param(
            {"results": [{"key": "SBX"}]},
            "scope resolution requires exactly one matching identity",
            id="missing-id",
        ),
        pytest.param(
            {"results": [{"id": "55", "key": "SBX"}] * 2},
            "scope resolution requires exactly one matching identity",
            id="duplicate-id",
        ),
        pytest.param(
            {"results": [{"id": "55", "key": "SBX"}, {"id": "55", "key": "ENG"}]},
            "scope resolution requires exactly one matching identity",
            id="conflicting-keys",
        ),
        pytest.param(
            {"results": [{"id": "55"}]},
            "missing or invalid scope identity",
            id="missing-key",
        ),
        pytest.param(
            {"results": [{"id": "55", "key": None}]},
            "missing or invalid scope identity",
            id="null-key",
        ),
        pytest.param(
            {"results": [{"id": "55", "key": True}]},
            "missing or invalid scope identity",
            id="boolean-key",
        ),
        pytest.param(
            {"results": [{"id": "55", "key": ""}]},
            "missing or invalid scope identity",
            id="empty-key",
        ),
        pytest.param(
            {"results": [{"id": "55", "key": "ENG"}]},
            "identity is not allowed",
            id="foreign-space",
        ),
        pytest.param(
            {
                "results": [{"id": "55", "key": "SBX"}],
                "_links": {"next": "/spaces?cursor=more"},
            },
            "scope resolution result is incomplete",
            id="next",
        ),
        pytest.param(
            {"results": [{"id": "55", "key": "SBX"}], "cursor": "more"},
            "scope resolution result is incomplete",
            id="cursor",
        ),
        pytest.param(
            Response(404, {"message": "private metadata"}),
            "scope resolution could not establish membership",
            id="404",
        ),
        pytest.param(
            Response(503, {"message": "private metadata"}),
            "scope resolution could not establish membership",
            id="503",
        ),
    ],
)
def test_blog_unproven_space_metadata_stops_after_second_read(
    blog_scoped, blog_call, response, reason
):
    blog_scoped.seed("getBlogPostById", [{"id": "123", "spaceId": "55"}])
    blog_scoped.seed("getSpaces", [response])
    assert_blog_refusal(invoke(*blog_call), blog_call[0], reason)
    assert blog_scoped.requests == [
        ("getBlogPostById", {"id": 123}, None),
        ("getSpaces", {"ids": [55]}, None),
    ]
    assert blog_scoped.roles == ["resolution", "resolution"]


@pytest.mark.parametrize("allowed", ["", " , , "])
def test_blog_empty_policy_refuses_without_metadata(blog_scoped, blog_call, allowed):
    result = invoke(*blog_call, env={"CONFLUENCE_ALLOWED_SPACES": allowed})
    assert_blog_refusal(result, blog_call[0], "empty allowlist", allowed=())
    assert blog_scoped.requests == []
    assert blog_scoped.roles == []


def test_blog_absent_policy_defaults_to_no_metadata_reads(
    blog_scoped, blog_call, monkeypatch
):
    monkeypatch.delenv("CONFLUENCE_ALLOWED_SPACES")
    ConfigManager.get_instance().config["confluence"].pop("allowed_spaces", None)
    assert_blog_refusal(invoke(*blog_call), blog_call[0], "empty allowlist", allowed=())
    assert blog_scoped.requests == []
    assert blog_scoped.roles == []


@pytest.mark.parametrize("allowed", [None, [], {"SBX": True}, False])
def test_blog_malformed_settings_keep_configuration_error_envelope(
    blog_scoped, blog_call, monkeypatch, allowed
):
    monkeypatch.delenv("CONFLUENCE_ALLOWED_SPACES")
    ConfigManager.get_instance().config["confluence"]["allowed_spaces"] = allowed
    result = invoke(*blog_call)
    assert_blog_error(
        result, None, "allowed_spaces must be comma-separated space keys", code=2
    )
    assert blog_scoped.requests == []
    assert blog_scoped.roles == []


@pytest.mark.parametrize("flags", [(), ("--id", ""), ("--id", "abc"), ("--id", "1.5")])
def test_blog_invalid_id_uses_schema_error_before_any_read(
    blog_scoped, blog_call, flags
):
    operation = blog_call[0]
    result = invoke(operation, *flags, "--confirm")
    message = (
        "invalid parameter id: must be an integer"
        if flags
        else "missing required parameter: id"
    )
    assert_blog_error(result, operation, message, code=2)
    assert blog_scoped.requests == []
    assert blog_scoped.roles == []


@pytest.mark.parametrize("identity", ["0", "-1"])
def test_blog_integer_schema_does_not_invent_a_positive_id_constraint(
    blog_scoped, blog_call, identity
):
    # These are synthetic metadata identities, not assertions about live IDs.
    blog_scoped.seed(
        "getBlogPostById", [{"id": identity, "spaceId": "55"}, {"id": identity}]
    )
    blog_scoped.seed("getSpaces", [{"results": [{"id": "55", "key": "SBX"}]}])
    blog_scoped.seed("deleteBlogPost", [Response(204, None)])
    result = invoke(blog_call[0], "--id", identity, "--confirm")
    assert result.exit_code == 0, (result.output, result.exception)
    assert result.stderr == ""
    assert json.loads(result.stdout) == (
        {"id": identity} if blog_call[0] == "getBlogPostById" else None
    )
    assert blog_scoped.requests == [
        ("getBlogPostById", {"id": int(identity)}, None),
        ("getSpaces", {"ids": [55]}, None),
        (blog_call[0], {"id": int(identity)}, None),
    ]
    assert blog_scoped.roles == ["resolution", "resolution", "operation"]


def test_blog_direct_space_lookup_still_requires_site_permission(blog_scoped):
    result = invoke("getSpaces", "--ids", "55", "--space", "SBX")
    assert_blog_refusal(result, "getSpaces", "site access is disabled", identity=None)
    assert blog_scoped.requests == []
    assert blog_scoped.roles == []


def test_blog_create_explicit_sbx_and_body_id_require_matching_metadata(blog_scoped):
    blog_scoped.seed("getSpaces", [{"results": [{"id": "55", "key": "SBX"}]}])
    blog_scoped.seed("createBlogPost", [{"id": "123", "spaceId": "55"}])
    result = invoke(
        "createBlogPost",
        "--space",
        "SBX",
        "--field",
        'spaceId="55"',
        "--field",
        "title=Blog",
        "--private",
        "true",
    )
    assert result.exit_code == 0, (result.output, result.exception)
    assert result.stderr == ""
    assert json.loads(result.stdout) == {"id": "123", "spaceId": "55"}
    assert blog_scoped.requests == [
        ("getSpaces", {"keys": ["SBX"]}, None),
        ("createBlogPost", {"private": True}, {"spaceId": "55", "title": "Blog"}),
    ]
    assert blog_scoped.roles == ["resolution", "operation"]


@pytest.mark.parametrize("flags", [(), ("--space", "ENG"), ("--space", "")])
def test_blog_create_requires_an_explicit_allowed_space_before_io(blog_scoped, flags):
    result = invoke(
        "createBlogPost", "--field", 'spaceId="55"', "--field", "title=Blog", *flags
    )
    assert_blog_refusal(
        result,
        "createBlogPost",
        "body scope requires an allowed argv identity",
        identity="55",
    )
    assert blog_scoped.requests == []
    assert blog_scoped.roles == []


def test_blog_create_missing_body_id_refuses_before_io(blog_scoped):
    result = invoke("createBlogPost", "--space", "SBX", "--field", "title=Blog")
    assert_blog_refusal(
        result, "createBlogPost", "missing body scope identity", identity=None
    )
    assert blog_scoped.requests == []
    assert blog_scoped.roles == []


def test_blog_create_mismatched_body_id_never_creates(blog_scoped):
    blog_scoped.seed("getSpaces", [{"results": [{"id": "99", "key": "SBX"}]}])
    result = invoke(
        "createBlogPost",
        "--space",
        "SBX",
        "--field",
        'spaceId="55"',
        "--field",
        "title=Blog",
    )
    assert_blog_refusal(
        result,
        "createBlogPost",
        "body identity does not match command identity",
        identity="55",
    )
    assert blog_scoped.requests == [("getSpaces", {"keys": ["SBX"]}, None)]
    assert blog_scoped.roles == ["resolution"]


def test_blog_create_does_not_assume_the_page_space_key_alias(blog_scoped):
    result = invoke(
        "createBlogPost",
        "--space",
        "SBX",
        "--space-key",
        "SBX",
        "--field",
        "title=Blog",
    )
    assert_blog_error(result, "createBlogPost", "Unknown flag: --space-key", code=2)
    assert blog_scoped.requests == []
    assert blog_scoped.roles == []


def test_blog_list_explicit_sbx_space_and_exact_blog_id_preserve_filters(blog_scoped):
    blog_scoped.seed("getSpaces", [{"results": [{"id": "55", "key": "SBX"}]}])
    blog_scoped.seed("getBlogPosts", [{"results": [{"id": "123", "spaceId": "55"}]}])
    result = invoke("getBlogPosts", "--space", "SBX", "--space-id", "55", "--id", "123")
    assert result.exit_code == 0, (result.output, result.exception)
    assert result.stderr == ""
    assert json.loads(result.stdout) == {"results": [{"id": "123", "spaceId": "55"}]}
    assert blog_scoped.requests == [
        ("getSpaces", {"ids": [55]}, None),
        ("getBlogPosts", {"space-id": [55], "id": [123]}, None),
    ]
    assert blog_scoped.roles == ["resolution", "operation"]


def test_blog_list_exact_id_does_not_replace_space_filter(blog_scoped):
    result = invoke("getBlogPosts", "--space", "SBX", "--id", "123")
    assert_blog_refusal(
        result, "getBlogPosts", "missing or invalid scope identity", identity=None
    )
    assert blog_scoped.requests == []
    assert blog_scoped.roles == []


@pytest.mark.parametrize(
    ("flags", "reason"),
    [
        ((), "identity is not allowed"),
        (("--space", "SBX"), "tagged identity does not match command identity"),
    ],
)
def test_blog_list_foreign_space_in_filter_never_sends_list(blog_scoped, flags, reason):
    blog_scoped.seed(
        "getSpaces",
        [{"results": [{"id": "55", "key": "SBX"}, {"id": "66", "key": "ENG"}]}],
    )
    result = invoke("getBlogPosts", "--space-id", "55,66", "--id", "123", *flags)
    assert_blog_refusal(result, "getBlogPosts", reason, identity=[55, 66])
    assert blog_scoped.requests == [("getSpaces", {"ids": [55, 66]}, None)]
    assert blog_scoped.roles == ["resolution"]
