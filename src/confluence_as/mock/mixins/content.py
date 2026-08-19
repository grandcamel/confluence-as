"""
Content Operations Mixin

Provides mock implementations for Confluence search and content operations.
"""

from __future__ import annotations

import re
from typing import Any


class ContentMixin:
    """Mixin for content search and miscellaneous operations.

    Add to MockConfluenceClientBase to enable content operation mocking.

    Example:
        class MyMock(ContentMixin, MockConfluenceClientBase):
            pass

        client = MyMock()
        results = client.get("/api/v2/search", params={"cql": 'title~"Test"'})
    """

    def get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        operation: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Handle GET requests for content operations."""
        self._record_request("GET", endpoint, params=params)  # type: ignore[attr-defined]

        # GET /api/v2/users/current
        if endpoint == "/api/v2/users/current":
            return self.USERS[0].copy()  # type: ignore[attr-defined]

        # GET /wiki/api/v2/users/current
        if endpoint == "/wiki/api/v2/users/current":
            return self.USERS[0].copy()  # type: ignore[attr-defined]

        # GET /api/v2/search (CQL search)
        if endpoint == "/api/v2/search":
            return self._search(params or {})

        # GET /wiki/rest/api/search (legacy search)
        if endpoint == "/wiki/rest/api/search":
            return self._search_legacy(params or {})

        # GET /api/v2/pages/{id}/labels
        match = re.match(r"/api/v2/pages/(\d+)/labels", endpoint)
        if match:
            page_id = match.group(1)
            return self._get_labels(page_id)

        # GET /api/v2/pages/{id}/footer-comments
        match = re.match(r"/api/v2/pages/(\d+)/footer-comments", endpoint)
        if match:
            page_id = match.group(1)
            return self._get_comments(page_id)

        # GET /api/v2/pages/{id}/attachments
        match = re.match(r"/api/v2/pages/(\d+)/attachments", endpoint)
        if match:
            page_id = match.group(1)
            return self._get_attachments(page_id)

        # GET /api/v2/pages/{id}/properties
        match = re.match(r"/api/v2/pages/(\d+)/properties$", endpoint)
        if match:
            page_id = match.group(1)
            return self._get_properties(page_id)

        # Try parent class
        return super().get(endpoint, params=params, operation=operation, **kwargs)  # type: ignore[misc]

    def post(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
        operation: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Handle POST requests for content operations."""
        # The real client accepts the payload as json_data=; honor both.
        json_payload = kwargs.pop("json_data", None)
        if json_payload is not None:
            data = json_payload
        self._record_request("POST", endpoint, data=data)  # type: ignore[attr-defined]

        # POST /api/v2/pages/{id}/labels
        match = re.match(r"/api/v2/pages/(\d+)/labels", endpoint)
        if match:
            page_id = match.group(1)
            return self._add_label(page_id, data or {})

        # POST /api/v2/pages/{id}/footer-comments
        match = re.match(r"/api/v2/pages/(\d+)/footer-comments", endpoint)
        if match:
            page_id = match.group(1)
            return self._add_comment(page_id, data or {})

        # POST /api/v2/pages/{id}/properties
        match = re.match(r"/api/v2/pages/(\d+)/properties$", endpoint)
        if match:
            page_id = match.group(1)
            return self._create_property(page_id, data or {})

        # Try parent class
        return super().post(endpoint, data=data, operation=operation, **kwargs)  # type: ignore[misc]

    def put(
        self,
        endpoint: str,
        data: dict[str, Any] | None = None,
        operation: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Handle PUT requests for content operations."""
        json_payload = kwargs.pop("json_data", None)
        if json_payload is not None:
            data = json_payload
        self._record_request("PUT", endpoint, data=data)  # type: ignore[attr-defined]

        # PUT /api/v2/pages/{id}/properties/{property_id}
        match = re.match(r"/api/v2/pages/(\d+)/properties/(\d+)", endpoint)
        if match:
            page_id = match.group(1)
            property_id = match.group(2)
            return self._update_property(page_id, property_id, data or {})

        # Try parent class
        return super().put(endpoint, data=data, operation=operation, **kwargs)  # type: ignore[misc]

    def delete(
        self,
        endpoint: str,
        operation: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Handle DELETE requests for content operations."""
        self._record_request("DELETE", endpoint)  # type: ignore[attr-defined]

        # DELETE /api/v2/pages/{id}/labels/{label}
        match = re.match(r"/api/v2/pages/(\d+)/labels/(.+)", endpoint)
        if match:
            page_id = match.group(1)
            label = match.group(2)
            return self._remove_label(page_id, label)

        # DELETE /api/v2/footer-comments/{id}
        match = re.match(r"/api/v2/footer-comments/(\d+)", endpoint)
        if match:
            comment_id = match.group(1)
            return self._delete_comment(comment_id)

        # DELETE /api/v2/pages/{id}/properties/{property_id}
        match = re.match(r"/api/v2/pages/(\d+)/properties/(\d+)", endpoint)
        if match:
            page_id = match.group(1)
            property_id = match.group(2)
            return self._delete_property(page_id, property_id)

        # Try parent class
        return super().delete(endpoint, operation=operation, **kwargs)  # type: ignore[misc]

    def _search(self, params: dict[str, Any]) -> dict[str, Any]:
        """Search content using CQL."""
        cql = params.get("cql", "")
        limit = int(params.get("limit", 25))

        # Simple title search
        results = []
        for page in self._pages.values():  # type: ignore[attr-defined]
            title = page.get("title", "").lower()
            # Basic CQL parsing for title contains
            if "title~" in cql.lower():
                match = re.search(r'title~"([^"]+)"', cql, re.IGNORECASE)
                if match:
                    search_term = match.group(1).lower()
                    if search_term in title:
                        results.append(
                            {
                                "content": page,
                                "title": page.get("title"),
                                "excerpt": "",
                                "url": page.get("_links", {}).get("webui", ""),
                            }
                        )
            elif "text~" in cql.lower():
                # Search in body
                match = re.search(r'text~"([^"]+)"', cql, re.IGNORECASE)
                if match:
                    search_term = match.group(1).lower()
                    body = str(
                        page.get("body", {}).get("storage", {}).get("value", "")
                    ).lower()
                    if search_term in body or search_term in title:
                        results.append(
                            {
                                "content": page,
                                "title": page.get("title"),
                                "excerpt": "",
                                "url": page.get("_links", {}).get("webui", ""),
                            }
                        )

        return {"results": results[:limit], "_links": {}}

    def _search_legacy(self, params: dict[str, Any]) -> dict[str, Any]:
        """Legacy search API."""
        return self._search(params)

    def _get_labels(self, page_id: str) -> dict[str, Any]:
        """Get labels for a page."""
        labels = self._labels.get(page_id, [])  # type: ignore[attr-defined]
        return {"results": labels, "_links": {}}

    def _add_label(self, page_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Add a label to a page."""
        if page_id not in self._pages:  # type: ignore[attr-defined]
            from confluence_as.error_handler import NotFoundError

            raise NotFoundError(f"Page {page_id} not found")

        label_name = data.get("name", data.get("label", ""))
        label = {
            "id": self._generate_id(),  # type: ignore[attr-defined]
            "name": label_name,
            "prefix": data.get("prefix", "global"),
        }

        if page_id not in self._labels:  # type: ignore[attr-defined]
            self._labels[page_id] = []  # type: ignore[attr-defined]
        self._labels[page_id].append(label)  # type: ignore[attr-defined]

        return label

    def _remove_label(self, page_id: str, label_name: str) -> None:
        """Remove a label from a page."""
        if page_id in self._labels:  # type: ignore[attr-defined]
            self._labels[page_id] = [  # type: ignore[attr-defined]
                label_item
                for label_item in self._labels[page_id]  # type: ignore[attr-defined]
                if label_item.get("name") != label_name
            ]

    def _get_comments(self, page_id: str) -> dict[str, Any]:
        """Get comments for a page."""
        comments = self._comments.get(page_id, [])  # type: ignore[attr-defined]
        return {"results": comments, "_links": {}}

    def _add_comment(self, page_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Add a comment to a page."""
        if page_id not in self._pages:  # type: ignore[attr-defined]
            from confluence_as.error_handler import NotFoundError

            raise NotFoundError(f"Page {page_id} not found")

        comment = {
            "id": self._generate_id(),  # type: ignore[attr-defined]
            "status": "current",
            "title": "",
            "pageId": page_id,
            "authorId": "user-001",
            "createdAt": self._now_iso(),  # type: ignore[attr-defined]
            "body": data.get("body", {}),
            "version": {"number": 1, "createdAt": self._now_iso()},  # type: ignore[attr-defined]
        }

        if page_id not in self._comments:  # type: ignore[attr-defined]
            self._comments[page_id] = []  # type: ignore[attr-defined]
        self._comments[page_id].append(comment)  # type: ignore[attr-defined]

        return comment

    def _delete_comment(self, comment_id: str) -> None:
        """Delete a comment."""
        for page_id, comments in self._comments.items():  # type: ignore[attr-defined]
            self._comments[page_id] = [  # type: ignore[attr-defined]
                c for c in comments if c.get("id") != comment_id
            ]

    def _get_attachments(self, page_id: str) -> dict[str, Any]:
        """Get attachments for a page."""
        attachments = self._attachments.get(page_id, [])  # type: ignore[attr-defined]
        return {"results": attachments, "_links": {}}

    def _get_properties(self, page_id: str) -> dict[str, Any]:
        """Get properties for a page."""
        properties = self._properties.get(page_id, [])  # type: ignore[attr-defined]
        return {"results": properties, "_links": {}}

    def _create_property(self, page_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new property on a page."""
        if page_id not in self._pages:  # type: ignore[attr-defined]
            from confluence_as.error_handler import NotFoundError

            raise NotFoundError(f"Page {page_id} not found")

        property_id = self._generate_id()  # type: ignore[attr-defined]
        prop = {
            "id": property_id,
            "key": data.get("key", ""),
            "value": data.get("value", {}),
            "version": {"number": 1, "createdAt": self._now_iso()},  # type: ignore[attr-defined]
        }

        if page_id not in self._properties:  # type: ignore[attr-defined]
            self._properties[page_id] = []  # type: ignore[attr-defined]
        self._properties[page_id].append(prop)  # type: ignore[attr-defined]

        return prop

    def _update_property(
        self, page_id: str, property_id: str, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Update an existing property."""
        if page_id not in self._properties:  # type: ignore[attr-defined]
            from confluence_as.error_handler import NotFoundError

            raise NotFoundError(f"Property {property_id} not found on page {page_id}")

        for prop in self._properties[page_id]:  # type: ignore[attr-defined]
            if prop["id"] == property_id:
                prop["value"] = data.get("value", prop["value"])
                version_num = data.get("version", {}).get(
                    "number", prop["version"]["number"] + 1
                )
                prop["version"] = {
                    "number": version_num,
                    "createdAt": self._now_iso(),  # type: ignore[attr-defined]
                }
                return prop

        from confluence_as.error_handler import NotFoundError

        raise NotFoundError(f"Property {property_id} not found on page {page_id}")

    def _delete_property(self, page_id: str, property_id: str) -> None:
        """Delete a property."""
        if page_id in self._properties:  # type: ignore[attr-defined]
            self._properties[page_id] = [  # type: ignore[attr-defined]
                p
                for p in self._properties[page_id]  # type: ignore[attr-defined]
                if p.get("id") != property_id
            ]
