"""Committed generator, hand decisions, and compiled tag contracts."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from as_engine.build import compile_product

ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "src/confluence_as/specs"


@pytest.fixture(scope="module")
def compiled(tmp_path_factory):
    out = tmp_path_factory.mktemp("enriched-indexes")
    compile_product(SPECS, out)
    return {
        key: json.loads((out / f"{key}.index.json").read_bytes())
        for key in ("v1", "v2")
    }


def test_regeneration_is_stable_and_preserves_hand_overrides_and_bases(tmp_path):
    specs = tmp_path / "specs"
    shutil.copytree(SPECS, specs)
    before = {p.name: p.read_bytes() for p in specs.iterdir() if p.is_file()}
    # A local hand edit must survive regeneration, not only the known defaults.
    override = specs / "v2.overlay.json"
    hand = json.loads(override.read_bytes())
    hand["info"]["title"] = "Human changes survive regeneration"
    override.write_text(json.dumps(hand) + "\n")
    before[override.name] = override.read_bytes()
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/generate_paging_tags.py"),
            "--spec-dir",
            str(specs),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "HAND REVIEW: getPageAncestors" in result.stdout
    assert {p.name: p.read_bytes() for p in specs.iterdir() if p.is_file()} == before


def test_compiled_index_carries_contract_for_pages_and_prerequisites(compiled):
    ops = compiled["v2"]["operations"]
    assert ops["getPages"]["extensions"]["x-as-paging"] == {
        "style": "cursor",
        "request": {
            "token": {"in": "query", "name": "cursor"},
            "limit": {"in": "query", "name": "limit"},
        },
        "itemsPath": "/results",
        "next": {"kind": "link", "path": "/_links/next"},
    }
    prerequisite = ops["createPage"]["extensions"]["x-as-prerequisites"][0]
    assert prerequisite == {
        "target": {"in": "body", "path": "/spaceId"},
        "alias": "space-key",
        "operationId": "getSpaces",
        "parameter": {"in": "query", "name": "keys", "array": True},
        "resultsPath": "/results",
        "matchPath": "/key",
        "valuePath": "/id",
    }
    assert ops["updatePage"]["extensions"]["x-as-version"] == {
        "operationId": "getPageById",
        "parameters": {"id": {"in": "path", "name": "id"}},
        "responsePath": "/version/number",
        "target": {"in": "body", "path": "/version/number"},
        "increment": 1,
        "overrides": [{"when": {"path": "/status", "equals": "draft"}, "value": 1}],
    }
    assert sum("x-as-paging" in op["extensions"] for op in ops.values()) == 93
    assert (
        sum(
            "x-as-paging" in op["extensions"]
            for op in compiled["v1"]["operations"].values()
        )
        == 37
    )


def test_hand_decisions_do_not_invent_mutation_paging(compiled):
    v2 = compiled["v2"]["operations"]
    for name in ("setSpaceRoleAssignments", "createBulkUserLookup"):
        assert v2[name]["extensions"]["x-as-paging"] == {
            "style": "none",
            "request": {},
            "itemsPath": "/results",
        }
    ancestor = v2["getPageAncestors"]["extensions"]["x-as-paging"]
    assert ancestor["style"] == "ancestor"
    assert ancestor["request"]["token"] == {"in": "path", "name": "id"}
    assert ancestor["next"] == {"kind": "token", "path": "/results/0/id"}
    assert ancestor["merge"] == "prepend"
    v1 = compiled["v1"]["operations"]
    assert v1["getGroups"]["extensions"]["x-as-paging"]["style"] == "start/limit"
    for name in (
        "createOrUpdateAttachments",
        "createAttachment",
        "addLabelsToContent",
        "updateRestrictions",
        "addRestrictions",
        "deleteRestrictions",
        "addLabelsToSpace",
        "getBulkUserLookup",
    ):
        assert v1[name]["extensions"]["x-as-paging"]["style"] == "none"
    assert v1["getAvailableContentStates"]["extensions"]["x-as-paging"][
        "itemsPaths"
    ] == ["/spaceContentStates", "/customContentStates"]


def test_manifest_order_makes_hand_override_win(tmp_path):
    specs = tmp_path / "specs"
    shutil.copytree(SPECS, specs)
    manifest = json.loads((specs / "manifest.json").read_bytes())
    assert all(
        item["overlays"]
        == [f"{item['id']}.paging.overlay.json", f"{item['id']}.overlay.json"]
        for item in manifest["documents"]
    )
    override = specs / "v2.overlay.json"
    hand = json.loads(override.read_bytes())
    generated = json.loads((specs / "v2.paging.overlay.json").read_bytes())
    action = next(
        item
        for item in generated["actions"]
        if item["x-as-test"] == "paging_v2_getPages"
    )
    action["x-as-test"] = "hand_precedence_probe"
    action["update"] = {"x-as-paging": {"request": {"limit": {"name": "hand-wins"}}}}
    hand["actions"].append(action)
    override.write_text(json.dumps(hand))
    out = tmp_path / "out"
    compile_product(specs, out)
    index = json.loads((out / "v2.index.json").read_bytes())
    assert (
        index["operations"]["getPages"]["extensions"]["x-as-paging"]["request"][
            "limit"
        ]["name"]
        == "hand-wins"
    )


def resolve_ref(schema, document):
    while "$ref" in schema:
        ref = schema["$ref"]
        assert ref.startswith("#/")
        schema = document
        for part in ref[2:].split("/"):
            schema = schema[part.replace("~1", "/").replace("~0", "~")]
    return schema


def schema_path(schema, path, document):
    """Resolve a JSON instance path against the vendor's schema positions."""
    schema = resolve_ref(schema, document)
    if not path:
        return schema
    parts = path[1:].split("/")
    for part in parts:
        schema = resolve_ref(schema, document)
        if "allOf" in schema:
            candidates = [resolve_ref(item, document) for item in schema["allOf"]]
            props = {
                key: value
                for item in candidates
                for key, value in item.get("properties", {}).items()
            }
            schema = {**schema, "properties": {**props, **schema.get("properties", {})}}
        schema = (
            schema["items"]
            if schema.get("type") == "array" and part.isdigit()
            else schema["properties"][part.replace("~1", "/").replace("~0", "~")]
        )
    return resolve_ref(schema, document)


def test_all_tag_parameter_and_schema_paths_resolve(compiled):
    manifest = json.loads((SPECS / "manifest.json").read_bytes())
    for entry in manifest["documents"]:
        doc = json.loads((SPECS / entry["file"]).read_bytes())
        ops = compiled[entry["id"]]["operations"]
        for op in ops.values():
            tag = op["extensions"].get("x-as-paging")
            if not tag:
                continue
            assert tag["style"] in {"cursor", "start/limit", "none", "ancestor"}
            for parameter in tag["request"].values():
                assert any(
                    p["name"] == parameter["name"] and p["in"] == parameter["in"]
                    for p in op["parameters"]
                ), op["operationId"]
            vendor_op = doc["paths"][op["path"]][op["method"].lower()]
            response = resolve_ref(vendor_op["responses"]["200"], doc)
            schema = response["content"]["application/json"]["schema"]
            for path in tag.get("itemsPaths", [tag.get("itemsPath")]):
                assert schema_path(schema, path, doc)["type"] == "array", op[
                    "operationId"
                ]
            if "next" in tag and entry["id"] == "v2":
                assert schema_path(schema, tag["next"]["path"], doc)["type"] == "string"
            for path in tag.get("response", {}).values():
                assert schema_path(schema, path, doc)["type"] == "integer"
        if entry["id"] != "v2":
            continue
        prerequisite = ops["createPage"]["extensions"]["x-as-prerequisites"][0]
        lookup = ops[prerequisite["operationId"]]
        assert any(
            p["name"] == "keys" and p["in"] == "query" and p["type"] == "array"
            for p in lookup["parameters"]
        )
        response = doc["paths"][lookup["path"]]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        for field in ("matchPath", "valuePath"):
            assert (
                schema_path(
                    response,
                    prerequisite["resultsPath"] + "/0" + prerequisite[field],
                    doc,
                )["type"]
                == "string"
            )
        body = resolve_ref(doc["paths"]["/pages"]["post"]["requestBody"], doc)[
            "content"
        ]["application/json"]["schema"]
        assert (
            schema_path(body, prerequisite["target"]["path"], doc)["type"] == "string"
        )
        version = ops["updatePage"]["extensions"]["x-as-version"]
        read = ops[version["operationId"]]
        assert any(p["in"] == "path" and p["name"] == "id" for p in read["parameters"])
        schema = doc["paths"][read["path"]]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        assert schema_path(schema, version["responsePath"], doc)["type"] == "integer"
        body = resolve_ref(doc["paths"]["/pages/{id}"]["put"]["requestBody"], doc)[
            "content"
        ]["application/json"]["schema"]
        assert schema_path(body, version["target"]["path"], doc)["type"] == "integer"
