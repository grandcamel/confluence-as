"""CSV, report, macro and local-history survivors at the argv/transport seams."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
import requests
from as_engine.simulation import SimulationStore
from click.testing import CliRunner

from confluence_as import engine
from confluence_as.cli.main import cli


@pytest.fixture
def state(monkeypatch, tmp_path):
    monkeypatch.setenv("CONFLUENCE_ALLOWED_SPACES", "DOCS")
    monkeypatch.setenv("CONFLUENCE_ALLOW_SITE_OPERATIONS", "true")
    store = SimulationStore()
    store.pages[0]["labels"] = ["reviewed"]
    store.pages[1]["labels"] = ["reviewed", "other"]
    store.pages[0]["body"] = {
        "storage": {
            "representation": "storage",
            "value": (
                '<p>SBX-1</p><ac:structured-macro ac:name="jira">'
                '<ac:parameter ac:name="jqlQuery">project=SBX</ac:parameter>'
                "</ac:structured-macro>"
            ),
        }
    }
    surface = engine.create_surface(transport="simulation", store=store)
    monkeypatch.setattr(engine, "create_surface", lambda **_: surface)
    monkeypatch.setattr(
        requests.Session,
        "send",
        lambda *_a, **_k: pytest.fail("HTTP bypassed transport"),
    )
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
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
    return store


HTTP_CASES = [
    (["search", "suggest", "--field", "space", "--output", "json"], "getSpaces"),
    (["search", "export", "space=DOCS", "--output", "export.csv"], "searchByCQL"),
    (
        ["search", "stream-export", "space=DOCS", "--output", "stream.csv"],
        "searchByCQL",
    ),
    (["label", "popular", "--space", "DOCS", "--output", "json"], "searchByCQL"),
    (["analytics", "space", "DOCS", "--output", "json"], "searchByCQL"),
    (
        [
            "jira",
            "link",
            "1",
            "SBX-2",
            "--jira-url",
            "https://example.invalid",
            "--output",
            "json",
        ],
        "updatePage",
    ),
    (["jira", "linked", "1", "--output", "json"], "getPageById"),
    (["jira", "embed", "1", "--issues", "SBX-2", "--output", "json"], "updatePage"),
    (
        ["jira", "sync-macro", "1", "--update-jql", "project=SBX", "--output", "json"],
        "updatePage",
    ),
]


@pytest.mark.parametrize(
    "argv,operation", HTTP_CASES, ids=[" ".join(c[0][:2]) for c in HTTP_CASES]
)
def test_survivor_uses_recorded_transport(
    state, tmp_path, monkeypatch, argv, operation
):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, argv)
    assert result.exit_code == 0, result.output
    assert operation in [name for name, _, _ in state.calls]
    if argv[:2] == ["label", "popular"]:
        assert json.loads(result.stdout)["labels"][0] == {
            "name": "reviewed",
            "count": 2,
        }
    if argv[0] == "search" and "export" in argv[1]:
        path = tmp_path / ("stream.csv" if argv[1] == "stream-export" else "export.csv")
        assert "First" in path.read_text() and "Second" in path.read_text()
    if operation == "updatePage":
        writes = [
            (params, body) for name, params, body in state.calls if name == "updatePage"
        ]
        assert writes[0][1]["version"]["number"] == 2
        assert writes[0][1]["body"]["representation"] == "storage"


@pytest.mark.parametrize(
    "args",
    [
        ["list"],
        ["search", "DOCS"],
        ["show", "1"],
        ["clear"],
        ["export", "history.csv"],
        ["cleanup", "--days", "90"],
    ],
)
def test_history_affordance_sends_nothing(state, tmp_path, monkeypatch, args):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli, ["search", "history", *args])
    assert result.exit_code == 0, result.output
    assert state.calls == []


def test_macro_link_duplicate_decision_does_not_write_twice(state):
    argv = [
        "jira",
        "link",
        "1",
        "SBX-2",
        "--jira-url",
        "https://example.invalid",
        "--skip-if-exists",
    ]
    assert CliRunner().invoke(cli, argv).exit_code == 0
    state.calls.clear()
    result = CliRunner().invoke(cli, argv)
    assert result.exit_code == 0, result.output
    assert "updatePage" not in [name for name, _, _ in state.calls]
