"""
Space Operations Mixin

Provides mock implementations for Confluence space operations.
"""

from __future__ import annotations

import re
from typing import Any


class SpaceMixin:
    """Mixin for space-related API operations.

    Add to MockConfluenceClientBase to enable space operation mocking.

    Example:
        class MyMock(SpaceMixin, MockConfluenceClientBase):
            pass

        client = MyMock()
        spaces = client.get("/api/v2/spaces")
    """

    def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        operation: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Handle GET requests for spaces."""
        self._record_request("GET", endpoint, params=params)  # type: ignore[attr-defined]

        # GET /api/v2/spaces/{id}
        match = re.match(r"/api/v2/spaces/(\d+)$", endpoint)
        if match:
            space_id = match.group(1)
            return self._get_space_by_id(space_id)

        # GET /api/v2/spaces (list spaces)
        if endpoint == "/api/v2/spaces":
            return self._list_spaces(params or {})

        # Try parent class
        return super().get(endpoint, params=params, operation=operation, **kwargs)  # type: ignore[misc]

    def _get_space_by_id(self, space_id: str) -> dict[str, Any]:
        """Get space by ID."""
        for space in self.SPACES:  # type: ignore[attr-defined]
            if space["id"] == space_id:
                return space.copy()

        from confluence_assistant_skills_lib.error_handler import NotFoundError

        raise NotFoundError(f"Space {space_id} not found")

    def _list_spaces(self, params: dict[str, Any]) -> dict[str, Any]:
        """List spaces with optional filters."""
        spaces = list(self.SPACES)  # type: ignore[attr-defined]

        # Filter by keys
        keys = params.get("keys")
        if keys:
            if isinstance(keys, str):
                keys = [keys]
            spaces = [s for s in spaces if s["key"] in keys]

        # Filter by type
        space_type = params.get("type")
        if space_type:
            spaces = [s for s in spaces if s.get("type") == space_type]

        # Filter by status
        status = params.get("status", "current")
        if status:
            spaces = [s for s in spaces if s.get("status") == status]

        # Apply limit
        limit = int(params.get("limit", 25))
        cursor = params.get("cursor")

        start = 0
        if cursor:
            try:
                start = int(cursor)
            except ValueError:
                start = 0

        spaces = spaces[start : start + limit]
        next_cursor = str(start + limit) if len(spaces) == limit else None

        return {
            "results": spaces,
            "_links": (
                {"next": f"/api/v2/spaces?cursor={next_cursor}"} if next_cursor else {}
            ),
        }

    def get_space_by_key(self, space_key: str) -> dict[str, Any] | None:
        """Utility method to get space by key."""
        for space in self.SPACES:  # type: ignore[attr-defined]
            if space["key"] == space_key:
                return space.copy()
        return None
