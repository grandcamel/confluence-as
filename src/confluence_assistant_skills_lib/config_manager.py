"""
Configuration Manager for Confluence Assistant Skills

Handles configuration from multiple sources with priority:
1. Environment variables (highest priority)
2. settings.local.json (personal, gitignored)
3. settings.json (team defaults, committed)
4. Built-in defaults (lowest priority)

Required Environment Variables:
    CONFLUENCE_API_TOKEN - API token for authentication
    CONFLUENCE_EMAIL - Email address for authentication
    CONFLUENCE_SITE_URL - Confluence site URL (e.g., https://your-site.atlassian.net)

Usage:
    from confluence_assistant_skills_lib import get_confluence_client

    # Get a configured client
    client = get_confluence_client()
"""

from typing import TYPE_CHECKING, Any

from assistant_skills_lib.config_manager import BaseConfigManager
from assistant_skills_lib.error_handler import ValidationError

if TYPE_CHECKING:
    from .confluence_client import ConfluenceClient


class ConfigManager(BaseConfigManager):
    """
    Manages Confluence configuration from environment variables and settings files.
    """

    def get_service_name(self) -> str:
        """Returns the name of the service, which is 'confluence'."""
        return "confluence"

    def get_default_config(self) -> dict[str, Any]:
        """Returns the default configuration dictionary for Confluence."""
        return {
            "api": {
                "version": "2",
                "timeout": 30,
                "max_retries": 3,
                "retry_backoff": 2.0,
                "verify_ssl": True,
            },
        }

    def get_credentials(self) -> dict[str, Any]:
        """
        Get and validate credentials from environment variables.

        Returns:
            A dictionary containing validated 'url', 'email', and 'api_token'.

        Raises:
            ValidationError: If required credentials are not found or are invalid.
        """
        url = self.get_credential_from_env("SITE_URL")
        email = self.get_credential_from_env("EMAIL")
        api_token = self.get_credential_from_env("API_TOKEN")

        if not url:
            raise ValidationError(
                "Confluence URL not configured. "
                "Set CONFLUENCE_SITE_URL environment variable."
            )
        if not email:
            raise ValidationError(
                "Confluence email not configured. "
                "Set CONFLUENCE_EMAIL environment variable."
            )
        if not api_token:
            raise ValidationError(
                "Confluence API token not configured. "
                "Set CONFLUENCE_API_TOKEN environment variable."
            )

        from assistant_skills_lib.validators import validate_email, validate_url

        return {
            "url": validate_url(url, require_https=True),
            "email": validate_email(email),
            "api_token": api_token,
        }


# Module-level convenience functions


def get_confluence_client(**kwargs) -> "ConfluenceClient":
    """
    Get a configured Confluence client.

    Args:
        **kwargs: Additional arguments passed to ConfluenceClient.

    Returns:
        Configured ConfluenceClient instance.
    """
    from .confluence_client import ConfluenceClient

    manager = ConfigManager.get_instance()

    # Get credentials and API settings from the manager
    credentials = manager.get_credentials()
    api_config = manager.get_api_config()

    client_kwargs = {
        "base_url": credentials["url"],
        "email": credentials["email"],
        "api_token": credentials["api_token"],
        "timeout": api_config.get("timeout", 30),
        "max_retries": api_config.get("max_retries", 3),
        "retry_backoff": api_config.get("retry_backoff", 2.0),
        "verify_ssl": api_config.get("verify_ssl", True),
    }
    client_kwargs.update(kwargs)

    return ConfluenceClient(**client_kwargs)
