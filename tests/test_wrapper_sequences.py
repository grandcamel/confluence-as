"""Surviving wrapper verbs use only the stateful Surface transport seam."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests
from as_engine.index import ProductIndexes
from as_engine.simulation import Simulation, SimulationStore
from as_engine.surface import Surface
from click.testing import CliRunner

from confluence_as import engine
from confluence_as.cli.main import cli


@pytest.fixture
def store(monkeypatch):
    result = SimulationStore(
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
    indexes = ProductIndexes(Path(engine.__file__).parent / "_generated")
    surface = Surface(
        indexes,
        lambda _document, _index: Simulation(result),
        scope_allowlist=("DOCS",),
        scope_allow_site=True,
        scope_resolution_rules={
            "v2:getPageById": (("id",),),
            "v2:getSpaceById": (("id",),),
            "v2:getSpaces": (("ids",), ("keys",)),
        },
    )
    monkeypatch.setenv("CONFLUENCE_ALLOWED_SPACES", "DOCS")
    monkeypatch.setenv("CONFLUENCE_ALLOW_SITE_OPERATIONS", "true")
    monkeypatch.setattr(engine, "create_surface", lambda: surface)
    monkeypatch.setattr(
        requests.Session,
        "send",
        lambda *_args, **_kwargs: pytest.fail("HTTP bypassed transport"),
    )
    result.pages[0]["body"] = {"representation": "storage", "value": "<p>source</p>"}
    result.pages[1]["body"] = {"representation": "storage", "value": "<p>child</p>"}
    return result


def test_tree_and_reorder_only_read_through_surface(store):
    runner = CliRunner()
    tree = runner.invoke(cli, ["hierarchy", "tree", "1", "--output", "json"])
    assert (
        tree.exit_code == 0 and json.loads(tree.output)["tree"][0]["title"] == "Second"
    )
    before = len(store.calls)
    reorder = runner.invoke(cli, ["hierarchy", "reorder", "1", "--output", "json"])
    assert (
        reorder.exit_code == 0
        and json.loads(reorder.output)["newOrder"][0]["id"] == "2"
    )
    assert {name for name, _, _ in store.calls[before:]} <= {
        "getPageById",
        "getSpaces",
        "getChildPages",
    }


def test_copy_children_and_property_update_use_explicit_surface_operations(store):
    runner = CliRunner()
    copied = runner.invoke(
        cli, ["page", "copy", "1", "--include-children", "--output", "json"]
    )
    assert copied.exit_code == 0, copied.output
    copied_pages = store.pages[2:]
    assert [page["title"] for page in copied_pages] == ["Copy of First", "Second"]
    assert [page["body"]["value"] for page in copied_pages] == [
        "<p>source</p>",
        "<p>child</p>",
    ]
    updated = runner.invoke(
        cli, ["property", "set", "1", "review", "--value", "true", "--output", "json"]
    )
    assert updated.exit_code == 0, updated.output
    assert json.loads(updated.output)["property"]["value"] is True
    again = runner.invoke(
        cli, ["property", "set", "1", "review", "--value", "false", "--output", "json"]
    )
    assert again.exit_code == 0, again.output
    names = [name for name, _, _ in store.calls]
    assert "createPage" in names and "getPageContentProperties" in names
    assert "createPageProperty" in names and "updatePagePropertyById" in names


def test_template_creation_copies_raw_storage_and_adds_v1_labels(store, tmp_path):
    runner = CliRunner()
    listed = runner.invoke(cli, ["template", "list", "--output", "json"])
    assert listed.exit_code == 0, listed.output
    assert json.loads(listed.output)["count"] == 1
    created = runner.invoke(
        cli,
        [
            "template",
            "create-from",
            "--template",
            "tpl-1",
            "--space",
            "DOCS",
            "--title",
            "From template",
            "--labels",
            "ready",
            "--output",
            "json",
        ],
    )
    assert created.exit_code == 0, created.output
    assert json.loads(created.output)["page"]["title"] == "From template"
    page = next(page for page in store.pages if page["title"] == "From template")
    assert page["body"] == {"representation": "storage", "value": "<p>Template</p>"}
    assert page["labels"] == ["ready"]
    assert [name for name, _, _ in store.calls][-4:] == [
        "getContentTemplate",
        "getSpaces",
        "createPage",
        "addLabelsToContent",
    ]
    source = tmp_path / "custom.md"
    source.write_text("# Custom", encoding="utf-8")
    custom = runner.invoke(
        cli,
        [
            "template",
            "create-from",
            "--template",
            "tpl-1",
            "--space",
            "DOCS",
            "--title",
            "Custom",
            "--file",
            str(source),
            "--output",
            "json",
        ],
    )
    assert custom.exit_code == 0, custom.output
    assert (
        next(page for page in store.pages if page["title"] == "Custom")["body"]["value"]
        == "<h1>Custom</h1>"
    )


def test_copy_refuses_target_inside_source_hierarchy(store):
    result = CliRunner().invoke(
        cli, ["page", "copy", "1", "--parent", "2", "--output", "json"]
    )
    assert result.exit_code != 0
    assert not any(name == "createPage" for name, _, _ in store.calls)


def test_copy_with_children_refuses_a_cyclic_source_before_writing(store):
    store.pages[0]["parentId"] = "2"
    result = CliRunner().invoke(
        cli, ["page", "copy", "1", "--include-children", "--output", "json"]
    )
    assert result.exit_code != 0
    assert not any(name == "createPage" for name, _, _ in store.calls)


def test_template_blueprint_refuses_without_creating_a_blank_page(store):
    result = CliRunner().invoke(
        cli,
        [
            "template",
            "create-from",
            "--blueprint",
            "bp-1",
            "--space",
            "DOCS",
            "--title",
            "Nope",
        ],
    )
    assert result.exit_code == 2
    assert not any(name == "createPage" for name, _, _ in store.calls)
