"""
Page Operations Mixin

Provides mock implementations for Confluence page CRUD operations.
"""

from __future__ import annotations

import re
from typing import Any


class PageMixin:
    """Mixin for page-related API operations.

    Add to MockConfluenceClientBase to enable page operation mocking.

    Example:
        class MyMock(PageMixin, MockConfluenceClientBase):
            pass

        client = MyMock()
        page = client.get("/api/v2/pages/100001")
    """

    def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        operation: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Handle GET requests for pages."""
        self._record_request("GET", endpoint, params=params)  # type: ignore[attr-defined]

        # GET /api/v2/pages/{id}
        match = re.match(r"/api/v2/pages/(\d+)$", endpoint)
        if match:
            page_id = match.group(1)
            page = self._pages.get(page_id)  # type: ignore[attr-defined]
            if page:
                return page.copy()
            from confluence_assistant_skills_lib.error_handler import NotFoundError

            raise NotFoundError(f"Page {page_id} not found")

        # GET /api/v2/pages (list pages)
        if endpoint == "/api/v2/pages":
            return self._list_pages(params or {})

        # GET /api/v2/pages/{id}/children
        match = re.match(r"/api/v2/pages/(\d+)/children", endpoint)
        if match:
            parent_id = match.group(1)
            return self._get_children(parent_id, params or {})

        # GET /api/v2/pages/{id}/versions
        match = re.match(r"/api/v2/pages/(\d+)/versions", endpoint)
        if match:
            page_id = match.group(1)
            return self._get_versions(page_id)

        # Try parent class
        return super().get(endpoint, params=params, operation=operation, **kwargs)  # type: ignore[misc]

    def post(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
        operation: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Handle POST requests for pages."""
        self._record_request("POST", endpoint, data=data)  # type: ignore[attr-defined]

        # POST /api/v2/pages (create page)
        if endpoint == "/api/v2/pages":
            return self._create_page(data or {})

        # Try parent class
        return super().post(endpoint, data=data, operation=operation, **kwargs)  # type: ignore[misc]

    def put(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
        operation: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Handle PUT requests for pages."""
        self._record_request("PUT", endpoint, data=data)  # type: ignore[attr-defined]

        # PUT /api/v2/pages/{id}
        match = re.match(r"/api/v2/pages/(\d+)$", endpoint)
        if match:
            page_id = match.group(1)
            return self._update_page(page_id, data or {})

        # Try parent class
        return super().put(endpoint, data=data, operation=operation, **kwargs)  # type: ignore[misc]

    def delete(
        self,
        endpoint: str,
        operation: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Handle DELETE requests for pages."""
        self._record_request("DELETE", endpoint)  # type: ignore[attr-defined]

        # DELETE /api/v2/pages/{id}
        match = re.match(r"/api/v2/pages/(\d+)$", endpoint)
        if match:
            page_id = match.group(1)
            return self._delete_page(page_id)

        # Try parent class
        return super().delete(endpoint, operation=operation, **kwargs)  # type: ignore[misc]

    def _list_pages(self, params: dict[str, Any]) -> dict[str, Any]:
        """List pages with optional filters."""
        pages = list(self._pages.values())  # type: ignore[attr-defined]

        # Filter by space
        space_id = params.get("space-id")
        if space_id:
            pages = [p for p in pages if p.get("spaceId") == space_id]

        # Filter by status
        status = params.get("status", "current")
        if status:
            pages = [p for p in pages if p.get("status") == status]

        # Apply limit
        limit = int(params.get("limit", 25))
        cursor = params.get("cursor")

        # Simple cursor-based pagination
        start = 0
        if cursor:
            try:
                start = int(cursor)
            except ValueError:
                start = 0

        pages = pages[start : start + limit]
        next_cursor = str(start + limit) if len(pages) == limit else None

        return {
            "results": pages,
            "_links": (
                {"next": f"/api/v2/pages?cursor={next_cursor}"} if next_cursor else {}
            ),
        }

    def _get_children(self, parent_id: str, params: dict[str, Any]) -> dict[str, Any]:
        """Get child pages."""
        children = [
            p
            for p in self._pages.values()  # type: ignore[attr-defined]
            if p.get("parentId") == parent_id
        ]
        return {"results": children, "_links": {}}

    def _get_versions(self, page_id: str) -> dict[str, Any]:
        """Get page versions."""
        page = self._pages.get(page_id)  # type: ignore[attr-defined]
        if not page:
            from confluence_assistant_skills_lib.error_handler import NotFoundError

            raise NotFoundError(f"Page {page_id} not found")

        version = page.get("version", {"number": 1})
        return {
            "results": [
                {
                    "number": version.get("number", 1),
                    "message": version.get("message", ""),
                    "createdAt": version.get("createdAt", self._now_iso()),  # type: ignore[attr-defined]
                    "authorId": version.get("authorId", "user-001"),
                }
            ],
            "_links": {},
        }

    def _create_page(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new page."""
        page_id = self._generate_id()  # type: ignore[attr-defined]
        space_id = data.get("spaceId")

        # Find space key
        space_key = None
        for space in self.SPACES:  # type: ignore[attr-defined]
            if space["id"] == space_id:
                space_key = space["key"]
                break

        page = {
            "id": page_id,
            "type": "page",
            "status": data.get("status", "current"),
            "title": data.get("title", "Untitled"),
            "spaceId": space_id,
            "parentId": data.get("parentId"),
            "parentType": data.get("parentType"),
            "position": 0,
            "authorId": "user-001",
            "ownerId": "user-001",
            "createdAt": self._now_iso(),  # type: ignore[attr-defined]
            "version": {
                "number": 1,
                "message": "Created",
                "createdAt": self._now_iso(),  # type: ignore[attr-defined]
                "authorId": "user-001",
            },
            "body": data.get("body", {}),
            "_links": {
                "webui": (
                    f"/spaces/{space_key}/pages/{page_id}"
                    if space_key
                    else f"/pages/{page_id}"
                ),
                "tinyui": f"/x/{page_id}",
            },
        }

        self._pages[page_id] = page  # type: ignore[attr-defined]
        return page

    def _update_page(self, page_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing page."""
        page = self._pages.get(page_id)  # type: ignore[attr-defined]
        if not page:
            from confluence_assistant_skills_lib.error_handler import NotFoundError

            raise NotFoundError(f"Page {page_id} not found")

        # Update fields
        if "title" in data:
            page["title"] = data["title"]
        if "body" in data:
            page["body"] = data["body"]
        if "status" in data:
            page["status"] = data["status"]

        # Increment version
        current_version = page.get("version", {}).get("number", 1)
        page["version"] = {
            "number": current_version + 1,
            "message": data.get("version", {}).get("message", "Updated"),
            "createdAt": self._now_iso(),  # type: ignore[attr-defined]
            "authorId": "user-001",
        }

        return page

    def _delete_page(self, page_id: str) -> None:
        """Delete a page."""
        if page_id not in self._pages:  # type: ignore[attr-defined]
            from confluence_assistant_skills_lib.error_handler import NotFoundError

            raise NotFoundError(f"Page {page_id} not found")

        del self._pages[page_id]  # type: ignore[attr-defined]
        # Also delete comments, labels, attachments
        self._comments.pop(page_id, None)  # type: ignore[attr-defined]
        self._labels.pop(page_id, None)  # type: ignore[attr-defined]
        self._attachments.pop(page_id, None)  # type: ignore[attr-defined]
