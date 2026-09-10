"""Nonrecursive copy of a newly owned leaf within SBX."""

import pytest

pytestmark = [pytest.mark.live, pytest.mark.destructive]


def test_copy_owned_leaf_same_sbx_nonrecursive(live_run, live_page):
    copied = live_run.copy_leaf(live_page, live_run.root)
    assert copied.id not in {live_page.id, live_run.root.id}
    assert copied.parent == live_run.root.token
    assert copied.state == "owned"
