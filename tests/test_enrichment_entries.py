"""One discoverable build-seam check for every committed enrichment action."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest
from as_engine.enrichment import entry_cases
from as_engine.overlay import apply_overlay
from referencing import Registry
from referencing.exceptions import NoSuchResource, Unresolvable

SPECS = Path(__file__).resolve().parents[1] / "src/confluence_as/specs"
CASES = list(entry_cases(SPECS))


def reject_retrieval(uri):
    raise NoSuchResource(ref=uri)


def validate_body(instance, schema, document):
    # Local component refs remain rooted in the complete Base Document. The
    # envelope prevents the OpenAPI root being mistaken for a body schema.
    # Retrieval is explicitly disabled, including for nested external refs.
    envelope = {**document, "allOf": [schema]}
    jsonschema.Draft4Validator(
        envelope, registry=Registry(retrieve=reject_retrieval)
    ).validate(instance)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.id)
def test_enrichment_entry(case):
    case.check(validate_body=validate_body)


def test_example_validator_rejects_invalid_bodies_and_external_nested_refs():
    with pytest.raises(jsonschema.ValidationError):
        validate_body({}, {"type": "object", "required": ["spaceId"]}, {})
    with pytest.raises(Unresolvable):
        validate_body({}, {"$ref": "https://example.invalid/no-network"}, {})


@pytest.mark.parametrize("document_id", ["v1", "v2"])
def test_oas_patch_cross_check(document_id, tmp_path):
    manifest = json.loads((SPECS / "manifest.json").read_bytes())
    entry = next(item for item in manifest["documents"] if item["id"] == document_id)
    binary = shutil.which("oas-patch", path=str(Path(sys.executable).parent))
    assert binary, (
        "oas-patch is a required dev dependency for the independent CI cross-check"
    )
    source = SPECS / entry["file"]
    expected = json.loads(source.read_bytes())
    for index, name in enumerate(entry["overlays"]):
        expected = apply_overlay(expected, json.loads((SPECS / name).read_bytes()))
        output = tmp_path / f"{document_id}-{index}.json"
        result = subprocess.run(
            [binary, "overlay", str(source), str(SPECS / name), "-o", str(output)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(output.read_bytes()) == expected, name
        source = output
