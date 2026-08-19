"""
Consolidated pytest fixtures for unit tests.

Migrated from Confluence-Assistant-Skills skill-specific conftest files.
Provides fixtures for all domain tests (comment, label, search, analytics, etc.)
"""

import json
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

# =============================================================================
# MOCK HTTP RESPONSE FIXTURE
# =============================================================================


@pytest.fixture
def mock_response():
    """Factory for creating mock HTTP responses.

    Usage:
        response = mock_response(status_code=200, json_data={"key": "value"})
        response = mock_response(status_code=404, json_data={"message": "Not found"})
    """

    def _create_response(
        status_code: int = 200,
        json_data: dict[str, Any] | None = None,
        text: str = "",
        headers: dict[str, str] | None = None,
    ):
        response = Mock()
        response.status_code = status_code
        response.ok = 200 <= status_code < 300
        response.text = text or json.dumps(json_data or {})
        response.headers = headers or {}

        if json_data is not None:
            response.json.return_value = json_data
        else:
            response.json.side_effect = ValueError("No JSON")

        return response

    return _create_response


# =============================================================================
# MOCK CLIENT FIXTURE
# =============================================================================


@pytest.fixture
def mock_client(mock_response):
    """Create a mock Confluence client with helper methods.

    The client includes a setup_response() helper for configuring mock responses:

    Usage:
        def test_something(mock_client):
            mock_client.setup_response("get", {"results": []})
            result = mock_client.get("/api/v2/pages/123")
    """
    from confluence_as import ConfluenceClient

    with patch.object(ConfluenceClient, "_create_session"):
        client = ConfluenceClient(
            base_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="test-token",
        )

        client.session = MagicMock()

        def setup_response(
            method: str, response_data: dict[str, Any], status_code: int = 200
        ):
            """Configure mock response for a given HTTP method."""
            response = mock_response(status_code=status_code, json_data=response_data)
            method_upper = method.upper()
            # POST/PUT/PATCH use session.request(), GET/DELETE use direct methods
            if method_upper in ("POST", "PUT", "PATCH"):
                client.session.request.return_value = response
            else:
                getattr(client.session, method.lower()).return_value = response

        client.setup_response = setup_response
        yield client


# =============================================================================
# SAMPLE PAGE DATA FIXTURES
# =============================================================================


@pytest.fixture
def sample_page():
    """Sample page data from API (v2 format)."""
    return {
        "id": "123456",
        "status": "current",
        "title": "Test Page",
        "spaceId": "789",
        "parentId": "111",
        "parentType": "page",
        "position": 0,
        "authorId": "user123",
        "ownerId": "user123",
        "createdAt": "2024-01-15T10:30:00.000Z",
        "version": {
            "number": 1,
            "message": "Initial version",
            "minorEdit": False,
            "authorId": "user123",
            "createdAt": "2024-01-15T10:30:00.000Z",
        },
        "body": {
            "storage": {"value": "<p>Test content</p>", "representation": "storage"},
        },
        "_links": {
            "webui": "/wiki/spaces/TEST/pages/123456/Test+Page",
        },
    }


@pytest.fixture
def sample_page_history():
    """Sample page history data from v1 API."""
    return {
        "id": "123456",
        "type": "page",
        "title": "Test Page",
        "version": {
            "number": 5,
            "when": "2024-01-15T10:30:00.000Z",
            "by": {"displayName": "John Doe"},
        },
        "history": {
            "latest": True,
            "createdBy": {"displayName": "John Doe"},
            "createdDate": "2024-01-01T10:00:00.000Z",
            "contributors": {
                "publishers": {
                    "users": [
                        {"displayName": "John Doe", "username": "jdoe"},
                        {"displayName": "Jane Smith", "username": "jsmith"},
                    ]
                }
            },
        },
    }


# =============================================================================
# SAMPLE SPACE DATA FIXTURES
# =============================================================================


@pytest.fixture
def sample_space():
    """Sample space data from API."""
    return {
        "id": "789",
        "key": "TEST",
        "name": "Test Space",
        "type": "global",
        "status": "current",
        "homepageId": "123456",
        "_links": {"webui": "/wiki/spaces/TEST"},
    }


# =============================================================================
# SAMPLE COMMENT DATA FIXTURES
# =============================================================================


@pytest.fixture
def sample_comment():
    """Sample comment data from API."""
    return {
        "id": "999",
        "status": "current",
        "title": "Re: Test Page",
        "pageId": "123456",
        "version": {"number": 1},
        "body": {
            "storage": {
                "value": "<p>This is a comment</p>",
                "representation": "storage",
            }
        },
        "createdAt": "2025-12-28T10:00:00.000Z",
        "authorId": "user123",
        "_links": {"webui": "/wiki/spaces/TEST/pages/123456#comment-999"},
    }


# =============================================================================
# SAMPLE LABEL DATA FIXTURES
# =============================================================================


@pytest.fixture
def sample_label():
    """Sample label data from API."""
    return {"id": "label-1", "name": "documentation", "prefix": "global"}


@pytest.fixture
def sample_labels():
    """Sample labels collection from API."""
    return {
        "results": [
            {"id": "label-1", "name": "documentation", "prefix": "global"},
            {"id": "label-2", "name": "approved", "prefix": "global"},
            {"id": "label-3", "name": "draft", "prefix": "global"},
        ],
        "_links": {},
    }


# =============================================================================
# SAMPLE SEARCH DATA FIXTURES
# =============================================================================


@pytest.fixture
def sample_search_results(sample_page):
    """Sample search results from API."""
    return {
        "results": [
            {
                "content": sample_page,
                "excerpt": "This is a <em>test</em> page with content...",
                "lastModified": "2024-01-15T10:30:00.000Z",
            }
        ],
        "_links": {"next": "/rest/api/search?cql=space=TEST&cursor=abc123"},
        "limit": 25,
        "size": 1,
        "start": 0,
        "totalSize": 1,
    }


@pytest.fixture
def sample_cql_fields():
    """Sample CQL field suggestions."""
    return [
        {"name": "space", "type": "string", "description": "Space key"},
        {"name": "title", "type": "string", "description": "Page title"},
        {"name": "text", "type": "string", "description": "Full text search"},
        {
            "name": "type",
            "type": "enum",
            "description": "Content type",
            "values": ["page", "blogpost", "comment", "attachment"],
        },
        {"name": "label", "type": "string", "description": "Content label"},
        {"name": "creator", "type": "string", "description": "Content creator"},
        {"name": "created", "type": "date", "description": "Creation date"},
        {"name": "lastModified", "type": "date", "description": "Last modified date"},
        {"name": "ancestor", "type": "string", "description": "Ancestor page ID"},
        {"name": "parent", "type": "string", "description": "Parent page ID"},
    ]


@pytest.fixture
def sample_cql_operators():
    """Sample CQL operators."""
    return [
        {"operator": "=", "description": "Equals"},
        {"operator": "!=", "description": "Not equals"},
        {"operator": "~", "description": "Contains (text search)"},
        {"operator": "!~", "description": "Does not contain"},
        {"operator": ">", "description": "Greater than"},
        {"operator": "<", "description": "Less than"},
        {"operator": ">=", "description": "Greater than or equal"},
        {"operator": "<=", "description": "Less than or equal"},
        {"operator": "in", "description": "In list"},
        {"operator": "not in", "description": "Not in list"},
    ]


@pytest.fixture
def sample_cql_functions():
    """Sample CQL functions."""
    return [
        {"name": "currentUser()", "description": "Current logged in user"},
        {"name": "startOfDay()", "description": "Start of today"},
        {"name": "startOfWeek()", "description": "Start of this week"},
        {"name": "startOfMonth()", "description": "Start of this month"},
        {"name": "startOfYear()", "description": "Start of this year"},
        {"name": "endOfDay()", "description": "End of today"},
        {"name": "endOfWeek()", "description": "End of this week"},
        {"name": "endOfMonth()", "description": "End of this month"},
        {"name": "endOfYear()", "description": "End of this year"},
    ]


@pytest.fixture
def sample_query_history():
    """Sample query history entries."""
    return [
        {
            "query": "space = 'DOCS' AND type = page",
            "timestamp": "2024-01-15T10:30:00.000Z",
            "results_count": 42,
        },
        {
            "query": "label = 'api' AND creator = currentUser()",
            "timestamp": "2024-01-14T15:45:00.000Z",
            "results_count": 15,
        },
        {
            "query": "text ~ 'documentation' ORDER BY lastModified DESC",
            "timestamp": "2024-01-13T09:20:00.000Z",
            "results_count": 128,
        },
    ]


@pytest.fixture
def sample_spaces_for_suggestion():
    """Sample spaces for field value suggestions."""
    return {
        "results": [
            {"id": "1", "key": "DOCS", "name": "Documentation"},
            {"id": "2", "key": "KB", "name": "Knowledge Base"},
            {"id": "3", "key": "DEV", "name": "Development"},
        ]
    }


@pytest.fixture
def sample_labels_for_suggestion():
    """Sample labels for field value suggestions."""
    return {
        "results": [
            {"id": "1", "name": "documentation", "prefix": "global"},
            {"id": "2", "name": "api", "prefix": "global"},
            {"id": "3", "name": "tutorial", "prefix": "global"},
            {"id": "4", "name": "reference", "prefix": "global"},
        ]
    }


# =============================================================================
# SAMPLE ATTACHMENT DATA FIXTURES
# =============================================================================


@pytest.fixture
def sample_attachment():
    """Sample attachment data from API."""
    return {
        "id": "att123456",
        "status": "current",
        "title": "test-file.pdf",
        "fileId": "file123",
        "fileSize": 1024,
        "webuiLink": "/wiki/download/attachments/123456/test-file.pdf",
        "downloadLink": "/wiki/download/attachments/123456/test-file.pdf",
        "mediaType": "application/pdf",
        "version": {"number": 1, "createdAt": "2024-01-01T00:00:00.000Z"},
        "pageId": "123456",
    }


@pytest.fixture
def test_file(tmp_path):
    """Create a temporary test file."""
    test_file = tmp_path / "test_upload.txt"
    test_file.write_text("This is a test file for attachment upload")
    return test_file


@pytest.fixture
def test_pdf_file(tmp_path):
    """Create a temporary test PDF file (mock)."""
    test_file = tmp_path / "test_document.pdf"
    test_file.write_bytes(b"%PDF-1.4 mock pdf content")
    return test_file


@pytest.fixture
def test_image_file(tmp_path):
    """Create a temporary test image file (mock)."""
    test_file = tmp_path / "test_image.png"
    test_file.write_bytes(b"\x89PNG\r\n\x1a\n mock png content")
    return test_file


# =============================================================================
# SAMPLE WATCH DATA FIXTURES
# =============================================================================


@pytest.fixture
def sample_watcher():
    """Sample watcher/user data from API."""
    return {
        "type": "known",
        "accountId": "user-123",
        "email": "test@example.com",
        "displayName": "Test User",
        "publicName": "Test User",
    }


@pytest.fixture
def sample_watchers(sample_watcher):
    """Sample watchers data."""
    return {
        "results": [
            sample_watcher,
            {
                "type": "known",
                "accountId": "user-456",
                "email": "user2@example.com",
                "displayName": "User Two",
            },
        ],
        "start": 0,
        "limit": 25,
        "size": 2,
    }


@pytest.fixture
def sample_watch_response():
    """Sample watch response from API."""
    return {"success": True, "status_code": 200}


# =============================================================================
# SAMPLE TEMPLATE DATA FIXTURES
# =============================================================================


@pytest.fixture
def sample_template():
    """Sample template data from API."""
    return {
        "templateId": "tmpl-123",
        "name": "Meeting Notes",
        "description": "Template for meeting notes",
        "templateType": "page",
        "body": {
            "storage": {
                "value": "<h1>Meeting Notes</h1><p>Date: </p><p>Attendees: </p>",
                "representation": "storage",
            }
        },
        "labels": [{"name": "template"}],
        "space": {"key": "DOCS"},
    }


@pytest.fixture
def sample_blueprint():
    """Sample blueprint data from API."""
    return {
        "blueprintId": "bp-456",
        "name": "Project Plan",
        "description": "Blueprint for project planning",
        "contentBlueprintId": "com.atlassian.confluence.plugins.confluence-software-project:project-plan-blueprint",
        "moduleCompleteKey": "com.atlassian.confluence.plugins.confluence-software-project:project-plan-blueprint",
    }


# =============================================================================
# SAMPLE PROPERTY DATA FIXTURES
# =============================================================================


@pytest.fixture
def sample_property():
    """Sample property data from API."""
    return {
        "id": "prop-123",
        "key": "my-property",
        "value": {"data": "test value", "metadata": {"example": "data"}},
        "version": {"number": 1},
    }


@pytest.fixture
def sample_properties():
    """Sample properties list from API."""
    return {
        "results": [
            {
                "id": "prop-1",
                "key": "property-one",
                "value": {"data": "value one"},
                "version": {"number": 1},
            },
            {
                "id": "prop-2",
                "key": "property-two",
                "value": {"data": "value two"},
                "version": {"number": 2},
            },
        ],
        "_links": {},
    }


# =============================================================================
# SAMPLE PERMISSION DATA FIXTURES
# =============================================================================


@pytest.fixture
def sample_space_permissions():
    """Sample space permissions data from API."""
    return {
        "results": [
            {
                "principal": {"type": "user", "id": "user-123"},
                "operation": {"key": "read", "target": "space"},
            },
            {
                "principal": {"type": "group", "id": "group-456"},
                "operation": {"key": "administer", "target": "space"},
            },
        ],
        "_links": {},
    }


@pytest.fixture
def sample_page_restrictions():
    """Sample page restrictions data from v1 API."""
    return {
        "read": {
            "operation": "read",
            "restrictions": {
                "user": {
                    "results": [
                        {
                            "type": "known",
                            "username": "user1",
                            "userKey": "user-key-1",
                            "accountId": "account-id-1",
                        }
                    ],
                    "size": 1,
                },
                "group": {
                    "results": [
                        {
                            "type": "group",
                            "name": "confluence-administrators",
                            "id": "group-id-1",
                        }
                    ],
                    "size": 1,
                },
            },
        },
        "update": {
            "operation": "update",
            "restrictions": {
                "user": {"results": [], "size": 0},
                "group": {"results": [], "size": 0},
            },
        },
    }


@pytest.fixture
def sample_page_operations():
    """Sample page operations data from v2 API."""
    return {
        "results": [
            {"operation": "read", "targetType": "page"},
            {"operation": "update", "targetType": "page"},
            {"operation": "delete", "targetType": "page"},
        ],
        "_links": {},
    }


# =============================================================================
# SAMPLE ANALYTICS DATA FIXTURES
# =============================================================================


@pytest.fixture
def analytics_search_results():
    """Sample CQL search results for analytics."""
    return {
        "results": [
            {
                "content": {
                    "id": "123456",
                    "type": "page",
                    "title": "Popular Page 1",
                    "space": {"key": "TEST"},
                    "_links": {"webui": "/wiki/spaces/TEST/pages/123456"},
                }
            },
            {
                "content": {
                    "id": "123457",
                    "type": "page",
                    "title": "Popular Page 2",
                    "space": {"key": "TEST"},
                    "_links": {"webui": "/wiki/spaces/TEST/pages/123457"},
                }
            },
        ],
        "start": 0,
        "limit": 25,
        "size": 2,
        "_links": {},
    }
