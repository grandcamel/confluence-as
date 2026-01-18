"""
Error Handling for Confluence Assistant Skills

Provides a Confluence-specific exception hierarchy that builds upon the base
error handler from assistant_skills_lib.
"""

import functools
import sys
from typing import Any, Callable, Literal, Optional

import requests
from assistant_skills_lib.error_handler import (
    AuthenticationError as BaseAuthenticationError,
)
from assistant_skills_lib.error_handler import (
    BaseAPIError,
)
from assistant_skills_lib.error_handler import (
    ConflictError as BaseConflictError,
)
from assistant_skills_lib.error_handler import (
    NotFoundError as BaseNotFoundError,
)
from assistant_skills_lib.error_handler import (
    PermissionError as BasePermissionError,
)
from assistant_skills_lib.error_handler import (
    RateLimitError as BaseRateLimitError,
)
from assistant_skills_lib.error_handler import (
    ServerError as BaseServerError,
)
from assistant_skills_lib.error_handler import (
    ValidationError as BaseValidationError,
)
from assistant_skills_lib.error_handler import (
    handle_errors as base_handle_errors,
)
from assistant_skills_lib.error_handler import (
    print_error as base_print_error,
)
from assistant_skills_lib.error_handler import (
    sanitize_error_message as base_sanitize_error_message,
)


class ConfluenceError(BaseAPIError):
    """Base exception for all Confluence-related errors."""

    pass


class AuthenticationError(BaseAuthenticationError, ConfluenceError):
    """Raised when authentication fails (401)."""

    pass


class PermissionError(BasePermissionError, ConfluenceError):
    """Raised when user lacks permission (403)."""

    pass


class ValidationError(BaseValidationError, ConfluenceError):
    """Raised for invalid input or bad requests (400)."""

    pass


class NotFoundError(BaseNotFoundError, ConfluenceError):
    """Raised when resource is not found (404)."""

    pass


class RateLimitError(BaseRateLimitError, ConfluenceError):
    """Raised when rate limit is exceeded (429)."""

    pass


class ConflictError(BaseConflictError, ConfluenceError):
    """Raised on resource conflicts (409)."""

    pass


class ServerError(BaseServerError, ConfluenceError):
    """Raised for server-side errors (5xx)."""

    pass


def sanitize_error_message(message: str) -> str:
    """
    Sanitize error messages by calling the base sanitizer.
    Confluence does not require extra specific sanitization beyond the base.
    """
    return base_sanitize_error_message(message)


def extract_error_message(response: requests.Response) -> str:
    """
    Extract a meaningful error message from a Confluence API response.
    """
    try:
        data = response.json()
        if "errors" in data and isinstance(data["errors"], list) and data["errors"]:
            error = data["errors"][0]
            return error.get("title", error.get("detail", str(error)))
        if "message" in data:
            return data["message"]
        if "errorMessage" in data:
            return data["errorMessage"]
        return str(data)
    except (ValueError, KeyError):
        return response.text[:500] if response.text else f"HTTP {response.status_code}"


def handle_confluence_error(
    response: requests.Response,
    operation: str = "API request",
) -> None:
    """
    Handle an error response from the Confluence API, raising a canonical exception.
    """
    status_code = response.status_code
    message = extract_error_message(response)
    message = sanitize_error_message(message)

    base_kwargs = {
        "status_code": status_code,
        "response_data": response.text,
        "operation": operation,
    }

    if status_code == 400:
        raise ValidationError(message=message, **base_kwargs)
    elif status_code == 401:
        raise AuthenticationError(
            message="Authentication failed. Check your email and API token.",
            **base_kwargs,
        )
    elif status_code == 403:
        raise PermissionError(message=f"Permission denied: {message}", **base_kwargs)
    elif status_code == 404:
        raise NotFoundError(message=message, **base_kwargs)
    elif status_code == 409:
        raise ConflictError(message=message, **base_kwargs)
    elif status_code == 429:
        retry_after_str = response.headers.get("Retry-After")
        retry_after = (
            int(retry_after_str)
            if retry_after_str and retry_after_str.isdigit()
            else None
        )
        raise RateLimitError(
            message=f"Rate limit exceeded. Retry after {retry_after or 'unknown'} seconds.",
            retry_after=retry_after,
            **base_kwargs,
        )
    elif 500 <= status_code < 600:
        raise ServerError(message=f"Confluence server error: {message}", **base_kwargs)
    else:
        raise ConfluenceError(message=message, **base_kwargs)


def print_error(
    message: str,
    error: Optional[Exception] = None,
    suggestion: Optional[str] = None,
    show_traceback: bool = False,
) -> None:
    """
    Print a formatted error message to stderr using the base printer.
    """
    extra_hints = {
        AuthenticationError: "Check CONFLUENCE_EMAIL and CONFLUENCE_API_TOKEN. Token URL: https://id.atlassian.com/manage-profile/security/api-tokens"
    }
    base_print_error(message, error, suggestion, show_traceback, extra_hints)


def handle_errors(func: Callable) -> Callable:
    """
    Decorator to handle errors in main functions.
    This wraps the base decorator to catch Confluence-specific errors first.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        try:
            return func(*args, **kwargs)
        except ConfluenceError as e:
            print_error("Confluence API Error", e)
            sys.exit(1)
        # Let the base handler catch everything else

    return base_handle_errors(wrapper)


class ErrorContext:
    """
    Context manager for error handling with custom messages.
    """

    def __init__(self, operation: str, **context: Any):
        self.operation = operation
        self.context = context

    def __enter__(self) -> "ErrorContext":
        return self

    def __exit__(
        self, exc_type: Optional[type], exc_val: Optional[BaseAPIError], exc_tb: Any
    ) -> Literal[False]:
        if (
            exc_type is not None
            and exc_val is not None
            and issubclass(exc_type, BaseAPIError)
        ):
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            exc_val.operation = (
                f"{self.operation} ({context_str})" if context_str else self.operation
            )
        return False
