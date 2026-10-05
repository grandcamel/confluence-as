"""One newly owned, rootless current blog lifecycle in verified global SBX."""

import pytest

pytestmark = [pytest.mark.live, pytest.mark.integration, pytest.mark.destructive]


def test_owned_blog_create_read_delete(live_run):
    blog = live_run.create_blog()
    assert blog.kind == "blog" and blog.parent is None and blog.state == "owned"
    assert blog.id != live_run.root.id
    current = live_run.read_blog(blog)
    assert str(current["id"]) == blog.id
    assert current["title"] == blog.name
    assert str(current["spaceId"]) == live_run.space_id
    assert current["status"] == "current"
    assert current["body"]["storage"]["representation"] == "storage"
    assert (
        current["body"]["storage"]["value"] == f"<p>JAS-43 owned blog {blog.name}.</p>"
    )
    live_run.delete_blog(blog)
    assert blog.state == "deleted"
