"""
Confluence Credential Management

Provides secure credential storage with keychain integration for Confluence Assistant Skills.
Extends BaseCredentialManager from assistant_skills_lib.

Priority order:
1. Environment variables (CONFLUENCE_API_TOKEN, CONFLUENCE_EMAIL, etc.)
2. System keychain (via keyring library)
3. .claude/settings.local.json
"""

from __future__ import annotations

import threading
from typing import Any

from assistant_skills_lib import (
    BaseCredentialManager,
    CredentialBackend,
)
from assistant_skills_lib import (
    CredentialNotFoundError as BaseCredentialNotFoundError,
)

from .error_handler import AuthenticationError, ConfluenceError, ValidationError
from .validators import validate_email, validate_url


class CredentialNotFoundError(ConfluenceError):
    """Raised when credentials cannot be found in any backend."""

    def __init__(self, hint: str | None = None, **kwargs: Any):
        message = "No Confluence credentials found"
        if hint:
            message = message + "\n\n" + hint
        super().__init__(message, **kwargs)


class ConfluenceCredentialManager(BaseCredentialManager):
    """
    Credential manager for Confluence Assistant Skills.

    Handles secure storage and retrieval of Confluence credentials including:
    - Site URL
    - Email address
    - API token

    Example usage:
        from confluence_assistant_skills_lib import ConfluenceCredentialManager

        # Get credentials
        manager = ConfluenceCredentialManager()
        creds = manager.get_credentials()

        # Store credentials
        manager.store_credentials({
            "site_url": "https://your-site.atlassian.net",
            "email": "your-email@example.com",
            "api_token": "your-api-token"
        })
    """

    def get_service_name(self) -> str:
        """Return the keychain service name."""
        return "confluence-assistant"

    def get_env_prefix(self) -> str:
        """Return the environment variable prefix."""
        return "CONFLUENCE"

    def get_credential_fields(self) -> list[str]:
        """Return list of credential field names.

        Required fields:
        - site_url: Confluence Cloud URL
        - email: Email address for authentication
        - api_token: API token for authentication
        """
        return ["site_url", "email", "api_token"]

    def get_credential_not_found_hint(self) -> str:
        """Return help text for credential not found error."""
        return """To configure Confluence credentials, set environment variables:

  export CONFLUENCE_SITE_URL='https://your-site.atlassian.net'
  export CONFLUENCE_EMAIL='your-email@example.com'
  export CONFLUENCE_API_TOKEN='your-api-token'

Get an API token at:
  https://id.atlassian.com/manage-profile/security/api-tokens

Or store credentials securely:
  from confluence_assistant_skills_lib import ConfluenceCredentialManager
  manager = ConfluenceCredentialManager()
  manager.store_credentials({
      "site_url": "https://your-site.atlassian.net",
      "email": "your-email@example.com",
      "api_token": "your-api-token"
  })
"""

    def validate_credentials(self, credentials: dict[str, str]) -> dict[str, Any]:
        """
        Validate credentials by making a test API call.

        Args:
            credentials: Dictionary of credential values

        Returns:
            User info on success

        Raises:
            ValidationError: If required fields are missing
            AuthenticationError: If credentials are invalid
        """
        import requests

        from .error_handler import sanitize_error_message

        site_url = credentials.get("site_url", "")
        email = credentials.get("email", "")
        api_token = credentials.get("api_token", "")

        # Validate required fields
        if not site_url:
            raise ValidationError(
                "site_url is required",
                operation="validate_credentials",
            )
        if not email:
            raise ValidationError(
                "email is required",
                operation="validate_credentials",
            )
        if not api_token:
            raise ValidationError(
                "api_token is required",
                operation="validate_credentials",
            )

        # Validate formats
        site_url = validate_url(site_url, require_https=True)
        email = validate_email(email)

        # Test with /wiki/api/v2/users/current endpoint
        test_url = f"{site_url}/wiki/api/v2/users/current"

        try:
            response = requests.get(
                test_url,
                auth=(email, api_token),
                headers={"Accept": "application/json"},
                timeout=10,
            )

            if response.status_code == 401:
                raise AuthenticationError(
                    "Invalid credentials. Please check your email and API token."
                )
            elif response.status_code == 403:
                raise AuthenticationError(
                    "Access forbidden. Your API token may lack required permissions."
                )
            elif not response.ok:
                raise ConfluenceError(
                    f"Connection failed with status {response.status_code}",
                    status_code=response.status_code,
                )

            return response.json()

        except requests.exceptions.ConnectionError:
            raise ConfluenceError(
                f"Cannot connect to {site_url}. Please check the URL and your network connection."
            ) from None
        except requests.exceptions.Timeout:
            raise ConfluenceError(
                f"Connection to {site_url} timed out. The server may be slow or unreachable."
            ) from None
        except requests.exceptions.RequestException as e:
            raise ConfluenceError(
                f"Connection error: {sanitize_error_message(str(e))}"
            ) from e

    def get_credentials_tuple(self) -> tuple[str, str, str]:
        """
        Retrieve credentials as a tuple (url, email, api_token).

        This provides backward compatibility with existing code.

        Returns:
            Tuple of (url, email, api_token)

        Raises:
            CredentialNotFoundError: If credentials not found in any backend
            ValidationError: If credentials are invalid
        """
        try:
            creds = self.get_credentials()
        except BaseCredentialNotFoundError:
            raise CredentialNotFoundError(
                hint=self.get_credential_not_found_hint()
            ) from None

        url = creds.get("site_url", "")
        email = creds.get("email", "")
        api_token = creds.get("api_token", "")

        # Validate credentials
        url = validate_url(url, require_https=True)
        email = validate_email(email)

        return url, email, api_token


# Singleton instance
_credential_manager: ConfluenceCredentialManager | None = None
_credential_manager_lock = threading.Lock()


def get_credential_manager() -> ConfluenceCredentialManager:
    """Get or create global ConfluenceCredentialManager instance.

    Thread-safe singleton access using double-checked locking pattern.
    """
    global _credential_manager
    if _credential_manager is None:
        with _credential_manager_lock:
            if _credential_manager is None:
                _credential_manager = ConfluenceCredentialManager()
    return _credential_manager


# Convenience functions (match JIRA credential_manager.py pattern)


def is_keychain_available() -> bool:
    """Check if system keychain is available."""
    return ConfluenceCredentialManager.is_keychain_available()


def get_credentials() -> tuple[str, str, str]:
    """
    Get Confluence credentials.

    Returns:
        Tuple of (url, email, api_token)

    Raises:
        CredentialNotFoundError: If credentials not found
    """
    manager = get_credential_manager()
    return manager.get_credentials_tuple()


def store_credentials(
    url: str,
    email: str,
    api_token: str,
    backend: CredentialBackend | None = None,
) -> CredentialBackend:
    """
    Store credentials using preferred backend.

    Args:
        url: Confluence site URL
        email: User email
        api_token: API token
        backend: Specific backend to use (default: auto-select)

    Returns:
        The backend where credentials were stored
    """
    manager = get_credential_manager()

    # Validate inputs
    validated_url = validate_url(url, require_https=True)
    validated_email = validate_email(email)

    if not api_token or not api_token.strip():
        raise ValidationError("API token cannot be empty")

    credentials = {
        "site_url": validated_url,
        "email": validated_email,
        "api_token": api_token,
    }

    return manager.store_credentials(credentials, backend)


def validate_credentials(url: str, email: str, api_token: str) -> dict[str, Any]:
    """
    Validate credentials by making a test API call.

    Args:
        url: Confluence site URL
        email: User email
        api_token: API token

    Returns:
        User info dict on success

    Raises:
        AuthenticationError: If credentials are invalid
        ConfluenceError: If connection fails
    """
    manager = get_credential_manager()
    credentials = {
        "site_url": url,
        "email": email,
        "api_token": api_token,
    }
    return manager.validate_credentials(credentials)


# Re-export CredentialBackend for convenience
__all__ = [
    "ConfluenceCredentialManager",
    "CredentialNotFoundError",
    "CredentialBackend",
    "get_credential_manager",
    "is_keychain_available",
    "get_credentials",
    "store_credentials",
    "validate_credentials",
]
