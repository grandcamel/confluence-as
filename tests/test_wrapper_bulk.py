"""Bulk survivors use the shared surface and stateful simulation only."""

from __future__ import annotations

import json

import click
import pytest
import requests
from as_engine.simulation import SimulationStore
from click.testing import CliRunner

from confluence_as.cli.commands import bulk_cmds
from confluence_as.cli.main import cli
from confluence_as.engine import create_surface


@pytest.fixture
def simulated_surface(monkeypatch):
    store = SimulationStore()
    monkeypatch.setenv("CONFLUENCE_ALLOWED_SPACES", "DOCS")
    surface = create_surface(transport="simulation", store=store)
    monkeypatch.setattr(bulk_cmds, "_surface", lambda: surface)
    monkeypatch.setattr(
        requests.Session,
        "send",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("HTTP bypassed Surface")
        ),
    )
    return store, surface


def invoke(*args: str):
    return CliRunner().invoke(cli, ["bulk", *args])


def test_label_dry_run_reads_cql_and_prints_each_write(simulated_surface):
    store, _surface = simulated_surface
    result = invoke(
        "label",
        "add",
        "--cql",
        "space=DOCS AND type=page",
        "--labels",
        "reviewed",
        "--dry-run",
    )
    assert result.exit_code == 0, result.output
    plan = json.loads(result.output)
    assert [target["id"] for target in plan["targets"]] == ["1", "2"]
    assert plan["targets"][0]["intendedOperations"] == ["addLabelsToContent"]
    assert [name for name, _params, _body in store.calls] == ["searchByCQL"]


def test_label_alias_applies_without_interactive_prompt(simulated_surface):
    store, _surface = simulated_surface
    result = invoke("label", "--cql", "space=DOCS AND type=page", "--add", "reviewed")
    assert result.exit_code == 0, result.output
    assert [name for name, _params, _body in store.calls] == [
        "searchByCQL",
        "addLabelsToContent",
        "addLabelsToContent",
    ]
    assert all("reviewed" in page.get("labels", []) for page in store.pages)


@pytest.mark.parametrize(
    "arguments",
    [
        ("--add", "reviewed"),
        ("--remove", "reviewed"),
        ("--cql", "space=DOCS", "--add", "reviewed", "--remove", "old"),
        ("--cql", "space=DOCS"),
    ],
)
def test_label_alias_refuses_missing_or_ambiguous_inputs(monkeypatch, arguments):
    attempts = {"surface": 0, "send": 0}

    def forbidden_surface():
        attempts["surface"] += 1
        raise AssertionError("invalid alias created a surface")

    def forbidden_send(*args, **kwargs):
        attempts["send"] += 1
        raise AssertionError("invalid alias sent a request")

    monkeypatch.setattr(bulk_cmds, "_surface", forbidden_surface)
    monkeypatch.setattr(requests.Session, "send", forbidden_send)
    result = invoke("label", *arguments)
    assert result.exit_code == 2, result.output
    assert "Supply exactly one of --add and --remove with --cql" in result.stderr
    assert attempts == {"surface": 0, "send": 0}


def test_checkpoint_records_failure_and_resume_retries_only_failed(
    simulated_surface, tmp_path
):
    store, surface = simulated_surface
    original = surface.call
    failed = {"value": False}

    def fail_once(name, parameters, body=None, **kwargs):
        if (
            name == "addLabelsToContent"
            and str(parameters["id"]) == "2"
            and not failed["value"]
        ):
            failed["value"] = True
            raise RuntimeError("simulated failure")
        return original(name, parameters, body, **kwargs)

    surface.call = fail_once  # type: ignore[method-assign]
    checkpoint = tmp_path / "bulk.json"
    first = invoke(
        "label",
        "add",
        "--cql",
        "space=DOCS AND type=page",
        "--labels",
        "reviewed",
        "--yes",
        "--checkpoint",
        str(checkpoint),
    )
    assert first.exit_code == 1, first.output
    saved = json.loads(checkpoint.read_text())
    assert saved["done"] == ["1"]
    assert "2" in saved["failures"]
    surface.call = original  # type: ignore[method-assign]
    store.calls.clear()
    resumed = invoke(
        "label",
        "add",
        "--cql",
        "space=DOCS AND type=page",
        "--labels",
        "reviewed",
        "--yes",
        "--checkpoint",
        str(checkpoint),
        "--resume",
    )
    assert resumed.exit_code == 0, resumed.output
    assert [name for name, _params, _body in store.calls] == [
        "searchByCQL",
        "addLabelsToContent",
    ]
    assert json.loads(checkpoint.read_text())["done"] == ["1", "2"]


def test_delete_resume_accepts_disappeared_done_target(monkeypatch, tmp_path):
    monkeypatch.setenv("CONFLUENCE_ALLOWED_SPACES", "DOCS")
    store = SimulationStore()
    surface = create_surface(transport="simulation", store=store)
    monkeypatch.setattr(bulk_cmds, "_surface", lambda: surface)
    original = surface.call
    failed = {"value": False}

    def fail_second_delete(name, parameters, body=None, **kwargs):
        if (
            name == "deletePage"
            and str(parameters["id"]) == "2"
            and not failed["value"]
        ):
            failed["value"] = True
            raise RuntimeError("delete failure")
        return original(name, parameters, body, **kwargs)

    surface.call = fail_second_delete  # type: ignore[method-assign]
    checkpoint = tmp_path / "delete.json"
    first = invoke(
        "delete", "--cql", "type=page", "--yes", "--checkpoint", str(checkpoint)
    )
    assert first.exit_code == 1, first.output
    assert json.loads(checkpoint.read_text())["done"] == ["1"]
    surface.call = original  # type: ignore[method-assign]
    store.calls.clear()
    resumed = invoke(
        "delete",
        "--cql",
        "type=page",
        "--yes",
        "--checkpoint",
        str(checkpoint),
        "--resume",
    )
    assert resumed.exit_code == 0, resumed.output
    deletes = [
        params["id"] for name, params, _body in store.calls if name == "deletePage"
    ]
    assert deletes == [2]
    assert store.pages == []


def test_checkpoint_rejects_malformed_and_changed_unresolved_targets(tmp_path):
    path = tmp_path / "checkpoint.json"
    path.write_text(
        '{"version": 1, "command": "bulk delete", "arguments": {}, "targets": [1], "done": [], "failures": {}}'
    )
    with pytest.raises(click.UsageError, match="Malformed checkpoint"):
        bulk_cmds._checkpoint(path, "bulk delete", {}, ["1"])
    path.write_text(
        '{"version": 1, "command": "bulk delete", "arguments": {}, "targets": ["1", "2"], "done": ["1"], "failures": {}}'
    )
    with pytest.raises(click.UsageError, match="unresolved"):
        bulk_cmds._checkpoint(path, "bulk delete", {}, ["1"])


@pytest.mark.parametrize(
    ("arguments", "seed", "expected"),
    [
        (
            ("label", "add", "--cql", "space=DOCS", "--labels", "reviewed", "--yes"),
            None,
            {"searchByCQL", "addLabelsToContent"},
        ),
        (
            ("label", "remove", "--cql", "space=DOCS", "--labels", "reviewed", "--yes"),
            {
                "pages": [
                    {
                        "id": "1",
                        "spaceId": "55",
                        "title": "First",
                        "labels": ["reviewed"],
                    }
                ]
            },
            {"searchByCQL", "removeLabelFromContent"},
        ),
        (
            ("move", "--cql", "space=DOCS", "--target-parent", "1", "--yes"),
            None,
            {"searchByCQL", "movePage"},
        ),
        (
            ("delete", "--cql", "space=DOCS", "--yes"),
            None,
            {"searchByCQL", "deletePage"},
        ),
        (
            ("permission", "--cql", "space=DOCS", "--add-group", "team", "--yes"),
            None,
            {"searchByCQL", "addGroupToContentRestrictionByGroupId"},
        ),
        (
            ("update", "--cql", "space=DOCS", "--title-prefix", "X ", "--yes"),
            None,
            {"searchByCQL", "getPageById", "updatePage"},
        ),
    ],
)
def test_each_bulk_survivor_uses_the_surface(
    simulated_surface, arguments, seed, expected
):
    store, surface = simulated_surface
    if seed is not None:
        store = SimulationStore(seed)
        surface = create_surface(transport="simulation", store=store)
        bulk_cmds._surface = lambda: surface
    result = invoke(*arguments)
    assert result.exit_code == 0, result.output
    assert expected <= {
        name for name, _params, _body in store.calls if name != "getSpaces"
    }
