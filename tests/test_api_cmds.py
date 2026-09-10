"""API argv acceptance against the responder; all HTTP intercepted or forbidden."""

from __future__ import annotations

import json
from dataclasses import replace
from unittest.mock import Mock

import pytest
import requests
import responses
from as_engine.responder import Responder
from as_engine.surface import Surface
from as_engine.transforms import Context
from as_engine.transforms.formats import Formats
from as_engine.transforms.richtext import RichText
from as_engine.transport import Response
from click.testing import CliRunner

from confluence_as.cli.commands import api_cmds
from confluence_as.cli.main import cli
from confluence_as.config_manager import ConfigManager
from confluence_as.engine import create_surface


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("CONFLUENCE_AS_TRANSPORT", "responder")
    monkeypatch.setenv("CONFLUENCE_ALLOWED_SPACES", "S1,S4,S5")
    monkeypatch.setenv("CONFLUENCE_ALLOW_SITE_OPERATIONS", "1")
    original_call = Responder.call

    def metadata(self, operation, parameters, body):
        if operation.extensions.get("x-as-resolution-read"):
            # Explicit fixture-space records served only for metadata reads.
            spaces = [{"id": str(i), "key": f"S{i}"} for i in (1, 4, 5)]
            if operation.operationId == "getSpaces":
                rows = [
                    row
                    for row in spaces
                    if (
                        row["key"] in parameters.get("keys", [])
                        or int(row["id"]) in parameters.get("ids", [])
                    )
                ]
                return Response(200, {"results": rows})
            if operation.operationId == "getPageById" and parameters == {"id": 1}:
                return Response(200, {"id": "1", "spaceId": "5"})
            raise AssertionError("unexpected metadata lookup")
        return original_call(self, operation, parameters, body)

    monkeypatch.setattr(Responder, "call", metadata)

    # JAS-38: bounded schema generation cannot synthesize an encoded document.
    # Seed only success defaults; forced errors keep the original responder path.
    def richtext_responder(index, *, status=200):
        responder = Responder(index, status=status)
        if 200 <= status < 300:
            page = {
                "id": "1",
                "spaceId": "5",
                "status": "current",
                "version": {"number": 1},
                "body": {
                    "storage": {"representation": "storage", "value": "<p>Fixture</p>"}
                },
            }
            responder.seed("getPages", [{"results": [page]}])
            responder.seed("createPage", [page])
            responder.seed("updatePage", [page])
        return responder

    monkeypatch.setattr("confluence_as.engine.Responder", richtext_responder)

    def forbidden(*args, **kwargs):
        raise AssertionError("HTTP attempted by argv responder test")

    monkeypatch.setattr(requests.Session, "send", forbidden)


def invoke(*args, input=None):
    args = list(args)
    if "call" in args:
        operation = args[args.index("call") + 1]
        if operation in {"getPages", "get-pages"} and "--space-id" not in args:
            args.extend(["--space-id", "5"])
        if operation == "createPage" and "--space" not in args:
            args.extend(["--space", "S5"])
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
    assert calls[0] == ("getSpaces", {"ids": [4, 5]}, None)
    assert len(calls) == 2
    result = invoke(
        "call",
        "createPage",
        "--space",
        "S1",
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
        if not operation.extensions.get("x-as-resolution-read"):
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
    assert (
        invoke("call", "createPage", "--body", "-", input='{"spaceId":5}').exit_code
        == 0
    )
    failure = invoke(
        "--respond-with",
        "400",
        "call",
        "createPage",
        "--body",
        "-",
        input='{"spaceId":5}',
    )
    assert failure.exit_code == 2
    assert "body.spaceId: must be string" in json.loads(failure.stderr)["messages"]


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
    assert {"adf", "paging", "risk", "scope"} <= set(
        invoke("topics").stdout.splitlines()
    )
    assert (
        json.loads(invoke("topics", "--format", "json").stdout)
        == invoke("topics").stdout.splitlines()
    )


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
    config.get_scope_config.return_value = {
        "scope_allowlist": ("S5",),
        "scope_allow_site": True,
    }
    monkeypatch.setattr(ConfigManager, "get_instance", lambda: config)
    surface = create_surface(transport="http")
    with responses.RequestsMock() as wire:
        # responses intercepts HTTPAdapter.send; remove the stricter test guard only inside it.
        monkeypatch.setattr(requests.Session, "send", ORIGINAL_SEND)
        wire.get(
            "https://offline.invalid/wiki/api/v2/pages?limit=5&space-id=5",
            json={"results": [{"id": "10"}]},
        )
        wire.get(
            "https://offline.invalid/wiki/api/v2/spaces?ids=5",
            json={"results": [{"id": "5", "key": "S5"}]},
        )
        assert surface.call("getPages", {"limit": "5", "space-id": [5]}).body == {
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
            surface.call("getPages", {"space-id": [5]})
        assert caught.value.code == 4 and "No permission" in caught.value.messages


ORIGINAL_SEND = requests.Session.send


def test_string_array_numeric_values_preserved():
    result = invoke("call", "getSpaces", "--keys", "123")
    assert result.exit_code == 0, result.output
    result = invoke("call", "getPages", "--id", "[broken")
    assert result.exit_code == 2 and "Invalid JSON array" in result.stderr


@pytest.fixture
def guarded_preview(monkeypatch):
    surface = create_surface(transport="responder")
    attempts = dict.fromkeys(("call", "transport", "config", "credentials", "send"), 0)

    def forbid(kind):
        def denied(*args, **kwargs):
            attempts[kind] += 1
            raise AssertionError(f"preview attempted {kind}")

        return denied

    monkeypatch.setattr(surface, "call", forbid("call"))
    monkeypatch.setattr(Surface, "call", forbid("call"))
    monkeypatch.setattr(surface, "transport_factory", forbid("transport"))
    monkeypatch.setattr(ConfigManager, "get_instance", forbid("config"))
    monkeypatch.setattr(ConfigManager, "get_scope_config", forbid("config"))
    monkeypatch.setattr(ConfigManager, "get_api_config", forbid("config"))
    monkeypatch.setattr(ConfigManager, "get_credentials", forbid("credentials"))
    monkeypatch.setattr(Responder, "call", forbid("send"))
    monkeypatch.setattr(requests.Session, "send", forbid("send"))
    monkeypatch.setattr(api_cmds, "create_surface", lambda **kwargs: surface)
    yield surface, attempts
    assert attempts == dict.fromkeys(attempts, 0), attempts


@pytest.mark.parametrize(
    ("representation", "raw"),
    [("storage", False), ("storage", True), ("atlas_doc_format", True)],
)
def test_preview_converts_markdown_with_local_version_and_inert_origin(
    guarded_preview, monkeypatch, representation, raw
):
    surface, _attempts = guarded_preview
    observed = []
    original = RichText.request
    inputs = []
    original_build = api_cmds.build_body

    def record_body(*args, **kwargs):
        body = original_build(*args, **kwargs)
        inputs.append(body)
        return body

    def observe(self, context, tag):
        observed.append((context, context.origin()))
        return original(self, context, tag)

    monkeypatch.setattr(RichText, "request", observe)
    monkeypatch.setattr(api_cmds, "build_body", record_body)
    result = invoke(
        "call",
        "updatePage",
        "--id",
        "123",
        "--version",
        "7",
        "--field",
        "title=Preview",
        "--field",
        "body=**Preview**",
        "--representation",
        representation,
        *(["--raw"] if raw else []),
    )
    assert result.exit_code == 0 and result.stderr == "", result.output
    preview = json.loads(result.stdout)
    assert preview["dry_run"] is True
    assert preview["operationId"] == "updatePage"
    assert (preview["method"], preview["path"], preview["parameters"]) == (
        "PUT",
        "/pages/123",
        {"id": 123},
    )
    assert preview["body"]["title"] == "Preview"
    assert preview["body"]["version"] == {"number": 7}
    assert inputs == [{"title": "Preview", "body": "**Preview**"}]
    assert "version_requirement" not in preview
    envelope = preview["body"]["body"]
    assert envelope["representation"] == representation
    if representation == "storage":
        assert "<strong>Preview</strong>" in envelope["value"]
    else:
        adf = json.loads(envelope["value"])
        assert adf["type"] == "doc"
        assert adf["content"][0]["content"][0] == {
            "type": "text",
            "text": "Preview",
            "marks": [{"type": "strong"}],
        }
    assert len(observed) == 1
    context, origin = observed[0]
    document, index, operation = surface.resolve("updatePage")
    assert isinstance(context, Context)
    assert context.document == document == "v2"
    assert context.index is index and context.operation is operation
    assert context.representation == representation and context.raw is raw
    assert origin is None
    assert context.scope_allowlist == () and context.scope_allow_site is False
    assert context.scope_send is None and context.scope_argv_identity is None
    assert context.scope_resolution_rules == {}


def test_preview_keeps_explicit_storage_body_with_raw(guarded_preview):
    body = {
        "title": "Preview",
        "body": {"representation": "storage", "value": "<p>Stored</p>"},
        "version": {"number": 7},
    }
    result = invoke(
        "call",
        "updatePage",
        "--id",
        "123",
        "--body",
        "-",
        "--raw",
        "--representation",
        "storage",
        input=json.dumps(body),
    )
    assert result.exit_code == 0 and result.stderr == "", result.output
    assert json.loads(result.stdout)["body"] == body


@pytest.mark.parametrize(
    ("name", "document", "arguments", "path"),
    [
        ("getPages", "v2", ("--space-id", "5"), "/pages"),
        ("searchByCQL", "v1", ("--cql", "type=page"), "/wiki/rest/api/search"),
    ],
)
def test_preview_scalar_conversion_preserves_resolved_document_and_paging(
    guarded_preview, monkeypatch, name, document, arguments, path
):
    surface, _attempts = guarded_preview
    resolved_document, index, operation = surface.resolve(name)
    # Neither product index currently declares scalar formats. Enrich only this
    # in-memory operation to exercise the real hook and the existing CLI schema.
    tagged = replace(
        operation,
        extensions={
            **operation.extensions,
            "x-as-risk": "destructive",
            "x-as-format": [
                {"target": {"in": "query", "name": "limit"}, "format": "duration"}
            ],
        },
    )
    index.operations[name] = tagged
    observed = []
    original = Formats.request

    def observe(self, context, tag):
        observed.append(context)
        return original(self, context, tag)

    monkeypatch.setattr(Formats, "request", observe)
    result = invoke(
        "call", name, *arguments, "--all", "--limit", "5", "--parameter-limit", "1m"
    )
    assert result.exit_code == 0 and result.stderr == "", result.output
    preview = json.loads(result.stdout)
    assert preview["dry_run"] is True and preview["path"] == path
    assert preview["parameters"]["limit"] == 60
    assert len(observed) == 1
    context = observed[0]
    assert isinstance(context, Context)
    assert context.document == resolved_document == document
    assert context.index is index and context.operation is tagged
    assert context.all_pages is True and context.limit == 5
    assert context.origin() is None
    invalid = invoke("call", name, *arguments, "--limit", "1m1h")
    assert invalid.exit_code == 2 and invalid.stdout == "", invalid.output
    error = json.loads(invalid.stderr)
    assert error["operation"] == name and error["status"] is None
    assert "duration requires ordered, nonrepeated" in " ".join(error["messages"])
    assert len(observed) == 1  # Invalid parameters fail before the request hook.


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (("--id", "bad"), "invalid parameter id"),
        ((), "missing required parameter: id"),
        (
            ("--id", "123", "--version", "7", "--field", "version.number=8"),
            "conflicting --version and body version",
        ),
        (
            ("--id", "123", "--representation", "wrong"),
            "unsupported rich-text representation",
        ),
        (
            (
                "--id",
                "123",
                "--raw",
                "--field",
                "body.representation=storage",
                "--field",
                "body.value=42",
            ),
            "rich-text value must be a string",
        ),
    ],
)
def test_preview_invalid_inputs_have_usage_envelope_without_io(
    guarded_preview, arguments, message
):
    result = invoke("call", "updatePage", *arguments)
    assert result.exit_code == 2 and result.stdout == "", result.output
    error = json.loads(result.stderr)
    assert set(error) == {"status", "messages", "operation", "note"}
    assert error["status"] is None and error["operation"] == "updatePage"
    assert message in " ".join(error["messages"])


def test_preview_alias_remains_unresolved_and_conflicting_id_is_refused(
    guarded_preview,
):
    surface, _attempts = guarded_preview
    _, index, operation = surface.resolve("createPage")
    index.operations["createPage"] = replace(
        operation, extensions={**operation.extensions, "x-as-risk": "destructive"}
    )
    args = ("call", "createPage", "--space-key", "S5", "--field", "title=Preview")
    result = invoke(*args)
    assert result.exit_code == 0 and result.stderr == "", result.output
    preview = json.loads(result.stdout)
    assert preview["dry_run"] is True
    assert preview["unresolved_aliases"] == {"space-key": "S5"}
    assert preview["body"] == {"title": "Preview"}
    conflict = invoke(*args, "--field", 'spaceId="5"')
    assert conflict.exit_code == 2 and conflict.stdout == "", conflict.output
    error = json.loads(conflict.stderr)
    assert error["status"] is None and error["operation"] == "createPage"
    assert error["messages"] == ["conflicting id and --space-key"]


@pytest.mark.parametrize(
    ("capability", "message"),
    [
        ("invoke", "Preview cannot invoke operations"),
        ("send", "Preview cannot send requests"),
    ],
)
def test_preview_denies_hook_io_with_the_specific_usage_error(
    guarded_preview, monkeypatch, capability, message
):
    attempted = []

    def attempt(self, context, tag):
        attempted.append(capability)
        if capability == "invoke":
            context.invoke("getPageById", {"id": 123}, None, all_pages=False)
        else:
            context.send({"id": 123}, None)

    monkeypatch.setattr(RichText, "request", attempt)
    result = invoke("call", "updatePage", "--id", "123", "--field", "title=Preview")
    assert result.exit_code == 2 and result.stdout == "", result.output
    error = json.loads(result.stderr)
    assert error["status"] is None and error["operation"] == "updatePage"
    assert error["messages"] == [message]
    assert attempted == [capability]
