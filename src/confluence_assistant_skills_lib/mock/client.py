"""
Composed Mock Confluence Client

Combines all mixins into a complete mock client for testing.
"""

from .base import MockConfluenceClientBase
from .mixins import ContentMixin, PageMixin, SpaceMixin


class MockConfluenceClient(
    PageMixin, SpaceMixin, ContentMixin, MockConfluenceClientBase
):
    """
    Full mock Confluence client with all API operations.

    Combines:
    - PageMixin: Page CRUD operations
    - SpaceMixin: Space operations
    - ContentMixin: Search, labels, comments, attachments

    Example usage:
        from confluence_assistant_skills_lib.mock import MockConfluenceClient

        client = MockConfluenceClient()

        # Get a page
        page = client.get("/api/v2/pages/100001")

        # Create a page
        new_page = client.post("/api/v2/pages", data={
            "spaceId": "12345",
            "title": "Test Page",
            "body": {"storage": {"value": "<p>Content</p>"}}
        })

        # Search
        results = client.get("/api/v2/search", params={"cql": 'title~"Test"'})
    """

    pass
