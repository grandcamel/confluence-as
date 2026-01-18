"""Tests for validators module."""

import pytest

# Import from base library to catch errors from both base validators and local validators
# Our local ValidationError is a subclass, so catching base catches both
from assistant_skills_lib.error_handler import ValidationError

from confluence_assistant_skills import (
    validate_content_type,
    validate_cql,
    validate_email,
    validate_issue_key,
    validate_jql_query,
    validate_label,
    validate_limit,
    validate_page_id,
    validate_space_key,
    validate_title,
    validate_url,
)


class TestValidatePageId:
    """Tests for validate_page_id."""

    def test_valid_numeric_string(self):
        assert validate_page_id("12345") == "12345"

    def test_valid_integer(self):
        assert validate_page_id(12345) == "12345"

    def test_strips_whitespace(self):
        assert validate_page_id("  12345  ") == "12345"

    def test_none_raises_error(self):
        with pytest.raises(ValidationError):
            validate_page_id(None)

    def test_empty_raises_error(self):
        with pytest.raises(ValidationError):
            validate_page_id("")

    def test_non_numeric_raises_error(self):
        with pytest.raises(ValidationError):
            validate_page_id("abc123")

    def test_custom_field_name_in_error(self):
        with pytest.raises(ValidationError) as exc_info:
            validate_page_id(None, field_name="custom_id")
        assert "custom_id" in str(exc_info.value)


class TestValidateSpaceKey:
    """Tests for validate_space_key."""

    def test_valid_uppercase(self):
        assert validate_space_key("DOCS") == "DOCS"

    def test_normalizes_to_uppercase(self):
        assert validate_space_key("docs") == "DOCS"

    def test_alphanumeric_with_underscore(self):
        assert validate_space_key("MY_SPACE_123") == "MY_SPACE_123"

    def test_none_raises_error(self):
        with pytest.raises(ValidationError):
            validate_space_key(None)

    def test_too_short_raises_error(self):
        with pytest.raises(ValidationError):
            validate_space_key("X")

    def test_starts_with_number_raises_error(self):
        with pytest.raises(ValidationError):
            validate_space_key("123ABC")

    def test_special_chars_raises_error(self):
        with pytest.raises(ValidationError):
            validate_space_key("MY-SPACE")


class TestValidateCql:
    """Tests for validate_cql."""

    def test_valid_simple_query(self):
        assert validate_cql('space = "DOCS"') == 'space = "DOCS"'

    def test_valid_complex_query(self):
        query = 'space = "DOCS" AND label = "api" ORDER BY created DESC'
        assert validate_cql(query) == query

    def test_none_raises_error(self):
        with pytest.raises(ValidationError):
            validate_cql(None)

    def test_empty_raises_error(self):
        with pytest.raises(ValidationError):
            validate_cql("")

    def test_unbalanced_parentheses_raises_error(self):
        with pytest.raises(ValidationError):
            validate_cql("space = DOCS AND (label = api")

    def test_unbalanced_quotes_raises_error(self):
        with pytest.raises(ValidationError):
            validate_cql('space = "DOCS')


class TestValidateContentType:
    """Tests for validate_content_type."""

    def test_valid_page(self):
        assert validate_content_type("page") == "page"

    def test_valid_blogpost(self):
        assert validate_content_type("blogpost") == "blogpost"

    def test_normalizes_case(self):
        assert validate_content_type("PAGE") == "page"

    def test_invalid_type_raises_error(self):
        with pytest.raises(ValidationError):
            validate_content_type("invalid")

    def test_custom_allowed_types(self):
        assert validate_content_type("custom", allowed=["custom", "other"]) == "custom"


class TestValidateUrl:
    """Tests for validate_url."""

    def test_valid_https_url(self):
        url = "https://example.atlassian.net"
        assert validate_url(url) == url

    def test_strips_trailing_slash(self):
        assert validate_url("https://example.com/") == "https://example.com"

    def test_http_allowed_by_default(self):
        # HTTP is allowed by default in the base library
        url = "http://example.com"
        assert validate_url(url) == url

    def test_http_disallowed_when_require_https(self):
        with pytest.raises(ValidationError):
            validate_url("http://example.com", require_https=True)

    def test_https_allowed_when_require_https(self):
        url = "https://example.com"
        assert validate_url(url, require_https=True) == url

    def test_atlassian_domain_check(self):
        # Use allowed_domains instead of require_atlassian
        with pytest.raises(ValidationError):
            validate_url("https://example.com", allowed_domains=[".atlassian.net"])

    def test_valid_atlassian_url(self):
        url = "https://mysite.atlassian.net"
        assert validate_url(url, allowed_domains=[".atlassian.net"]) == url


class TestValidateEmail:
    """Tests for validate_email."""

    def test_valid_email(self):
        assert validate_email("user@example.com") == "user@example.com"

    def test_normalizes_to_lowercase(self):
        assert validate_email("User@Example.COM") == "user@example.com"

    def test_invalid_email_raises_error(self):
        with pytest.raises(ValidationError):
            validate_email("not-an-email")

    def test_none_raises_error(self):
        with pytest.raises(ValidationError):
            validate_email(None)


class TestValidateTitle:
    """Tests for validate_title."""

    def test_valid_title(self):
        assert validate_title("My Page Title") == "My Page Title"

    def test_none_raises_error(self):
        with pytest.raises(ValidationError):
            validate_title(None)

    def test_too_long_raises_error(self):
        with pytest.raises(ValidationError):
            validate_title("x" * 256)

    def test_invalid_char_colon_raises_error(self):
        with pytest.raises(ValidationError):
            validate_title("Title: With Colon")

    def test_invalid_char_pipe_raises_error(self):
        with pytest.raises(ValidationError):
            validate_title("Title | With Pipe")


class TestValidateLabel:
    """Tests for validate_label."""

    def test_valid_label(self):
        assert validate_label("my-label") == "my-label"

    def test_normalizes_to_lowercase(self):
        assert validate_label("MY-LABEL") == "my-label"

    def test_spaces_raise_error(self):
        with pytest.raises(ValidationError):
            validate_label("my label")

    def test_special_chars_raise_error(self):
        with pytest.raises(ValidationError):
            validate_label("label@special")


class TestValidateLimit:
    """Tests for validate_limit."""

    def test_valid_limit(self):
        assert validate_limit(50) == 50

    def test_string_converted_to_int(self):
        assert validate_limit("50") == 50

    def test_none_returns_default(self):
        assert validate_limit(None) == 25
        assert validate_limit(None, default=100) == 100

    def test_below_min_raises_error(self):
        with pytest.raises(ValidationError):
            validate_limit(0)

    def test_above_max_raises_error(self):
        with pytest.raises(ValidationError):
            validate_limit(1000)


class TestValidateIssueKey:
    """Tests for validate_issue_key."""

    def test_valid_issue_key(self):
        assert validate_issue_key("PROJECT-123") == "PROJECT-123"

    def test_normalizes_to_uppercase(self):
        assert validate_issue_key("project-123") == "PROJECT-123"

    def test_invalid_format_raises_error(self):
        with pytest.raises(ValidationError):
            validate_issue_key("invalid")

    def test_missing_number_raises_error(self):
        with pytest.raises(ValidationError):
            validate_issue_key("PROJECT-")


class TestValidateJqlQuery:
    """Tests for validate_jql_query."""

    def test_valid_query(self):
        query = "project = TEST AND status = Open"
        assert validate_jql_query(query) == query

    def test_none_raises_error(self):
        with pytest.raises(ValidationError):
            validate_jql_query(None)

    def test_unbalanced_parens_raises_error(self):
        with pytest.raises(ValidationError):
            validate_jql_query("project = TEST AND (status = Open")
