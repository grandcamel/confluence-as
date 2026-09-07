"""Every retained verb executes with legacy HTTP disabled and one shared seam."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
import requests
from as_engine.simulation import SimulationStore
from click.testing import CliRunner

from confluence_as import engine
from confluence_as.cli import cli_utils
from confluence_as.cli.commands import admin_cmds, bulk_cmds, ops_cmds, permission_cmds
from confluence_as.cli.main import cli

CASES = {
    "admin permissions check": ["--space", "DOCS"],
    "analytics space": ["DOCS"],
    "attachment download": ["att1", "--output", "attachment.bin"],
    "bulk label add": ["--cql", "space=DOCS", "--labels", "reviewed"],
    "bulk label remove": ["--cql", "space=DOCS", "--labels", "reviewed"],
    "bulk move": ["--cql", "space=DOCS", "--target-parent", "1"],
    "bulk delete": ["--cql", "space=DOCS"],
    "bulk permission": ["--cql", "space=DOCS", "--add-group", "team"],
    "bulk update": ["--cql", "space=DOCS", "--title-prefix", "X "],
    "hierarchy tree": ["1"],
    "hierarchy reorder": ["1"],
    "jira link": ["1", "SBX-2", "--jira-url", "https://example.invalid"],
    "jira linked": ["1"],
    "jira embed": ["1", "--issues", "SBX-2"],
    "jira sync-macro": ["1", "--update-jql", "project=SBX"],
    "label popular": ["--space", "DOCS"],
    "ops cache-warm": ["--spaces"],
    "ops cache-status": [],
    "ops cache-clear": ["--force"],
    "ops health-check": [],
    "ops rate-limit-status": [],
    "ops api-diagnostics": [],
    "page copy": ["1", "--include-children"],
    "permission page remove": ["1", "--all", "--operation", "read"],
    "permission space remove": ["DOCS", "--permission-id", "1"],
    "property set": ["1", "reviewed", "--value", "true"],
    "search suggest": ["--field", "space"],
    "search export": ["space=DOCS", "--output", "export.csv"],
    "search stream-export": ["space=DOCS", "--output", "stream.csv"],
    "search history list": [],
    "search history search": ["DOCS"],
    "search history show": ["1"],
    "search history clear": [],
    "search history export": ["history.csv"],
    "search history cleanup": ["--days", "90"],
    "template list": [],
    "template create-from": [
        "--template",
        "tpl-1",
        "--space",
        "DOCS",
        "--title",
        "From template",
    ],
}
LOCAL = {"ops cache-status", "ops cache-clear"} | {
    verb for verb in CASES if verb.startswith("search history ")
}


def test_seam_covers_exactly_every_reviewed_survivor():
    rows = json.loads((Path(__file__).parent / "wrapper_verbs.json").read_text())
    assert len(CASES) == 37
    assert set(CASES) == {row["verb"] for row in rows if row["decision"] == "survivor"}


@pytest.mark.parametrize("verb", CASES)
def test_every_survivor_at_argv_transport_seam(verb, monkeypatch, tmp_path):
    monkeypatch.setenv("CONFLUENCE_ALLOWED_SPACES", "DOCS")
    monkeypatch.setenv("CONFLUENCE_ALLOW_SITE_OPERATIONS", "true")
    monkeypatch.setenv("CONFLUENCE_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.chdir(tmp_path)
    history = tmp_path / ".cache/confluence-assistant-skills/cql_history.json"
    history.parent.mkdir(parents=True)
    history.write_text(
        json.dumps(
            [
                {
                    "query": "space=DOCS",
                    "result_count": 2,
                    "timestamp": datetime.now().isoformat(),
                }
            ]
        )
    )
    store = SimulationStore(
        {
            "templates": [
                {
                    "id": "tpl-1",
                    "name": "Starter",
                    "templateType": "page",
                    "body": {"storage": {"value": "<p>Template</p>"}},
                }
            ]
        }
    )
    store.space_permissions["55"] = [
        {
            "id": "1",
            "operation": {"key": "read", "targetType": "space"},
            "principal": {"type": "user", "id": "sim-user"},
        }
    ]
    for page in store.pages:
        page["labels"] = ["reviewed"]
        page["body"] = {
            "storage": {
                "representation": "storage",
                "value": '<ac:structured-macro ac:name="jira"><ac:parameter ac:name="jqlQuery">project=SBX</ac:parameter></ac:structured-macro>',
            }
        }
    surface = engine.create_surface(transport="simulation", store=store)
    monkeypatch.setattr(engine, "create_surface", lambda **_: surface)
    monkeypatch.setattr(ops_cmds, "create_surface", lambda **_: surface)
    monkeypatch.setattr(bulk_cmds, "_surface", lambda: surface)
    monkeypatch.setattr(admin_cmds, "_surface", lambda: surface)
    monkeypatch.setattr(permission_cmds, "_surface", lambda: surface)

    def forbidden(*_a, **_k):
        pytest.fail("survivor bypassed Surface transport or acquired legacy client")

    monkeypatch.setattr(requests.Session, "send", forbidden)
    monkeypatch.setattr(cli_utils, "get_confluence_client", forbidden)
    import confluence_as

    monkeypatch.setattr(confluence_as, "get_confluence_client", forbidden)
    result = CliRunner().invoke(
        cli,
        [*verb.split(), *CASES[verb], *(["--yes"] if verb.startswith("bulk ") else [])],
    )
    assert result.exit_code == 0, (verb, result.output, result.exception)
    if verb in LOCAL:
        assert store.calls == []
    else:
        assert store.calls, verb
