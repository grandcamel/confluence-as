"""Tests for error_handler module."""

from unittest.mock import Mock

import pytest

from confluence_assistant_skills import (
    AuthenticationError,
    ConflictError,
    ConfluenceError,
    NotFoundError,
    PermissionError,
    RateLimitError,
    ServerError,
    extract_error_message,
    handle_confluence_error,
    sanitize_error_message,
)
from confluence_assistant_skills.error_handler import ValidationError


class TestConfluenceError:
    """Tests for ConfluenceError class."""

    def test_basic_error(self):
        error = ConfluenceError("Something went wrong")
        assert str(error) == "Something went wrong"

    def test_with_status_code(self):
        error = ConfluenceError("Error", status_code=404)
        assert "(HTTP 404)" in str(error)

    def test_with_operation(self):
        error = ConfluenceError("Error", operation="get page")
        assert "[get page]" in str(error)


class TestSanitizeErrorMessage:
    """Tests for sanitize_error_message."""

    def test_sanitizes_api_token(self):
        msg = 'api_token="secret12345678"'
        result = sanitize_error_message(msg)
        assert "secret12345678" not in result
        assert "[REDACTED]" in result

    def test_sanitizes_bearer_token(self):
        msg = "Bearer abc123def456"
        result = sanitize_error_message(msg)
        assert "abc123def456" not in result
        assert "[REDACTED]" in result

    def test_sanitizes_basic_auth(self):
        msg = "Basic YWJjMTIzZGVmNDU2"
        result = sanitize_error_message(msg)
        assert "YWJjMTIzZGVmNDU2" not in result

    def test_sanitizes_url_credentials(self):
        msg = "https://user:password123@example.com"
        result = sanitize_error_message(msg)
        assert "password123" not in result

    def test_leaves_normal_text(self):
        msg = "Page not found"
        result = sanitize_error_message(msg)
        assert result == "Page not found"


class TestExtractErrorMessage:
    """Tests for extract_error_message."""

    def test_v2_api_errors(self):
        response = Mock()
        response.json.return_value = {
            "errors": [{"title": "Not Found", "detail": "Page does not exist"}]
        }
        result = extract_error_message(response)
        assert "Not Found" in result

    def test_v1_api_message(self):
        response = Mock()
        response.json.return_value = {"message": "Invalid request"}
        result = extract_error_message(response)
        assert "Invalid request" in result

    def test_fallback_to_raw_text(self):
        response = Mock()
        response.json.side_effect = ValueError("Not JSON")
        response.text = "Raw error text"
        result = extract_error_message(response)
        assert "Raw error text" in result


class TestHandleConfluenceError:
    """Tests for handle_confluence_error."""

    def _create_response(self, status_code, json_data=None):
        response = Mock()
        response.status_code = status_code
        response.ok = status_code < 400
        response.headers = {}
        if json_data:
            response.json.return_value = json_data
        else:
            response.json.return_value = {"message": "Error"}
        return response

    def test_400_raises_validation_error(self):
        response = self._create_response(400)
        with pytest.raises(ValidationError):
            handle_confluence_error(response)

    def test_401_raises_authentication_error(self):
        response = self._create_response(401)
        with pytest.raises(AuthenticationError):
            handle_confluence_error(response)

    def test_403_raises_permission_error(self):
        response = self._create_response(403)
        with pytest.raises(PermissionError):
            handle_confluence_error(response)

    def test_404_raises_not_found_error(self):
        response = self._create_response(404)
        with pytest.raises(NotFoundError):
            handle_confluence_error(response)

    def test_409_raises_conflict_error(self):
        response = self._create_response(409)
        with pytest.raises(ConflictError):
            handle_confluence_error(response)

    def test_429_raises_rate_limit_error(self):
        response = self._create_response(429)
        response.headers = {"Retry-After": "60"}
        with pytest.raises(RateLimitError) as exc_info:
            handle_confluence_error(response)
        assert exc_info.value.retry_after == 60

    def test_500_raises_server_error(self):
        response = self._create_response(500)
        with pytest.raises(ServerError):
            handle_confluence_error(response)

    def test_operation_included_in_error(self):
        response = self._create_response(404)
        with pytest.raises(NotFoundError) as exc_info:
            handle_confluence_error(response, operation="get page")
        assert exc_info.value.operation == "get page"


class TestExceptionHierarchy:
    """Tests for exception hierarchy."""

    def test_authentication_is_confluence_error(self):
        assert issubclass(AuthenticationError, ConfluenceError)

    def test_permission_is_confluence_error(self):
        assert issubclass(PermissionError, ConfluenceError)

    def test_not_found_is_confluence_error(self):
        assert issubclass(NotFoundError, ConfluenceError)

    def test_rate_limit_is_confluence_error(self):
        assert issubclass(RateLimitError, ConfluenceError)

    def test_server_error_is_confluence_error(self):
        assert issubclass(ServerError, ConfluenceError)
