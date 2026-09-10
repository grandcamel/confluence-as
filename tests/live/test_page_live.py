"""Six caller-visible page contracts on this run's own SBX resources."""

import pytest

pytestmark = [pytest.mark.live, pytest.mark.destructive]


def test_create_read_page(live_run, live_page):
    page = live_run.read_page(live_page)
    assert page["id"] == live_page.id
    assert page["title"] == live_page.name
    assert str(page["spaceId"]) == live_run.space_id
    assert page["status"] == "current"


def test_create_child_page(live_run, live_page):
    child = live_run.create_page("child", parent=live_page)
    page = live_run.read_page(child)
    assert str(page["parentId"]) == live_page.id
    assert page["id"] != live_page.id
    assert str(page["spaceId"]) == live_run.space_id


def test_update_page_title(live_run, live_page):
    title = live_run.name("renamed")
    result = live_run.update_page(live_page, title=title)
    assert result["title"] == title
    assert live_run.read_page(live_page)["title"] == title


def test_markdown_storage_roundtrip(live_run):
    page = live_run.create_page(
        "markdown", parent=live_run.root, body="**JAS43 bold** and plain text."
    )
    storage = live_run.read_page(page)["body"]["storage"]["value"]
    assert "<strong>JAS43 bold</strong>" in storage
    assert "plain text" in storage
    result = live_run.update_page(page, body="Updated **JAS43 body**.")
    assert "<strong>JAS43 body</strong>" in result["body"]["storage"]["value"]


def test_page_version_increment(live_run, live_page):
    before = live_run.read_page(live_page)["version"]["number"]
    updated = live_run.update_page(live_page, title=live_run.name("version"))
    assert updated["version"]["number"] == before + 1


def test_delete_page_observed_in_filtered_list(live_run, live_page):
    assert [str(row["id"]) for row in live_run.list_owned_page(live_page)] == [
        live_page.id
    ]
    live_run.delete_page(live_page)
    assert live_page.state == "deleted"
    assert live_run.list_owned_page(live_page) == []
