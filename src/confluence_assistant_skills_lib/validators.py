"""
Input Validators for Confluence Assistant Skills
"""

import re
from pathlib import Path
from typing import Any, Optional, Union

from assistant_skills_lib.error_handler import (
    ValidationError as BaseValidationError,
)
from assistant_skills_lib.validators import (
    validate_email as base_validate_email,
)
from assistant_skills_lib.validators import (
    validate_int as base_validate_int,
)
from assistant_skills_lib.validators import (
    validate_path as base_validate_path,
)
from assistant_skills_lib.validators import (
    validate_required as base_validate_required,
)
from assistant_skills_lib.validators import (
    validate_url as base_validate_url,
)

# Import ValidationError from local error_handler for Confluence-specific errors
from .error_handler import ValidationError


def validate_required(value: Optional[Any], field_name: str = "value") -> str:
    """
    Validate that a value is provided and not empty.
    Wraps base validator to raise Confluence-specific ValidationError.
    """
    try:
        return base_validate_required(value, field_name)
    except BaseValidationError as e:
        raise ValidationError(
            str(e),
            operation="validation",
            details={"field": field_name},
        ) from e


def validate_int(
    value: Any,
    field_name: str = "value",
    min_value: Optional[int] = None,
    max_value: Optional[int] = None,
    allow_none: bool = False,
) -> int:
    """
    Validate an integer value with optional range constraints.
    Wraps base validator to raise Confluence-specific ValidationError.
    """
    try:
        return base_validate_int(value, field_name, min_value, max_value, allow_none)
    except BaseValidationError as e:
        raise ValidationError(
            str(e),
            operation="validation",
            details={"field": field_name},
        ) from e


def validate_page_id(page_id: Union[str, int], field_name: str = "page_id") -> str:
    """
    Validate a Confluence page ID.

    Page IDs in Confluence are always numeric strings. This function accepts
    both string and integer inputs and returns a validated string.

    Args:
        page_id: The page ID to validate (string or integer).
        field_name: Name of the field for error messages.

    Returns:
        Validated page ID as a string.

    Raises:
        ValidationError: If page_id is empty or not numeric.
    """
    page_id_str = validate_required(str(page_id), field_name)
    if not page_id_str.isdigit():
        raise ValidationError(
            f"{field_name} must be a numeric string (got: {page_id_str})",
            operation="validation",
            details={"field": field_name, "value": page_id_str},
        )
    return page_id_str


def validate_space_key(
    space_key: str,
    field_name: str = "space_key",
    allow_lowercase: bool = True,
) -> str:
    """
    Validate a Confluence space key.

    Space keys must be 2-255 characters, start with a letter, and contain
    only letters, numbers, and underscores. By default, the returned key
    is uppercased.

    Args:
        space_key: The space key to validate.
        field_name: Name of the field for error messages.
        allow_lowercase: If True (default), accept lowercase input and
            return uppercase. If False, return as-is.

    Returns:
        Validated space key (uppercase by default).

    Raises:
        ValidationError: If space_key is empty, wrong length, or contains
            invalid characters.
    """
    space_key = validate_required(space_key, field_name)

    if len(space_key) < 2 or len(space_key) > 255:
        raise ValidationError(
            f"{field_name} must be between 2 and 255 characters",
            operation="validation",
            details={"field": field_name, "value": space_key},
        )
    if not re.match(r"^[A-Za-z][A-Za-z0-9_]*$", space_key):
        raise ValidationError(
            f"{field_name} must start with a letter and contain only letters, numbers, and underscores",
            operation="validation",
            details={"field": field_name, "value": space_key},
        )
    return space_key.upper() if allow_lowercase else space_key


def _validate_balanced_syntax(query: str, field_name: str) -> None:
    """
    Validate balanced quotes and parentheses in query strings.

    Args:
        query: The query string to validate
        field_name: Name of the field for error messages

    Raises:
        ValidationError: If quotes or parentheses are unbalanced
    """
    if (
        query.count('"') % 2 != 0
        or query.count("'") % 2 != 0
        or query.count("(") != query.count(")")
    ):
        raise ValidationError(
            f"{field_name} has unbalanced quotes or parentheses",
            operation="validation",
            details={"field": field_name, "value": query},
        )


def validate_cql(cql: str, field_name: str = "cql") -> str:
    """
    Validate a CQL (Confluence Query Language) query.

    Performs basic syntax validation including checking for balanced
    quotes and parentheses. Does not validate CQL semantics.

    Args:
        cql: The CQL query string to validate.
        field_name: Name of the field for error messages.

    Returns:
        The validated CQL query string.

    Raises:
        ValidationError: If cql is empty or has unbalanced quotes/parentheses.
    """
    cql = validate_required(cql, field_name)
    _validate_balanced_syntax(cql, field_name)
    return cql


def validate_content_type(
    content_type: str,
    field_name: str = "content_type",
    allowed: Optional[list] = None,
) -> str:
    """
    Validate a Confluence content type.

    By default, valid content types are: page, blogpost, comment, attachment.
    Custom allowed types can be provided.

    Args:
        content_type: The content type to validate.
        field_name: Name of the field for error messages.
        allowed: List of allowed content types. Defaults to
            ['page', 'blogpost', 'comment', 'attachment'].

    Returns:
        Validated content type (lowercase).

    Raises:
        ValidationError: If content_type is empty or not in allowed list.
    """
    if allowed is None:
        allowed = ["page", "blogpost", "comment", "attachment"]
    content_type = validate_required(content_type, field_name).lower()
    if content_type not in allowed:
        raise ValidationError(
            f"{field_name} must be one of: {', '.join(allowed)} (got: {content_type})",
            operation="validation",
            details={"field": field_name, "value": content_type},
        )
    return content_type


def validate_title(
    title: str,
    field_name: str = "title",
    max_length: int = 255,
) -> str:
    """
    Validate a Confluence page or content title.

    Titles cannot contain certain special characters that are reserved
    by Confluence: colon (:), pipe (|), at sign (@), forward slash (/),
    and backslash (\\).

    Args:
        title: The title to validate.
        field_name: Name of the field for error messages.
        max_length: Maximum allowed length (default 255).

    Returns:
        The validated title string.

    Raises:
        ValidationError: If title is empty, too long, or contains
            invalid characters.
    """
    title = validate_required(title, field_name)
    if len(title) > max_length:
        raise ValidationError(
            f"{field_name} must be at most {max_length} characters (got {len(title)})",
            operation="validation",
            details={"field": field_name, "value": title},
        )
    invalid_chars = [":", "|", "@", "/", "\\"]
    for char in invalid_chars:
        if char in title:
            raise ValidationError(
                f"{field_name} cannot contain the character '{char}'",
                operation="validation",
                details={"field": field_name, "value": title},
            )
    return title


def validate_label(
    label: str,
    field_name: str = "label",
) -> str:
    """
    Validate a Confluence label.

    Labels must be lowercase, contain no spaces, and use only alphanumeric
    characters, hyphens, and underscores. Maximum length is 255 characters.

    Args:
        label: The label to validate.
        field_name: Name of the field for error messages.

    Returns:
        Validated label (lowercase).

    Raises:
        ValidationError: If label is empty, too long, contains spaces,
            or has invalid characters.
    """
    label = validate_required(label, field_name).lower()
    if len(label) > 255:
        raise ValidationError(
            f"{field_name} must be at most 255 characters",
            operation="validation",
            details={"field": field_name, "value": label},
        )
    if " " in label:
        raise ValidationError(
            f"{field_name} cannot contain spaces (use hyphens or underscores)",
            operation="validation",
            details={"field": field_name, "value": label},
        )
    if not re.match(r"^[a-z0-9_-]+$", label):
        raise ValidationError(
            f"{field_name} can only contain letters, numbers, hyphens, and underscores",
            operation="validation",
            details={"field": field_name, "value": label},
        )
    return label


def validate_limit(
    limit: Union[str, int, None],
    field_name: str = "limit",
    min_value: int = 1,
    max_value: int = 250,
    default: int = 25,
) -> int:
    """
    Validate a pagination limit.

    Args:
        limit: The limit value to validate (can be None for default)
        field_name: Name of the field for error messages
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        default: Default value to use when limit is None

    Returns:
        Validated limit as integer
    """
    if limit is None:
        return default
    return validate_int(limit, field_name, min_value, max_value, allow_none=False)


# Atlassian-shared validators (Jira & Confluence)
def validate_issue_key(
    issue_key: str,
    field_name: str = "issue_key",
) -> str:
    """
    Validate a JIRA issue key.

    Issue keys follow the format PROJECT-123 where PROJECT is 1-10 uppercase
    letters/numbers (starting with a letter) followed by a hyphen and a number.

    Args:
        issue_key: The issue key to validate (e.g., "PROJ-123").
        field_name: Name of the field for error messages.

    Returns:
        Validated issue key (uppercase).

    Raises:
        ValidationError: If issue_key is empty or doesn't match the format.
    """
    issue_key = validate_required(issue_key, field_name).upper()
    pattern = r"^[A-Z][A-Z0-9_]{0,9}-\d+$"
    if not re.match(pattern, issue_key):
        raise ValidationError(
            f"{field_name} must be in format PROJECT-123 (got: {issue_key})",
            operation="validation",
            details={"field": field_name, "value": issue_key},
        )
    return issue_key


def validate_jql_query(
    jql: str,
    field_name: str = "jql",
) -> str:
    """
    Validate a JQL (JIRA Query Language) query.

    Performs basic syntax validation including checking for balanced
    quotes and parentheses. Does not validate JQL semantics.

    Args:
        jql: The JQL query string to validate.
        field_name: Name of the field for error messages.

    Returns:
        The validated JQL query string.

    Raises:
        ValidationError: If jql is empty or has unbalanced quotes/parentheses.
    """
    jql = validate_required(jql, field_name)
    _validate_balanced_syntax(jql, field_name)
    return jql


# Aliases to base validators
validate_url = base_validate_url
validate_email = base_validate_email


def validate_file_path(
    path: Union[str, Path],
    field_name: str = "file_path",
    allowed_extensions: Optional[list[str]] = None,
    must_exist: bool = True,
) -> Path:
    """
    Validate a file path for Confluence operations (attachments, etc.).

    By default, requires the path to exist and be a file (for uploads).
    Use must_exist=False for output paths where the file will be created.

    Args:
        path: Path to validate
        field_name: Name of the field for error messages
        allowed_extensions: List of allowed file extensions (e.g., ['.pdf', '.txt'])
        must_exist: If True (default), require the file to exist

    Returns:
        Resolved Path object

    Raises:
        ValidationError: If path doesn't exist (when must_exist=True),
                        is not a file (when it exists), or has disallowed extension
    """
    # Use base validator with file-focused defaults, wrap exceptions
    try:
        resolved = base_validate_path(
            path,
            field_name=field_name,
            must_exist=must_exist,
            must_be_file=must_exist,  # Only check if file when it must exist
        )
    except BaseValidationError as e:
        raise ValidationError(
            str(e),
            operation="validation",
            details={"field": field_name, "value": str(path)},
        ) from e

    # Check allowed extensions if specified
    if allowed_extensions:
        ext = resolved.suffix.lower()
        allowed_lower = [e.lower() for e in allowed_extensions]
        if ext not in allowed_lower:
            raise ValidationError(
                f"{field_name} must have one of these extensions: {', '.join(allowed_extensions)} (got: {ext})",
                operation="validation",
                details={
                    "field": field_name,
                    "value": str(resolved),
                    "allowed_extensions": allowed_extensions,
                },
            )

    return resolved
