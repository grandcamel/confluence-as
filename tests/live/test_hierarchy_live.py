"""Exact tree of three newly owned pages, bounded at depth two."""

import pytest

pytestmark = [pytest.mark.live, pytest.mark.destructive]


def test_tree_matches_owned_root_child_grandchild(live_run, live_page):
    child = live_run.create_page("tree-child", parent=live_page)
    grandchild = live_run.create_page("tree-grandchild", parent=child)
    result = live_run.tree_matches(live_page, child, grandchild)
    assert result["stats"] == {"totalPages": 2, "maxDepth": 2, "rootChildren": 1}
