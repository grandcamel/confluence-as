"""Complete exact version listing after two owned-page updates."""

import pytest

pytestmark = [pytest.mark.live, pytest.mark.destructive]


def test_versions_match_owned_page_updates(live_run, live_page):
    versions = [live_run.read_page(live_page)["version"]["number"]]
    for purpose in ("version-two", "version-three"):
        updated = live_run.update_page(live_page, title=live_run.name(purpose))
        versions.append(updated["version"]["number"])
    result = live_run.versions_match(live_page, versions)
    assert {row["number"] for row in result} == set(versions)
