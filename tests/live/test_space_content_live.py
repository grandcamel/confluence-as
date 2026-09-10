"""SBX listing filtered to two exact owned current page IDs."""

import pytest

pytestmark = [pytest.mark.live, pytest.mark.destructive]


def test_space_listing_matches_exact_owned_ids(live_run, live_page):
    second = live_run.create_page("listed", parent=live_run.root)
    result = live_run.pages_match((live_page, second))
    assert {str(row["id"]) for row in result} == {live_page.id, second.id}
