"""Tests for config_manager module."""

import os

import pytest
from assistant_skills_lib.error_handler import ValidationError as BaseValidationError
from confluence_assistant_skills import ConfigManager, get_confluence_client

from confluence_assistant_skills_lib.error_handler import ValidationError


class TestConfigManager:
    """Tests for ConfigManager class."""

    def test_service_name(self):
        """Service name is confluence."""
        manager = ConfigManager()
        assert manager.get_service_name() == "confluence"

    def test_default_config(self):
        """Default configuration is returned."""
        manager = ConfigManager()
        config = manager.get_default_config()

        assert "api" in config
        assert config["api"]["version"] == "2"
        assert config["api"]["timeout"] == 30
        assert config["api"]["max_retries"] == 3
        assert config["api"]["retry_backoff"] == 2.0
        assert config["api"]["verify_ssl"] is True


@pytest.fixture(autouse=True)
def clean_env():
    """Clean up environment and singleton before each test."""
    # Save original values
    orig = {}
    for key in ["CONFLUENCE_SITE_URL", "CONFLUENCE_EMAIL", "CONFLUENCE_API_TOKEN"]:
        orig[key] = os.environ.get(key)

    # Clear singleton
    ConfigManager._instances = {}

    yield

    # Restore original values
    for key, value in orig.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    ConfigManager._instances = {}


class TestGetCredentials:
    """Tests for get_credentials method."""

    def test_all_credentials_present(self):
        """Returns credentials when all env vars are set."""
        os.environ["CONFLUENCE_SITE_URL"] = "https://test.atlassian.net"
        os.environ["CONFLUENCE_EMAIL"] = "test@example.com"
        os.environ["CONFLUENCE_API_TOKEN"] = "test-token"

        manager = ConfigManager()
        credentials = manager.get_credentials()

        assert credentials["url"] == "https://test.atlassian.net"
        assert credentials["email"] == "test@example.com"
        assert credentials["api_token"] == "test-token"

    def test_missing_site_url(self):
        """Raises error when site URL is missing."""
        os.environ.pop("CONFLUENCE_SITE_URL", None)
        os.environ["CONFLUENCE_EMAIL"] = "test@example.com"
        os.environ["CONFLUENCE_API_TOKEN"] = "test-token"

        manager = ConfigManager()

        with pytest.raises((ValidationError, BaseValidationError)) as exc_info:
            manager.get_credentials()
        assert "CONFLUENCE_SITE_URL" in str(exc_info.value)

    def test_missing_email(self):
        """Raises error when email is missing."""
        os.environ["CONFLUENCE_SITE_URL"] = "https://test.atlassian.net"
        os.environ.pop("CONFLUENCE_EMAIL", None)
        os.environ["CONFLUENCE_API_TOKEN"] = "test-token"

        manager = ConfigManager()

        with pytest.raises((ValidationError, BaseValidationError)) as exc_info:
            manager.get_credentials()
        assert "CONFLUENCE_EMAIL" in str(exc_info.value)

    def test_missing_api_token(self):
        """Raises error when API token is missing."""
        os.environ["CONFLUENCE_SITE_URL"] = "https://test.atlassian.net"
        os.environ["CONFLUENCE_EMAIL"] = "test@example.com"
        os.environ.pop("CONFLUENCE_API_TOKEN", None)

        manager = ConfigManager()

        with pytest.raises((ValidationError, BaseValidationError)) as exc_info:
            manager.get_credentials()
        assert "CONFLUENCE_API_TOKEN" in str(exc_info.value)

    def test_invalid_email_format(self):
        """Raises error for invalid email format."""
        os.environ["CONFLUENCE_SITE_URL"] = "https://test.atlassian.net"
        os.environ["CONFLUENCE_EMAIL"] = "not-an-email"
        os.environ["CONFLUENCE_API_TOKEN"] = "test-token"

        manager = ConfigManager()

        with pytest.raises((ValidationError, BaseValidationError)):
            manager.get_credentials()

    def test_http_url_rejected(self):
        """Raises error for non-HTTPS URL."""
        os.environ["CONFLUENCE_SITE_URL"] = "http://test.atlassian.net"
        os.environ["CONFLUENCE_EMAIL"] = "test@example.com"
        os.environ["CONFLUENCE_API_TOKEN"] = "test-token"

        manager = ConfigManager()

        with pytest.raises((ValidationError, BaseValidationError)):
            manager.get_credentials()


class TestGetConfluenceClient:
    """Tests for get_confluence_client function."""

    def test_returns_client(self):
        """Returns configured ConfluenceClient."""
        os.environ["CONFLUENCE_SITE_URL"] = "https://test.atlassian.net"
        os.environ["CONFLUENCE_EMAIL"] = "test@example.com"
        os.environ["CONFLUENCE_API_TOKEN"] = "test-token"

        client = get_confluence_client()

        from confluence_assistant_skills import ConfluenceClient

        assert isinstance(client, ConfluenceClient)
        assert client.base_url == "https://test.atlassian.net"
        assert client.email == "test@example.com"
        assert client.api_token == "test-token"

    def test_uses_default_settings(self):
        """Client uses default API settings."""
        os.environ["CONFLUENCE_SITE_URL"] = "https://test.atlassian.net"
        os.environ["CONFLUENCE_EMAIL"] = "test@example.com"
        os.environ["CONFLUENCE_API_TOKEN"] = "test-token"

        client = get_confluence_client()

        assert client.timeout == 30
        assert client.max_retries == 3
        assert client.retry_backoff == 2.0
        assert client.verify_ssl is True

    def test_override_settings(self):
        """Client settings can be overridden."""
        os.environ["CONFLUENCE_SITE_URL"] = "https://test.atlassian.net"
        os.environ["CONFLUENCE_EMAIL"] = "test@example.com"
        os.environ["CONFLUENCE_API_TOKEN"] = "test-token"

        client = get_confluence_client(timeout=60, max_retries=5)

        assert client.timeout == 60
        assert client.max_retries == 5

    def test_missing_credentials_raises_error(self):
        """Raises error when credentials are missing."""
        os.environ.pop("CONFLUENCE_SITE_URL", None)
        os.environ.pop("CONFLUENCE_EMAIL", None)
        os.environ.pop("CONFLUENCE_API_TOKEN", None)

        with pytest.raises((ValidationError, BaseValidationError)):
            get_confluence_client()
