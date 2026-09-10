"""Three caller-visible property contracts on run-owned pages and keys."""

import pytest

pytestmark = [pytest.mark.live, pytest.mark.destructive]


def test_indexed_property_create_read_delete(live_run, live_page):
    value = {"text": "JAS43", "count": 3, "items": ["one", "two"]}
    prop = live_run.create_property(live_page, value)
    result = live_run.read_property(prop)
    assert str(result["id"]) == prop.id
    assert result["key"] == prop.name
    assert result["value"] == value
    live_run.delete_property(prop)
    assert not any(str(row["id"]) == prop.id for row in live_run.properties(live_page))


def test_indexed_property_versioned_update(live_run, live_page):
    prop = live_run.create_property(live_page, {"revision": 1})
    version = live_run.read_property(prop)["version"]["number"]
    result = live_run.update_property(prop, {"revision": 2, "enabled": True})
    assert result["value"] == {"revision": 2, "enabled": True}
    assert result["version"]["number"] == version + 1
    assert str(result["id"]) == prop.id


def test_property_set_wrapper_create_and_upsert(live_run, live_page):
    prop = live_run.create_property(live_page, {"wrapper": "create"}, wrapper=True)
    version = live_run.read_property(prop)["version"]["number"]
    result = live_run.update_property(prop, {"wrapper": "upsert"}, wrapper=True)
    assert str(result["id"]) == prop.id
    assert result["key"] == prop.name
    assert result["value"] == {"wrapper": "upsert"}
    assert result["version"]["number"] == version + 1
