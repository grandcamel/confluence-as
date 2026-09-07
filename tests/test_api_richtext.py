"""Phase-B argv acceptance with valid seeded bodies and recorded scope reads."""

from __future__ import annotations

import json

import pytest
from as_engine.compiler import compile_document
from as_engine.converters import validate_adf
from as_engine.index import ProductIndexes
from as_engine.responder import Responder
from as_engine.surface import Surface

from confluence_as.engine import create_surface
from tests.test_api_scope import invoke
from tests.test_api_scope import scoped as scoped

MENTION = {"type": "mention", "attrs": {"id": "account-7", "text": "@Ada"}}
DOC = {
    "type": "doc",
    "version": 1,
    "content": [{"type": "paragraph", "content": [MENTION]}],
}


def seed_read(wire, body):
    wire.seed("getPageById", [{"id": "123", "spaceId": "55"}, body])
    wire.seed("getSpaces", [{"results": [{"id": "55", "key": "DOCS"}]}])


def seed_write(wire, *, lookup=False):
    metadata = {"id": "123", "spaceId": "55", "body": {"view": "unused metadata"}}
    wire.seed(
        "getPageById",
        [
            metadata,
            metadata,
            {"version": {"number": 7}, "body": {"view": "unused version body"}},
        ]
        if lookup
        else [metadata],
    )
    wire.seed(
        "getSpaces", [{"results": [{"id": "55", "key": "DOCS"}]}] * (2 if lookup else 1)
    )
    wire.seed("updatePage", [{"id": "123", "version": {"number": 8}}])


def write_args(*extra, version=True):
    return (
        "updatePage",
        "--id",
        "123",
        "--confirm",
        "--field",
        'id="123"',
        "--field",
        "title=Notes",
        "--field",
        "status=current",
        *(("--version", "8") if version else ()),
        *extra,
    )


def page():
    return {
        "id": "123",
        "title": "Notes",
        "version": {"number": 7},
        "body": {
            "atlas_doc_format": {
                "representation": "atlas_doc_format",
                "value": json.dumps(DOC),
                "metadata": {"kept": True},
            }
        },
    }


@pytest.mark.parametrize("representation", [None, "atlas_doc_format"])
def test_update_markdown_file_envelope_at_argv(scoped, tmp_path, representation):
    file = tmp_path / "notes.md"
    file.write_text("# Notes\n\nHello **world**", encoding="utf-8")
    seed_write(scoped)
    extra = ("--representation", representation) if representation else ()
    result = invoke(*write_args("--field", "body=@" + str(file), *extra))
    assert result.exit_code == 0 and result.stderr == "", result.output
    assert scoped.roles == ["resolution", "resolution", "operation"]
    assert scoped.requests[:2] == [
        ("getPageById", {"id": 123}, None),
        ("getSpaces", {"ids": [55]}, None),
    ]
    body = scoped.requests[-1][2]
    assert body["version"] == {"number": 8} and body["title"] == "Notes"
    if representation:
        assert body["body"]["representation"] == representation
        document = json.loads(body["body"]["value"])
        assert validate_adf(document)
        assert document["content"][0]["type"] == "heading"
    else:
        assert body["body"] == {
            "representation": "storage",
            "value": "<h1>Notes</h1><p>Hello <strong>world</strong></p>",
        }


def test_read_mention_file_round_trip_and_raw_are_separate_calls(scoped, tmp_path):
    seed_read(scoped, page())
    result = invoke("getPageById", "--id", "123", "--body-format", "atlas_doc_format")
    assert result.exit_code == 0, result.output
    rendered = json.loads(result.stdout)
    value = rendered["body"]["atlas_doc_format"]["value"]
    assert '{{as:1:adf:inline:mention:"@Ada":' in value
    assert rendered["body"]["atlas_doc_format"]["metadata"] == {"kept": True}
    assert scoped.requests[0][1] == {"id": 123}
    assert scoped.requests[-1][1] == {"id": 123, "body-format": "atlas_doc_format"}
    file = tmp_path / "read.md"
    file.write_text(value, encoding="utf-8")
    seed_write(scoped)
    result = invoke(
        *write_args(
            "--representation", "atlas_doc_format", "--field", "body=@" + str(file)
        )
    )
    assert result.exit_code == 0, result.output
    restored = json.loads(scoped.requests[-1][2]["body"]["value"])
    assert restored == DOC and validate_adf(restored)
    seed_read(scoped, page())
    result = invoke(
        "getPageById", "--id", "123", "--body-format", "atlas_doc_format", "--raw"
    )
    assert result.exit_code == 0 and json.loads(result.stdout) == page(), result.output


@pytest.mark.parametrize("text", ["", "#", "null", "123", '{"not": "a body"}'])
def test_empty_and_json_looking_adf_fields_validate(scoped, text):
    seed_write(scoped)
    result = invoke(
        *write_args("--representation", "atlas_doc_format", "--field", "body=" + text)
    )
    assert result.exit_code == 0, result.output
    document = json.loads(scoped.requests[-1][2]["body"]["value"])
    assert validate_adf(document)
    if text in ("null", "123", '{"not": "a body"}'):
        assert document["content"][0]["content"][0]["text"] == text


def test_raw_on_write_keeps_input_conversion_and_scope_guard(scoped):
    seed_write(scoped)
    scoped.seed("updatePage", [page()])
    result = invoke(*write_args("--raw", "--field", "body=Hi"))
    assert result.exit_code == 0 and json.loads(result.stdout) == page(), result.output
    assert scoped.requests[-1][2]["body"] == {
        "representation": "storage",
        "value": "<p>Hi</p>",
    }
    assert scoped.roles == ["resolution", "resolution", "operation"]


def test_version_pipeline_keeps_poisoned_lookup_bodies_raw(scoped):
    seed_write(scoped, lookup=True)
    result = invoke(
        *write_args(
            "--field", "body=Hi", "--representation", "atlas_doc_format", version=False
        )
    )
    assert result.exit_code == 0, result.output
    assert [r[0] for r in scoped.requests] == [
        "getPageById",
        "getSpaces",
        "getPageById",
        "getSpaces",
        "getPageById",
        "updatePage",
    ]
    assert scoped.roles == [
        "resolution",
        "resolution",
        "resolution",
        "resolution",
        "operation",
        "operation",
    ]
    assert all(r[1] == {"id": 123} for r in scoped.requests if r[0] == "getPageById")
    sent = scoped.requests[-1][2]
    assert sent["version"] == {"number": 8} and validate_adf(
        json.loads(sent["body"]["value"])
    )


@pytest.mark.parametrize(
    "flags",
    [
        ("--representation", "wiki", "--field", "body=T"),
        (
            "--field",
            "body.representation=storage",
            "--field",
            "body.value=<p>T</p>",
            "--representation",
            "atlas_doc_format",
        ),
        (
            "--field",
            "body.representation=atlas_doc_format",
            "--field",
            'body.value="bad"',
        ),
    ],
)
def test_invalid_options_fail_before_scope_reads(scoped, flags):
    result = invoke(*write_args(*flags))
    assert result.exit_code == 2 and result.stdout == "", result.output
    assert scoped.requests == []


@pytest.mark.parametrize("kind", ["missing", "invalid-utf8", "directory"])
def test_richtext_file_errors_before_any_lookup(scoped, tmp_path, kind):
    file = tmp_path / kind
    if kind == "invalid-utf8":
        file.write_bytes(b"\xff")
    elif kind == "directory":
        file.mkdir()
    result = invoke(*write_args("--field", "body=@" + str(file)))
    assert result.exit_code == 2 and "cannot read rich-text file" in result.stderr
    assert scoped.requests == []


def test_unsupported_raw_write_has_no_reads(scoped):
    result = invoke("deletePage", "--id", "123", "--confirm", "--raw")
    assert result.exit_code == 2 and scoped.requests == []


def test_optional_body_validation_exposes_vendor_oneof_overlap(scoped):
    seed_write(scoped)
    result = invoke(
        *write_args(
            "--field",
            "body=Hi",
            "--representation",
            "atlas_doc_format",
            "--validate-body",
        )
    )
    assert result.exit_code == 2, result.output
    assert json.loads(result.stderr)["messages"] == ["body.body: does not match oneOf"]
    assert scoped.roles == ["resolution", "resolution"]
    # A separately accepted identical conversion produces valid ADF; the
    # optional validator diagnoses the vendor envelope union, not the document.
    seed_write(scoped)
    result = invoke(
        *write_args("--field", "body=Hi", "--representation", "atlas_doc_format")
    )
    assert result.exit_code == 0, result.output
    assert validate_adf(json.loads(scoped.requests[-1][2]["body"]["value"]))


def test_preview_converts_locally_without_lookups(scoped):
    result = invoke(
        "updatePage",
        "--id",
        "123",
        "--field",
        "body=Hi",
        "--representation",
        "atlas_doc_format",
    )
    assert result.exit_code == 0 and scoped.requests == [], result.output
    preview = json.loads(result.stdout)
    assert preview["dry_run"] and "version_requirement" in preview
    assert validate_adf(json.loads(preview["body"]["body"]["value"]))


def test_overlay_public_describe_and_scope_metadata_survive(scoped):
    surface = create_surface(transport="responder")
    for name in ("createPage", "updatePage", "createBlogPost", "updateBlogPost"):
        desc = surface.describe(name)
        assert desc["extensions"]["x-as-representation"] == {
            "default": "storage",
            "alternatives": ["atlas_doc_format"],
        }
        assert desc["extensions"]["x-as-richtext"][0]["request"] == {
            "path": "/body",
            "shape": "envelope",
        }
    for name, path in (
        ("getPages", "/body"),
        ("getBlogPosts", "/body"),
        ("getPageVersions", "/page/body"),
        ("getBlogPostVersions", "/blogpost/body"),
    ):
        assert surface.describe(name)["extensions"]["x-as-richtext"][0]["response"] == {
            "path": path,
            "shape": "representation-map",
            "itemsPath": "/results",
        }
    assert surface.describe("updatePage")["extensions"]["x-as-scope"]["name"] == "id"
    assert scoped.requests == []


def scalar_surface(tmp_path, monkeypatch):
    op = {
        "operationId": "formatExample",
        "parameters": [
            {
                "name": "elapsed",
                "in": "query",
                "schema": {"type": "integer", "format": "int64"},
            }
        ],
        "x-as-format": [
            {"target": {"in": "query", "name": "elapsed"}, "format": "duration"},
            {"target": {"in": "body", "path": "/dueDate"}, "format": "date"},
        ],
    }
    (tmp_path / "index.json").write_text(
        json.dumps(
            compile_document({"openapi": "3.0.3", "paths": {"/format": {"post": op}}})
        )
    )
    (tmp_path / "catalog.json").write_text(
        json.dumps(
            {
                "format_version": 1,
                "documents": [{"id": "test", "tier": "primary", "file": "index.json"}],
            }
        )
    )
    indexes = ProductIndexes(tmp_path)
    wire = Responder(indexes.get("test"), body={"ok": True})
    surface = Surface(indexes, lambda *_: wire)
    monkeypatch.setattr(
        "confluence_as.cli.commands.api_cmds.create_surface", lambda **_: surface
    )
    return wire


def test_scalar_fields_through_same_argv_registry(scoped, tmp_path, monkeypatch):
    wire = scalar_surface(tmp_path, monkeypatch)
    result = invoke(
        "formatExample", "--elapsed", "2h30m", "--field", "dueDate=2028-02-29"
    )
    assert result.exit_code == 0, result.output
    assert wire.requests == [
        ("formatExample", {"elapsed": 9000}, {"dueDate": "2028-02-29"})
    ]


def test_acceptance_transcript(scoped, tmp_path, monkeypatch):
    """Print the exact offline argv/stdout/stderr/exit/transport receipts."""
    file = tmp_path / "notes.md"
    file.write_text("# Notes\n\nHello **world**", encoding="utf-8")
    placeholder = tmp_path / "round-trip.md"

    def run(label, args, *, wire=scoped):
        wire.requests.clear()
        if hasattr(wire, "roles"):
            wire.roles.clear()
        result = invoke(*args)
        print(
            "TRANSCRIPT "
            + json.dumps(
                {
                    "case": label,
                    "argv": ["confluence-as", "api", "call", *args],
                    "env": {
                        "CONFLUENCE_ALLOWED_SPACES": "DOCS",
                        "CONFLUENCE_AS_TRANSPORT": "responder",
                    },
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit": result.exit_code,
                    "roles": getattr(wire, "roles", []),
                    "requests": wire.requests,
                },
                ensure_ascii=False,
            )
        )
        return result

    for name, extra in (
        ("storage-default", ()),
        ("adf-override", ("--representation", "atlas_doc_format")),
    ):
        seed_write(scoped)
        result = run(name, write_args("--field", "body=@" + str(file), *extra))
        assert result.exit_code == 0, result.output
        if extra:
            assert validate_adf(json.loads(scoped.requests[-1][2]["body"]["value"]))
    seed_read(scoped, page())
    result = run(
        "read-mention",
        ("getPageById", "--id", "123", "--body-format", "atlas_doc_format"),
    )
    assert result.exit_code == 0, result.output
    placeholder.write_text(
        json.loads(result.stdout)["body"]["atlas_doc_format"]["value"], encoding="utf-8"
    )
    seed_read(scoped, page())
    assert (
        run(
            "read-raw",
            (
                "getPageById",
                "--id",
                "123",
                "--body-format",
                "atlas_doc_format",
                "--raw",
            ),
        ).exit_code
        == 0
    )
    seed_write(scoped)
    assert (
        run(
            "mention-round-trip",
            write_args(
                "--field",
                "body=@" + str(placeholder),
                "--representation",
                "atlas_doc_format",
            ),
        ).exit_code
        == 0
    )
    assert json.loads(scoped.requests[-1][2]["body"]["value"]) == DOC
    assert (
        run(
            "missing-file",
            write_args("--field", "body=@" + str(tmp_path / "absent.md")),
        ).exit_code
        == 2
    )
    assert scoped.requests == []
    assert (
        run(
            "unsupported-representation",
            write_args("--representation", "wiki", "--field", "body=T"),
        ).exit_code
        == 2
    )
    assert scoped.requests == []
    seed_write(scoped)
    assert (
        run(
            "final-body-validation",
            write_args(
                "--field",
                "body=Hi",
                "--representation",
                "atlas_doc_format",
                "--validate-body",
            ),
        ).exit_code
        == 2
    )
    assert [r[0] for r in scoped.requests] == ["getPageById", "getSpaces"]
    scalar = scalar_surface(tmp_path, monkeypatch)
    assert (
        run(
            "scalar-duration-date",
            ("formatExample", "--elapsed", "2h30m", "--field", "dueDate=2028-02-29"),
            wire=scalar,
        ).exit_code
        == 0
    )
    assert scalar.requests == [
        ("formatExample", {"elapsed": 9000}, {"dueDate": "2028-02-29"})
    ]


@pytest.mark.parametrize(
    "body",
    [
        {"storage": {"representation": "string", "value": "string"}},
        {"atlas_doc_format": {"representation": "atlas_doc_format", "value": "string"}},
        {"view": {"representation": "view", "value": "<p>T</p>"}},
    ],
)
def test_malformed_maps_are_not_hidden_by_success_fixtures(scoped, body):
    seed_read(scoped, {"id": "123", "body": body})
    result = invoke("getPageById", "--id", "123", "--body-format", "storage")
    assert result.exit_code == 2 and result.stdout == "", result.output
    assert scoped.roles == ["resolution", "resolution", "operation"]
