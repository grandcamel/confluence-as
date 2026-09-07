"""Offline tests for the Base Document drift command."""

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_base_document_drift.py"
SPEC = importlib.util.spec_from_file_location("drift", SCRIPT)
assert SPEC and SPEC.loader
drift = importlib.util.module_from_spec(SPEC)
sys.path.insert(0, str(ROOT / "scripts"))
SPEC.loader.exec_module(drift)


def document(description="old", include=True):
    paths = {
        "/pages": {
            "get": {
                "operationId": "getPages",
                "description": description,
                "responses": {"200": {"description": "ok"}},
            }
        }
    }
    if not include:
        paths = {}
    return {
        "openapi": "3.0.3",
        "info": {"title": "Fixture", "version": "1.0.0"},
        "paths": paths,
        "components": {"schemas": {"Page": {"type": "object"}}},
    }


@pytest.fixture
def fixture_manifest(tmp_path):
    old = document()
    data = json.dumps(old).encode()
    (tmp_path / "base.json").write_bytes(data)
    overlay = {
        "actions": [
            {
                "target": '$.paths["/pages"].get',
                "x-as-test": "pages",
                "description": "d",
                "x-as-reason": "r",
                "x-as-origin": "o",
                "x-as-evidence": {
                    "url": "https://example.invalid",
                    "date": "2026-09-01",
                },
                "update": {"x-as-paging": {}},
            }
        ]
    }
    (tmp_path / "overlay.json").write_text(json.dumps(overlay))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "format_version": 1,
                "documents": [
                    {
                        "id": "fixture",
                        "file": "base.json",
                        "url": "https://example.invalid/base.json",
                        "declared_version": "1.0.0",
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "overlays": ["overlay.json"],
                    }
                ],
            }
        )
    )
    return manifest


def oasdiff():
    binary = shutil.which("oasdiff") or ROOT.parent / "bin/oasdiff"
    if not Path(binary).is_file():
        pytest.skip("local oasdiff is unavailable")
    return str(binary)


def run(manifest, replacement, *extra):
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
            "--from-file",
            f"fixture={replacement}",
            "--oasdiff",
            oasdiff(),
            *extra,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_identical_document_is_silent(fixture_manifest):
    result = run(fixture_manifest, fixture_manifest.parent / "base.json")
    assert result.returncode == 0
    assert result.stdout == result.stderr == ""


def test_enriched_narrative_change_emits_dry_run_ticket(fixture_manifest):
    replacement = fixture_manifest.parent / "new.json"
    replacement.write_text(json.dumps(document("new narrative")))
    result = run(fixture_manifest, replacement, "--dry-run")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["project"] == {"key": "JAS"} and payload["components"] == [
        {"name": "confluence-as"}
    ]
    assert payload["issuetype"] == {"name": "Task"}
    assert payload["labels"] == ["base-document-drift"]
    assert "getPages (GET /pages)" in payload["description"]
    assert "/paths/~1pages/get/description" in payload["description"]


def test_breaking_removal_emits_ticket(fixture_manifest):
    replacement = fixture_manifest.parent / "new.json"
    replacement.write_text(json.dumps(document(include=False)))
    result = run(fixture_manifest, replacement, "--dry-run")
    assert result.returncode == 0, result.stderr
    assert "Confluence Base Document drift" in result.stdout


def test_oasdiff_failure_is_loud(fixture_manifest):
    replacement = fixture_manifest.parent / "new.json"
    replacement.write_text(json.dumps(document("changed")))
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(fixture_manifest),
            "--from-file",
            f"fixture={replacement}",
            "--oasdiff",
            "/missing/oasdiff",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "oasdiff executable not found" in result.stderr


def test_invalid_manifest_pin_fails_before_diff(fixture_manifest):
    (fixture_manifest.parent / "base.json").write_text(json.dumps(document("corrupt")))
    replacement = fixture_manifest.parent / "new.json"
    replacement.write_text(json.dumps(document("new")))
    result = run(fixture_manifest, replacement)
    assert result.returncode == 1
    assert "does not match manifest pin" in result.stderr


def test_file_ticket_requires_credentials_for_a_finding(fixture_manifest, monkeypatch):
    replacement = fixture_manifest.parent / "new.json"
    replacement.write_text(json.dumps(document("changed")))
    monkeypatch.delenv("JIRA_SITE_URL", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    with pytest.raises(ValueError, match="requires JIRA"):
        drift.file_ticket({"description": "x"})


def test_file_ticket_preflights_credentials_before_matching_documents(
    fixture_manifest, monkeypatch
):
    monkeypatch.delenv("JIRA_SITE_URL", raising=False)
    monkeypatch.delenv("JIRA_EMAIL", raising=False)
    monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
    monkeypatch.setattr(
        sys, "argv", [str(SCRIPT), "--manifest", str(fixture_manifest), "--file-ticket"]
    )
    assert drift.main() == 1


@pytest.mark.parametrize(
    "site",
    [
        "http://jira.example.test",
        "https://user@jira.example.test",
        "https://jira.example.test/?x=1",
    ],
)
def test_file_ticket_rejects_unsafe_site(monkeypatch, site):
    monkeypatch.setenv("JIRA_SITE_URL", site)
    monkeypatch.setenv("JIRA_EMAIL", "worker@example.test")
    monkeypatch.setenv("JIRA_API_TOKEN", "token")
    with pytest.raises(ValueError, match="HTTPS"):
        drift.file_ticket({"description": "x"})


def test_unenriched_nonbreaking_change_is_silent(fixture_manifest):
    replacement = fixture_manifest.parent / "new.json"
    changed = document()
    changed["paths"]["/other"] = {
        "get": {
            "operationId": "getOther",
            "description": "new endpoint",
            "responses": {"200": {"description": "ok"}},
        }
    }
    replacement.write_text(json.dumps(changed))
    result = run(fixture_manifest, replacement)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_unsupported_overlay_target_fails_loudly(fixture_manifest):
    (fixture_manifest.parent / "overlay.json").write_text(
        json.dumps({"actions": [{"target": "$.info", "x-as-test": "bad"}]})
    )
    with pytest.raises(ValueError, match="unsupported enrichment target"):
        drift.enriched_operation_pointers(
            fixture_manifest.parent,
            json.loads(fixture_manifest.read_text())["documents"][0],
        )


@pytest.mark.parametrize(
    "mutation", ["components", "security", "path_parameters", "servers"]
)
def test_shared_dependencies_mark_enriched_operation(fixture_manifest, mutation):
    old = document()
    new = document()
    if mutation == "components":
        new["components"]["schemas"]["Page"]["description"] = "changed"
    elif mutation == "security":
        new["security"] = [{"oauth": []}]
    elif mutation == "servers":
        new["servers"] = [{"url": "https://changed.example.invalid"}]
    else:
        new["paths"]["/pages"]["parameters"] = [{"name": "limit", "in": "query"}]
    record = json.loads(fixture_manifest.read_text())["documents"][0]
    assert drift.changed_enriched_operations(
        old, new, fixture_manifest.parent, record
    ) == ["getPages (GET /pages)"]


def test_file_ticket_posts_adf_payload_without_redirect(monkeypatch):
    captured = {}

    class Response:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Opener:
        def open(self, request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return Response()

    monkeypatch.setenv("JIRA_SITE_URL", "https://jira.example.test")
    monkeypatch.setenv("JIRA_EMAIL", "worker@example.test")
    monkeypatch.setenv("JIRA_API_TOKEN", "token")
    monkeypatch.setattr(drift, "build_opener", lambda *_handlers: Opener())
    drift.file_ticket(
        {
            "project": {"key": "JAS"},
            "issuetype": {"name": "Task"},
            "summary": "drift",
            "description": "heading\nbody",
            "components": [{"name": "confluence-as"}],
            "labels": ["base-document-drift"],
        }
    )
    assert captured["request"].full_url == "https://jira.example.test/rest/api/3/issue"
    body = json.loads(captured["request"].data)
    assert body["fields"]["project"] == {"key": "JAS"}
    assert body["fields"]["issuetype"] == {"name": "Task"}
    assert body["fields"]["description"]["type"] == "doc"
    assert [
        part["content"][0]["text"] for part in body["fields"]["description"]["content"]
    ] == ["heading", "body"]


def test_jira_refusal_does_not_echo_remote_error_or_credentials(monkeypatch):
    from urllib.error import URLError

    monkeypatch.setenv("JIRA_SITE_URL", "https://jira.example.test")
    monkeypatch.setenv("JIRA_EMAIL", "worker@example.test")
    monkeypatch.setenv("JIRA_API_TOKEN", "fixture-secret")

    class Opener:
        def open(self, *_args, **_kwargs):
            raise URLError("fixture-secret in a remote diagnostic")

    monkeypatch.setattr(drift, "build_opener", lambda *_: Opener())
    with pytest.raises(ValueError) as caught:
        drift.file_ticket({"description": "fixture"})
    assert str(caught.value) == "Jira ticket request failed: connection error"


def test_malformed_oasdiff_report_fails_instead_of_becoming_a_ticket():
    with pytest.raises(ValueError, match="invalid JSON"):
        drift._is_breaking("unexpected tool diagnostic")
