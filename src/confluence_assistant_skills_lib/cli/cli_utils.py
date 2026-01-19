"""CLI utility functions for Confluence Assistant Skills.

Provides common patterns for Click commands:
- Client context management
- Parsing utilities (comma-separated lists, JSON)
- Error handling decorator
- Output formatting helpers
- Validators for Click callbacks
"""

from __future__ import annotations

import functools
import json
import sys
from typing import TYPE_CHECKING, Any, Callable, TypeVar, cast

import click

from confluence_assistant_skills_lib import (
    AuthenticationError,
    ConflictError,
    ConfluenceError,
    NotFoundError,
    PermissionError,
    RateLimitError,
    ServerError,
    ValidationError,
    get_confluence_client,
    print_error,
)

if TYPE_CHECKING:
    from confluence_assistant_skills_lib import ConfluenceClient

F = TypeVar("F", bound=Callable[..., Any])


def get_client_from_context(ctx: click.Context) -> ConfluenceClient:
    """Get or create a shared ConfluenceClient from the Click context.

    This provides a single client instance shared across all commands in a CLI
    invocation, improving performance and testability.

    Args:
        ctx: Click context object

    Returns:
        Shared ConfluenceClient instance
    """
    ctx.ensure_object(dict)
    if ctx.obj.get("_client") is None:
        ctx.obj["_client"] = get_confluence_client()
    return cast("ConfluenceClient", ctx.obj["_client"])


def handle_cli_errors(func: F) -> F:
    """Decorator to handle exceptions in CLI commands.

    Catches ConfluenceError exceptions and prints user-friendly error messages,
    then exits with appropriate exit codes.

    Exit codes:
        1 - Validation error or generic error
        2 - Authentication error
        3 - Permission denied
        4 - Resource not found
        5 - Rate limit exceeded
        6 - Conflict error
        7 - Server error
        130 - User interrupt (Ctrl+C)
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except ValidationError as e:
            print_error(f"Validation error: {e}")
            sys.exit(1)
        except AuthenticationError as e:
            print_error(f"Authentication failed: {e}")
            sys.exit(2)
        except PermissionError as e:
            print_error(f"Permission denied: {e}")
            sys.exit(3)
        except NotFoundError as e:
            print_error(f"Not found: {e}")
            sys.exit(4)
        except RateLimitError as e:
            print_error(f"Rate limit exceeded: {e}")
            sys.exit(5)
        except ConflictError as e:
            print_error(f"Conflict: {e}")
            sys.exit(6)
        except ServerError as e:
            print_error(f"Server error: {e}")
            sys.exit(7)
        except ConfluenceError as e:
            print_error(f"Confluence error: {e}")
            sys.exit(1)
        except KeyboardInterrupt:
            print_error("Interrupted by user")
            sys.exit(130)
        except Exception as e:
            print_error(f"Unexpected error: {e}")
            sys.exit(1)

    return wrapper  # type: ignore[return-value]


def parse_comma_list(value: str | None) -> list[str] | None:
    """Parse a comma-separated string into a list.

    Args:
        value: Comma-separated string or None

    Returns:
        List of stripped strings, or None if input was None/empty

    Example:
        parse_comma_list("a, b, c") -> ["a", "b", "c"]
        parse_comma_list(None) -> None
    """
    if not value or not value.strip():
        return None
    result = [item.strip() for item in value.split(",") if item.strip()]
    return result if result else None


# Maximum JSON input size (1 MB) to prevent DoS via large payloads
MAX_JSON_SIZE = 1024 * 1024


def parse_json_arg(
    value: str | None, max_size: int = MAX_JSON_SIZE
) -> dict[str, Any] | None:
    """Parse a JSON string argument with size limit.

    Args:
        value: JSON string or None
        max_size: Maximum allowed JSON size in bytes (default 1 MB)

    Returns:
        Parsed dict, or None if input was None/empty

    Raises:
        click.BadParameter: If JSON parsing fails or size exceeds limit
    """
    if not value:
        return None
    if len(value) > max_size:
        raise click.BadParameter(
            f"JSON too large ({len(value):,} bytes, max {max_size:,} bytes)"
        )
    try:
        return cast(dict[str, Any], json.loads(value))
    except json.JSONDecodeError as e:
        raise click.BadParameter(f"Invalid JSON: {e}") from e


def validate_positive_int(
    ctx: click.Context, param: click.Parameter, value: int | None
) -> int | None:
    """Click callback to validate positive integers.

    Args:
        ctx: Click context
        param: Click parameter
        value: Integer value to validate

    Returns:
        Validated integer or None

    Raises:
        click.BadParameter: If value is not positive
    """
    if value is not None and value <= 0:
        raise click.BadParameter("must be a positive integer")
    return value


def validate_non_negative_int(
    ctx: click.Context, param: click.Parameter, value: int | None
) -> int | None:
    """Click callback to validate non-negative integers.

    Args:
        ctx: Click context
        param: Click parameter
        value: Integer value to validate

    Returns:
        Validated integer or None

    Raises:
        click.BadParameter: If value is negative
    """
    if value is not None and value < 0:
        raise click.BadParameter("must be a non-negative integer")
    return value


def get_output_format(ctx: click.Context, explicit_output: str | None = None) -> str:
    """Get output format from explicit option or context.

    Args:
        ctx: Click context
        explicit_output: Explicitly specified output format

    Returns:
        Output format string ("text" or "json")
    """
    if explicit_output:
        return explicit_output
    return ctx.obj.get("output", "text") if ctx.obj else "text"


def output_results(
    data: Any,
    output_format: str = "text",
    columns: list[str] | None = None,
    success_msg: str | None = None,
) -> None:
    """Output results in the specified format.

    Args:
        data: Results to output (list of dicts, dict, or string)
        output_format: One of "json", "text"
        columns: Column names for table output
        success_msg: Optional success message for text output
    """
    from confluence_assistant_skills_lib import format_json, format_table, print_success

    if output_format == "json":
        click.echo(format_json(data))
    else:
        if isinstance(data, list) and data:
            click.echo(format_table(data, columns=columns))
        elif isinstance(data, dict):
            click.echo(format_json(data))
        elif data:
            click.echo(data)
        if success_msg:
            print_success(success_msg)


def format_json_output(data: Any) -> str:
    """Format data as pretty-printed JSON.

    Args:
        data: Data to format

    Returns:
        JSON string with 2-space indentation
    """
    return json.dumps(data, indent=2, default=str)


# Alias for convenience
format_json = format_json_output


def with_date_range(func: F) -> F:
    """Decorator to add standard date range options to a Click command.

    Adds --start-date and --end-date options to the decorated command.
    These options accept ISO format dates (YYYY-MM-DD).

    Example:
        @content.command()
        @click.argument("space_key")
        @with_date_range
        @click.pass_context
        def search(ctx, space_key, start_date, end_date):
            ...
    """
    func = click.option(
        "--end-date",
        default=None,
        help="End date filter (YYYY-MM-DD format)",
    )(func)
    func = click.option(
        "--start-date",
        default=None,
        help="Start date filter (YYYY-MM-DD format)",
    )(func)
    return func


def validate_page_id_callback(
    ctx: click.Context, param: click.Parameter, value: str
) -> str:
    """Click callback to validate page ID parameter.

    Use this as a callback on Click arguments/options that accept a page ID.

    Args:
        ctx: Click context
        param: Click parameter
        value: Page ID value to validate

    Returns:
        Validated page ID

    Raises:
        click.BadParameter: If page ID is invalid
    """
    from confluence_assistant_skills_lib import validate_page_id

    try:
        return validate_page_id(value)
    except ValidationError as e:
        raise click.BadParameter(str(e)) from e


def validate_space_key_callback(
    ctx: click.Context, param: click.Parameter, value: str
) -> str:
    """Click callback to validate space key parameter.

    Use this as a callback on Click arguments/options that accept a space key.

    Args:
        ctx: Click context
        param: Click parameter
        value: Space key value to validate

    Returns:
        Validated space key

    Raises:
        click.BadParameter: If space key is invalid
    """
    from confluence_assistant_skills_lib import validate_space_key

    try:
        return validate_space_key(value)
    except ValidationError as e:
        raise click.BadParameter(str(e)) from e


__all__ = [
    "MAX_JSON_SIZE",
    "format_json",
    "format_json_output",
    "get_client_from_context",
    "get_output_format",
    "handle_cli_errors",
    "output_results",
    "parse_comma_list",
    "parse_json_arg",
    "validate_non_negative_int",
    "validate_page_id_callback",
    "validate_positive_int",
    "validate_space_key_callback",
    "with_date_range",
]
