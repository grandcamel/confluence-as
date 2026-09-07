"""Exercise the refresh command offline through its argv/file seam."""

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/refresh_base_documents.py"


@pytest.fixture
def pinned(tmp_path):
    old = {
        "openapi": "3.0.3",
        "info": {"title": "Fixture", "version": "1.0.0"},
        "paths": {
            "/pages": {
                "get": {
                    "operationId": "getPages",
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    data = json.dumps(old).encode()
    (tmp_path / "base.json").write_bytes(data)
    record = {
        "id": "fixture",
        "file": "base.json",
        "url": "https://example.invalid/base.json",
        "declared_version": "1.0.0",
        "sha256": hashlib.sha256(data).hexdigest(),
        "fetched_at": "2026-09-07T00:00:00Z",
        "tier": "primary",
        "overlays": [],
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"format_version": 1, "documents": [record]}))
    old["info"]["version"] = "1.1.0"
    old["paths"]["/new-pages"] = {
        "get": {
            "operationId": "getNewPages",
            "responses": {"200": {"description": "ok"}},
        }
    }
    new = tmp_path / "new.json"
    new.write_text(json.dumps(old))
    return manifest, new


def invoke(manifest, new, binary, doc_id="fixture"):
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
            "--from-file",
            f"{doc_id}={new}",
            "--oasdiff",
            str(binary),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_refresh_real_oasdiff_names_changed_operation_and_appends(pinned):
    binary = shutil.which("oasdiff")
    lane_binary = ROOT.parent / "bin/oasdiff"
    if not binary and lane_binary.is_file():
        binary = str(lane_binary)
    if not binary:
        pytest.skip("oasdiff executable unavailable; install it for refresh acceptance")
    manifest, new = pinned
    result = invoke(manifest, new, binary)
    assert result.returncode == 0, result.stderr
    record = json.loads(manifest.read_text())["documents"][0]
    assert record["declared_version"] == "1.1.0"
    assert record["sha256"] == hashlib.sha256(new.read_bytes()).hexdigest()
    assert record["fetched_at"].endswith("Z")
    assert (manifest.parent / "base.json").read_bytes() == new.read_bytes()
    changelog = manifest.parent / "base.changelog.md"
    first = changelog.read_text()
    assert "/new-pages" in first
    assert invoke(manifest, new, binary).returncode == 0
    assert changelog.read_text().startswith(first)
    assert (
        len(re.findall(r"^## \d{4}-\d{2}-\d{2}T", changelog.read_text(), re.MULTILINE))
        == 2
    )


def test_missing_oasdiff_records_named_skip(pinned):
    manifest, new = pinned
    result = invoke(manifest, new, "/nonexistent/oasdiff")
    assert result.returncode == 0, result.stderr
    assert "SKIPPED: oasdiff executable not found" in result.stderr
    assert "SKIPPED: oasdiff" in (manifest.parent / "base.changelog.md").read_text()


@pytest.mark.parametrize(
    "failure", ["invalid_json", "wrong_shape", "unknown_id", "bad_pin", "diff_error"]
)
def test_refresh_refuses_without_changing_pins_or_sources(pinned, failure):
    manifest, new = pinned
    binary = "/nonexistent/oasdiff"
    doc_id = "fixture"
    if failure == "invalid_json":
        new.write_text("not JSON")
    elif failure == "wrong_shape":
        new.write_text("{}")
    elif failure == "unknown_id":
        doc_id = "unknown"
    elif failure == "bad_pin":
        (manifest.parent / "base.json").write_text("{}")
    else:
        binary = manifest.parent / "failed-oasdiff"
        binary.write_text("#!/bin/sh\necho fixture-diff-error >&2\nexit 2\n")
        binary.chmod(0o755)
    before_manifest = manifest.read_bytes()
    before_source = (manifest.parent / "base.json").read_bytes()
    result = invoke(manifest, new, binary, doc_id)
    assert result.returncode != 0
    assert manifest.read_bytes() == before_manifest
    assert (manifest.parent / "base.json").read_bytes() == before_source
    assert not (manifest.parent / "base.changelog.md").exists()
