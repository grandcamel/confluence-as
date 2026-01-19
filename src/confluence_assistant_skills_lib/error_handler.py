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

    def __init__(
        self,
        message: str = "Authentication failed",
        **kwargs: Any,
    ):
        # Remove 'message' from kwargs if present to avoid duplicate argument
        kwargs.pop("message", None)
        hint = "\n\nTroubleshooting:\n"
        hint += "  1. Verify CONFLUENCE_API_TOKEN is set correctly\n"
        hint += "  2. Check that your email matches your Atlassian account\n"
        hint += "  3. Ensure the API token hasn't expired\n"
        hint += "  4. Get a new token at: https://id.atlassian.com/manage-profile/security/api-tokens"
        super().__init__(message + hint, **kwargs)


class PermissionError(BasePermissionError, ConfluenceError):
    """Raised when user lacks permission (403)."""

    def __init__(
        self,
        message: str = "Permission denied",
        **kwargs: Any,
    ):
        # Remove 'message' from kwargs if present to avoid duplicate argument
        kwargs.pop("message", None)
        hint = "\n\nTroubleshooting:\n"
        hint += "  1. Check your Confluence space permissions\n"
        hint += "  2. Verify you have the required role (e.g., Editor, Admin)\n"
        hint += "  3. Contact your Confluence administrator if access is needed"
        super().__init__(message + hint, **kwargs)


class ValidationError(BaseValidationError, ConfluenceError):
    """Raised for invalid input or bad requests (400)."""

    def __init__(
        self,
        message: str = "Validation failed",
        field: Optional[str] = None,
        **kwargs: Any,
    ):
        # Remove 'message' from kwargs if present to avoid duplicate argument
        kwargs.pop("message", None)
        self.field = field
        if field:
            message = f"{message} (field: {field})"
        super().__init__(message, **kwargs)


class NotFoundError(BaseNotFoundError, ConfluenceError):
    """Raised when resource is not found (404)."""

    def __init__(
        self,
        message: str = "Resource not found",
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        **kwargs: Any,
    ):
        # Remove 'message' from kwargs if present to avoid duplicate argument
        kwargs.pop("message", None)
        if resource_type and resource_id:
            message = f"{resource_type} '{resource_id}' not found"
        elif resource_type:
            message = f"{resource_type} not found"
        super().__init__(message, **kwargs)


class RateLimitError(BaseRateLimitError, ConfluenceError):
    """Raised when rate limit is exceeded (429)."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None,
        **kwargs: Any,
    ):
        # Remove 'message' from kwargs if present to avoid duplicate argument
        kwargs.pop("message", None)
        if retry_after:
            message = f"{message}. Retry after {retry_after} seconds"
        else:
            message = f"{message}. Please wait before retrying"
        super().__init__(message, retry_after=retry_after, **kwargs)


class ConflictError(BaseConflictError, ConfluenceError):
    """Raised on resource conflicts (409)."""

    def __init__(
        self,
        message: str = "Resource conflict",
        **kwargs: Any,
    ):
        # Remove 'message' from kwargs if present to avoid duplicate argument
        kwargs.pop("message", None)
        hint = "\n\nThis usually means the resource was modified by another user."
        hint += "\nTry refreshing and applying your changes again."
        super().__init__(message + hint, **kwargs)


class ServerError(BaseServerError, ConfluenceError):
    """Raised for server-side errors (5xx)."""

    def __init__(
        self,
        message: str = "Confluence server error",
        **kwargs: Any,
    ):
        # Remove 'message' from kwargs if present to avoid duplicate argument
        kwargs.pop("message", None)
        hint = "\n\nThe Confluence server encountered an error. Please try again later."
        super().__init__(message + hint, **kwargs)


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

    base_kwargs: dict[str, Any] = {
        "status_code": status_code,
        "response_data": response.text,
        "operation": operation,
    }

    if status_code == 400:
        raise ValidationError(message, **base_kwargs)
    elif status_code == 401:
        raise AuthenticationError(
            "Authentication failed. Check your email and API token.",
            **base_kwargs,
        )
    elif status_code == 403:
        raise PermissionError(f"Permission denied: {message}", **base_kwargs)
    elif status_code == 404:
        raise NotFoundError(message, **base_kwargs)
    elif status_code == 409:
        raise ConflictError(message, **base_kwargs)
    elif status_code == 429:
        retry_after_str = response.headers.get("Retry-After")
        retry_after = (
            int(retry_after_str)
            if retry_after_str and retry_after_str.isdigit()
            else None
        )
        raise RateLimitError(
            f"Rate limit exceeded. Retry after {retry_after or 'unknown'} seconds.",
            retry_after=retry_after,
            **base_kwargs,
        )
    elif 500 <= status_code < 600:
        raise ServerError(f"Confluence server error: {message}", **base_kwargs)
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
