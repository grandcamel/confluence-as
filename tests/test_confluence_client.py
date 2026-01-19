"""Tests for confluence_client module."""

import tempfile
from pathlib import Path

import pytest
import responses
from confluence_assistant_skills import ConfluenceClient, create_client

from confluence_assistant_skills_lib.error_handler import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
)


@pytest.fixture
def client():
    """Create a test client."""
    return ConfluenceClient(
        base_url="https://test.atlassian.net",
        email="test@example.com",
        api_token="test-token",
        timeout=10,
        max_retries=1,
    )


class TestClientInit:
    """Tests for client initialization."""

    def test_basic_init(self):
        """Client initializes with required parameters."""
        client = ConfluenceClient(
            base_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="test-token",
        )
        assert client.base_url == "https://test.atlassian.net"
        assert client.email == "test@example.com"
        assert client.api_token == "test-token"

    def test_trailing_slash_removed(self):
        """Trailing slash is removed from base URL."""
        client = ConfluenceClient(
            base_url="https://test.atlassian.net/",
            email="test@example.com",
            api_token="test-token",
        )
        assert client.base_url == "https://test.atlassian.net"

    def test_wiki_suffix_removed(self):
        """Wiki suffix is removed from base URL."""
        client = ConfluenceClient(
            base_url="https://test.atlassian.net/wiki",
            email="test@example.com",
            api_token="test-token",
        )
        assert client.base_url == "https://test.atlassian.net"

    def test_custom_options(self):
        """Custom options are applied."""
        client = ConfluenceClient(
            base_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="test-token",
            timeout=60,
            max_retries=5,
            retry_backoff=3.0,
            verify_ssl=False,
        )
        assert client.timeout == 60
        assert client.max_retries == 5
        assert client.retry_backoff == 3.0
        assert client.verify_ssl is False

    def test_session_headers(self):
        """Session has correct headers."""
        client = ConfluenceClient(
            base_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="test-token",
        )
        assert client.session.headers["Accept"] == "application/json"
        assert client.session.headers["Content-Type"] == "application/json"
        assert "Confluence-Assistant-Skills-Lib" in client.session.headers["User-Agent"]


class TestSessionCleanup:
    """Tests for session cleanup methods."""

    def test_close(self):
        """Client close method closes session."""
        client = ConfluenceClient(
            base_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="test-token",
        )
        # Session should be open initially
        assert client.session is not None

        # Close the session
        client.close()

        # Session should still exist but be closed (no way to check directly)
        # Just verify no exception is raised on double close
        client.close()

    def test_context_manager(self):
        """Client works as context manager."""
        with ConfluenceClient(
            base_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="test-token",
        ) as client:
            assert client.session is not None
            assert client.base_url == "https://test.atlassian.net"
        # Session should be closed after context exit

    @responses.activate
    def test_context_manager_with_request(self):
        """Context manager works with actual requests."""
        responses.add(
            responses.GET,
            "https://test.atlassian.net/wiki/api/v2/pages/12345",
            json={"id": "12345", "title": "Test Page"},
            status=200,
        )

        with ConfluenceClient(
            base_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="test-token",
        ) as client:
            result = client.get("/api/v2/pages/12345")
            assert result["id"] == "12345"


class TestBuildUrl:
    """Tests for URL building."""

    def test_v2_endpoint(self, client):
        """V2 API endpoints are built correctly."""
        url = client._build_url("/api/v2/pages/12345")
        assert url == "https://test.atlassian.net/wiki/api/v2/pages/12345"

    def test_v1_endpoint(self, client):
        """V1 API endpoints are built correctly."""
        url = client._build_url("/rest/api/content/12345")
        assert url == "https://test.atlassian.net/wiki/rest/api/content/12345"

    def test_wiki_endpoint(self, client):
        """Wiki endpoints are built correctly."""
        url = client._build_url("wiki/rest/api/content/12345")
        assert url == "https://test.atlassian.net/wiki/rest/api/content/12345"

    def test_leading_slash_stripped(self, client):
        """Leading slash is handled."""
        url1 = client._build_url("/api/v2/pages")
        url2 = client._build_url("api/v2/pages")
        assert url1 == url2


class TestGetRequest:
    """Tests for GET requests."""

    @responses.activate
    def test_get_success(self, client):
        """Successful GET request."""
        responses.add(
            responses.GET,
            "https://test.atlassian.net/wiki/api/v2/pages/12345",
            json={"id": "12345", "title": "Test Page"},
            status=200,
        )

        result = client.get("/api/v2/pages/12345")
        assert result["id"] == "12345"
        assert result["title"] == "Test Page"

    @responses.activate
    def test_get_with_params(self, client):
        """GET request with query parameters."""
        responses.add(
            responses.GET,
            "https://test.atlassian.net/wiki/api/v2/pages",
            json={"results": []},
            status=200,
        )

        client.get("/api/v2/pages", params={"space-id": "123"})
        assert "space-id=123" in responses.calls[0].request.url

    @responses.activate
    def test_get_404(self, client):
        """GET request returns 404."""
        responses.add(
            responses.GET,
            "https://test.atlassian.net/wiki/api/v2/pages/99999",
            json={"message": "Page not found"},
            status=404,
        )

        with pytest.raises(NotFoundError):
            client.get("/api/v2/pages/99999")

    @responses.activate
    def test_get_401(self, client):
        """GET request returns 401."""
        responses.add(
            responses.GET,
            "https://test.atlassian.net/wiki/api/v2/pages/12345",
            json={"message": "Unauthorized"},
            status=401,
        )

        with pytest.raises(AuthenticationError):
            client.get("/api/v2/pages/12345")

    @responses.activate
    def test_get_500(self, client):
        """GET request returns 500."""
        responses.add(
            responses.GET,
            "https://test.atlassian.net/wiki/api/v2/pages/12345",
            json={"message": "Internal error"},
            status=500,
        )

        with pytest.raises(ServerError):
            client.get("/api/v2/pages/12345")


class TestPostRequest:
    """Tests for POST requests."""

    @responses.activate
    def test_post_success(self, client):
        """Successful POST request."""
        responses.add(
            responses.POST,
            "https://test.atlassian.net/wiki/api/v2/pages",
            json={"id": "12345", "title": "New Page"},
            status=201,
        )

        result = client.post(
            "/api/v2/pages",
            json_data={"spaceId": "123", "title": "New Page"},
        )
        assert result["id"] == "12345"

    @responses.activate
    def test_post_with_list(self, client):
        """POST request with list body."""
        responses.add(
            responses.POST,
            "https://test.atlassian.net/wiki/api/v2/labels",
            json={"results": []},
            status=200,
        )

        client.post("/api/v2/labels", json_data=[{"name": "label1"}])
        # Should not raise


class TestPutRequest:
    """Tests for PUT requests."""

    @responses.activate
    def test_put_success(self, client):
        """Successful PUT request."""
        responses.add(
            responses.PUT,
            "https://test.atlassian.net/wiki/api/v2/pages/12345",
            json={"id": "12345", "title": "Updated Page"},
            status=200,
        )

        result = client.put(
            "/api/v2/pages/12345",
            json_data={"title": "Updated Page", "version": {"number": 2}},
        )
        assert result["title"] == "Updated Page"


class TestDeleteRequest:
    """Tests for DELETE requests."""

    @responses.activate
    def test_delete_success(self, client):
        """Successful DELETE request."""
        responses.add(
            responses.DELETE,
            "https://test.atlassian.net/wiki/api/v2/pages/12345",
            status=204,
        )

        result = client.delete("/api/v2/pages/12345")
        assert result == {}


class TestHandleResponse:
    """Tests for response handling."""

    @responses.activate
    def test_204_returns_empty_dict(self, client):
        """204 response returns empty dict."""
        responses.add(
            responses.DELETE,
            "https://test.atlassian.net/wiki/api/v2/pages/12345",
            status=204,
        )

        result = client.delete("/api/v2/pages/12345")
        assert result == {}

    @responses.activate
    def test_non_json_success(self, client):
        """Non-JSON success response."""
        responses.add(
            responses.GET,
            "https://test.atlassian.net/wiki/api/v2/pages/12345",
            body="OK",
            status=200,
        )

        result = client.get("/api/v2/pages/12345")
        assert result == {"success": True, "status_code": 200}

    @responses.activate
    def test_rate_limit_429(self, client):
        """429 response raises RateLimitError."""
        responses.add(
            responses.GET,
            "https://test.atlassian.net/wiki/api/v2/pages/12345",
            json={"message": "Rate limited"},
            status=429,
            headers={"Retry-After": "60"},
        )

        with pytest.raises(RateLimitError):
            client.get("/api/v2/pages/12345")


class TestPagination:
    """Tests for pagination."""

    @responses.activate
    def test_single_page(self, client):
        """Single page of results."""
        responses.add(
            responses.GET,
            "https://test.atlassian.net/wiki/api/v2/pages",
            json={"results": [{"id": "1"}, {"id": "2"}], "_links": {}},
            status=200,
        )

        results = list(client.paginate("/api/v2/pages"))
        assert len(results) == 2
        assert results[0]["id"] == "1"

    @responses.activate
    def test_multiple_pages(self, client):
        """Multiple pages of results."""
        responses.add(
            responses.GET,
            "https://test.atlassian.net/wiki/api/v2/pages",
            json={
                "results": [{"id": "1"}],
                "_links": {"next": "/api/v2/pages?cursor=abc123"},
            },
            status=200,
        )
        responses.add(
            responses.GET,
            "https://test.atlassian.net/wiki/api/v2/pages",
            json={"results": [{"id": "2"}], "_links": {}},
            status=200,
        )

        results = list(client.paginate("/api/v2/pages"))
        assert len(results) == 2

    @responses.activate
    def test_pagination_with_limit(self, client):
        """Pagination respects limit."""
        responses.add(
            responses.GET,
            "https://test.atlassian.net/wiki/api/v2/pages",
            json={
                "results": [{"id": "1"}, {"id": "2"}, {"id": "3"}],
                "_links": {"next": "/api/v2/pages?cursor=abc123"},
            },
            status=200,
        )

        results = list(client.paginate("/api/v2/pages", limit=2))
        assert len(results) == 2


class TestFileOperations:
    """Tests for file upload/download."""

    @responses.activate
    def test_upload_file(self, client):
        """File upload works."""
        responses.add(
            responses.POST,
            "https://test.atlassian.net/wiki/rest/api/content/12345/child/attachment",
            json={"results": [{"id": "att123"}]},
            status=200,
        )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"test content")
            f.flush()

            result = client.upload_file(
                "/rest/api/content/12345/child/attachment",
                file_path=f.name,
            )
            assert "results" in result

    def test_upload_file_not_found(self, client):
        """Upload raises error for missing file."""
        with pytest.raises(ValidationError):
            client.upload_file(
                "/rest/api/content/12345/child/attachment",
                file_path="/nonexistent/file.txt",
            )

    @responses.activate
    def test_download_file(self, client):
        """File download works."""
        responses.add(
            responses.GET,
            "https://test.atlassian.net/wiki/download/attachments/12345/file.pdf",
            body=b"PDF content",
            status=200,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "downloaded.pdf"
            result = client.download_file(
                "/wiki/download/attachments/12345/file.pdf",
                output_path=output_path,
            )
            assert result == output_path
            assert output_path.exists()
            assert output_path.read_bytes() == b"PDF content"


class TestAttachmentMethods:
    """Tests for attachment convenience methods."""

    @responses.activate
    def test_upload_attachment(self, client):
        """Upload attachment to page."""
        responses.add(
            responses.POST,
            "https://test.atlassian.net/wiki/rest/api/content/12345/child/attachment",
            json={"results": [{"id": "att123"}]},
            status=200,
        )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
            f.write(b"content")
            f.flush()

            result = client.upload_attachment("12345", f.name, comment="Test upload")
            assert "results" in result

    @responses.activate
    def test_download_attachment(self, client):
        """Download attachment content."""
        responses.add(
            responses.GET,
            "https://test.atlassian.net/wiki/api/v2/attachments/att123",
            json={"id": "att123", "downloadLink": "/download/file.pdf"},
            status=200,
        )
        responses.add(
            responses.GET,
            "https://test.atlassian.net/wiki/download/file.pdf",
            body=b"file content",
            status=200,
        )

        content = client.download_attachment("att123")
        assert content == b"file content"

    @responses.activate
    def test_download_attachment_no_link(self, client):
        """Download attachment raises error when no link."""
        responses.add(
            responses.GET,
            "https://test.atlassian.net/wiki/api/v2/attachments/att123",
            json={"id": "att123"},
            status=200,
        )

        with pytest.raises(ValidationError):
            client.download_attachment("att123")


class TestTestConnection:
    """Tests for connection testing."""

    @responses.activate
    def test_connection_success(self, client):
        """Successful connection test."""
        responses.add(
            responses.GET,
            "https://test.atlassian.net/wiki/rest/api/user/current",
            json={"displayName": "Test User", "email": "test@example.com"},
            status=200,
        )

        result = client.test_connection()
        assert result["success"] is True
        assert result["user"] == "Test User"

    @responses.activate
    def test_connection_failure(self, client):
        """Failed connection test."""
        responses.add(
            responses.GET,
            "https://test.atlassian.net/wiki/rest/api/user/current",
            json={"message": "Unauthorized"},
            status=401,
        )

        result = client.test_connection()
        assert result["success"] is False
        assert "error" in result


class TestCreateClient:
    """Tests for create_client factory function."""

    def test_create_client(self):
        """Factory function creates client."""
        client = create_client(
            base_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="test-token",
        )
        assert isinstance(client, ConfluenceClient)
        assert client.base_url == "https://test.atlassian.net"
