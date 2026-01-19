"""
Mock Confluence Client Base

Provides the base mock client with seed data and HTTP method stubs.
This class is designed to be extended with mixins for specific API areas.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Any


def is_mock_mode() -> bool:
    """Check if Confluence mock mode is enabled.

    Returns:
        True if CONFLUENCE_MOCK_MODE environment variable is set to 'true'.
    """
    return os.environ.get("CONFLUENCE_MOCK_MODE", "").lower() == "true"


class MockConfluenceClientBase:
    """
    Base class for mock Confluence clients.

    Provides:
    - Seed data for spaces, pages, users
    - HTTP method stubs (get, post, put, delete)
    - Utility methods for generating responses
    """

    # Seed data
    SPACES = [
        {
            "id": "12345",
            "key": "TEST",
            "name": "Test Space",
            "type": "global",
            "status": "current",
            "homepageId": "100001",
            "_links": {"webui": "/spaces/TEST"},
        },
        {
            "id": "12346",
            "key": "DEV",
            "name": "Development",
            "type": "global",
            "status": "current",
            "homepageId": "100002",
            "_links": {"webui": "/spaces/DEV"},
        },
        {
            "id": "12347",
            "key": "DOCS",
            "name": "Documentation",
            "type": "global",
            "status": "current",
            "homepageId": "100003",
            "_links": {"webui": "/spaces/DOCS"},
        },
    ]

    USERS = [
        {
            "accountId": "user-001",
            "email": "admin@example.com",
            "displayName": "Admin User",
            "type": "known",
            "accountType": "atlassian",
            "profilePicture": {"path": "/avatar/admin.png"},
        },
        {
            "accountId": "user-002",
            "email": "developer@example.com",
            "displayName": "Developer",
            "type": "known",
            "accountType": "atlassian",
            "profilePicture": {"path": "/avatar/dev.png"},
        },
    ]

    def __init__(
        self,
        base_url: str = "https://mock.atlassian.net",
        email: str = "mock@example.com",
        api_token: str = "mock-token",
        **kwargs: Any,
    ):
        """Initialize mock client with optional configuration."""
        self.base_url = base_url
        self.email = email
        self.api_token = api_token

        # Storage for dynamic data
        self._pages: dict[str, dict[str, Any]] = {}
        self._comments: dict[str, list[dict[str, Any]]] = {}
        self._labels: dict[str, list[dict[str, Any]]] = {}
        self._attachments: dict[str, list[dict[str, Any]]] = {}

        # Request tracking for assertions
        self._requests: list[dict[str, Any]] = []

        # Initialize with seed data
        self._init_seed_data()

    def _init_seed_data(self) -> None:
        """Initialize pages and other seed data."""
        # Create home pages for each space
        for space in self.SPACES:
            home_id = str(space["homepageId"])
            self._pages[home_id] = {
                "id": home_id,
                "type": "page",
                "status": "current",
                "title": f"{space['name']} Home",
                "spaceId": space["id"],
                "parentId": None,
                "parentType": None,
                "position": 0,
                "authorId": "user-001",
                "ownerId": "user-001",
                "createdAt": "2024-01-01T00:00:00.000Z",
                "version": {
                    "number": 1,
                    "message": "Initial version",
                    "createdAt": "2024-01-01T00:00:00.000Z",
                    "authorId": "user-001",
                },
                "body": {
                    "storage": {
                        "value": f"<p>Welcome to {space['name']}</p>",
                        "representation": "storage",
                    }
                },
                "_links": {
                    "webui": f"/spaces/{space['key']}/pages/{home_id}",
                    "tinyui": f"/x/{home_id}",
                },
            }

    def _generate_id(self) -> str:
        """Generate a unique ID for new resources."""
        return str(uuid.uuid4().int)[:10]

    def _now_iso(self) -> str:
        """Return current timestamp in ISO format."""
        return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")

    def _record_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Record a request for test assertions."""
        self._requests.append(
            {
                "method": method,
                "endpoint": endpoint,
                "params": params,
                "data": data,
                "timestamp": self._now_iso(),
            }
        )

    def get_recorded_requests(self) -> list[dict[str, Any]]:
        """Return all recorded requests."""
        return self._requests.copy()

    def clear_recorded_requests(self) -> None:
        """Clear recorded requests."""
        self._requests.clear()

    # HTTP method stubs - to be overridden by mixins
    def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        operation: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """GET request stub - override in mixins."""
        self._record_request("GET", endpoint, params=params)
        raise NotImplementedError(f"GET {endpoint} not implemented in mock")

    def post(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
        operation: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """POST request stub - override in mixins."""
        self._record_request("POST", endpoint, data=data)
        raise NotImplementedError(f"POST {endpoint} not implemented in mock")

    def put(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
        operation: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """PUT request stub - override in mixins."""
        self._record_request("PUT", endpoint, data=data)
        raise NotImplementedError(f"PUT {endpoint} not implemented in mock")

    def delete(
        self,
        endpoint: str,
        operation: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """DELETE request stub - override in mixins."""
        self._record_request("DELETE", endpoint)
        raise NotImplementedError(f"DELETE {endpoint} not implemented in mock")

    def test_connection(self) -> dict[str, Any]:
        """Test connection - return mock current user."""
        return {
            "accountId": "user-001",
            "email": "admin@example.com",
            "displayName": "Admin User",
            "type": "known",
        }

    # Utility methods for tests
    def add_page(self, page_data: dict[str, Any]) -> str:
        """Add a page to the mock data. Returns page ID."""
        page_id = page_data.get("id") or self._generate_id()
        page_data["id"] = page_id
        self._pages[page_id] = page_data
        return page_id

    def get_page_data(self, page_id: str) -> dict[str, Any] | None:
        """Get raw page data for assertions."""
        return self._pages.get(page_id)

    def add_space(self, space_data: dict[str, Any]) -> None:
        """Add a space to the mock data."""
        self.SPACES.append(space_data)

    def reset(self) -> None:
        """Reset all mock data to initial state."""
        self._pages.clear()
        self._comments.clear()
        self._labels.clear()
        self._attachments.clear()
        self._requests.clear()
        self._init_seed_data()
