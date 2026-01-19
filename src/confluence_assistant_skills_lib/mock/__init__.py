"""
Mock Confluence Client Module

Provides mixin-based mock clients for testing Confluence skills without
a live Confluence instance. Uses a composable mixin architecture to
allow selective testing of different API areas.

Example usage:
    from confluence_assistant_skills_lib.mock import MockConfluenceClient

    # Full mock client with all mixins
    client = MockConfluenceClient()

    # Get a page
    page = client.get("/api/v2/pages/100001")

    # Create a page
    new_page = client.post("/api/v2/pages", data={
        "spaceId": "12345",
        "title": "Test Page",
        "body": {"storage": {"value": "<p>Content</p>"}}
    })

Custom mock with specific mixins:
    from confluence_assistant_skills_lib.mock.base import MockConfluenceClientBase
    from confluence_assistant_skills_lib.mock.mixins import PageMixin, SpaceMixin

    class CustomMock(PageMixin, SpaceMixin, MockConfluenceClientBase):
        pass

    client = CustomMock()
"""

from .base import MockConfluenceClientBase, is_mock_mode
from .client import MockConfluenceClient
from .mixins import ContentMixin, PageMixin, SpaceMixin

__all__ = [
    "MockConfluenceClient",
    "MockConfluenceClientBase",
    "is_mock_mode",
    "PageMixin",
    "SpaceMixin",
    "ContentMixin",
]
