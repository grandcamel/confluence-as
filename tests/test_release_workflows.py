"""Release boundaries: immutable compiler, correct registry, no implicit writes."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"
CORE_SHA256 = "ac4cb0b07effbecff812652a33aea54b036971e883d3fe349428c6d723d90d83"


def test_all_build_workflows_use_one_hash_bound_compiler():
    for name in ("publish", "test", "drift"):
        workflow = (WORKFLOWS / f"{name}.yml").read_text()
        assert f"as_engine-0.1.2-py3-none-any.whl#sha256={CORE_SHA256}" in workflow
        assert 'pip install $BUILD_REQUIREMENTS "$CORE_WHEEL"' in workflow
        assert "as-engine@" not in workflow
        assert "--upgrade pip" not in workflow
        assert "hatchling==1.32.0" in workflow
        assert "build==1.6.0" in workflow
        if name in ("test", "drift"):
            assert "pip freeze --all > build-constraints.txt" in workflow
            assert (
                "pip install --no-build-isolation -c build-constraints.txt -e"
                in workflow
            )


def test_build_core_is_exact_and_runtime_floor_matches_verified_core():
    metadata = (ROOT / "pyproject.toml").read_text()
    assert 'requires = ["hatchling==1.32.0", "as-engine==0.1.2"]' in metadata
    dependencies = metadata.split("dependencies = [", 1)[1].split("]", 1)[0]
    assert '"as-engine>=0.1.2,<0.2"' in dependencies


def test_publish_registry_and_installed_wheel_provenance():
    workflow = (WORKFLOWS / "publish.yml").read_text()
    assert "https://pypi.org/project/confluence-as/" in workflow
    assert "confluence-assistant-skills" not in workflow
    assert "pip install --no-deps dist/*.whl" in workflow
    assert 'metadata.version("as-engine") == "0.1.2"' in workflow
    assert "pip freeze --all" in workflow
    assert "sha256sum dist/*.whl dist/*.tar.gz" in workflow
    assert 'get("editable")' in workflow
    build = workflow.split("  publish-pypi:")[0]
    assert "id-token: write" not in build
    publish = workflow.split("  publish-pypi:")[1]
    assert "id-token: write" in publish


def test_drift_ticket_requires_explicit_manual_authority():
    workflow = (WORKFLOWS / "drift.yml").read_text()
    assert re.search(
        r"file_ticket:\s+description:.*\s+type: boolean\s+default: false", workflow
    )
    assert "--dry-run > drift-report.json" in workflow
    ticket = workflow.split("      - name: File drift ticket", 1)[1]
    assert (
        "if: github.event_name == 'workflow_dispatch' && inputs.file_ticket" in ticket
    )
    assert "--file-ticket" in ticket
    assert (
        "secrets.JIRA_API_TOKEN"
        not in workflow.split("      - name: File drift ticket", 1)[0]
    )
