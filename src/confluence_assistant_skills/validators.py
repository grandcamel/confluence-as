"""
Input Validators for Confluence Assistant Skills
"""

import re
from pathlib import Path
from typing import Optional, Union, List

# Import ValidationError from local error_handler for Confluence-specific errors
from .error_handler import ValidationError
from assistant_skills_lib.validators import (
    validate_required,
    validate_path as base_validate_path,
    validate_url as base_validate_url,
    validate_email as base_validate_email,
    validate_int,
)


def validate_page_id(page_id: Union[str, int], field_name: str = "page_id") -> str:
    """
    Validate a Confluence page ID.
    """
    page_id_str = validate_required(str(page_id), field_name)
    if not page_id_str.isdigit():
        raise ValidationError(
            f"{field_name} must be a numeric string (got: {page_id_str})",
            operation="validation", details={"field": field_name, "value": page_id_str}
        )
    return page_id_str


def validate_space_key(
    space_key: str,
    field_name: str = "space_key",
    allow_lowercase: bool = True,
) -> str:
    """
    Validate a Confluence space key.
    """
    space_key = validate_required(space_key, field_name)

    if len(space_key) < 2 or len(space_key) > 255:
        raise ValidationError(
            f"{field_name} must be between 2 and 255 characters",
            operation="validation", details={"field": field_name, "value": space_key}
        )
    if not re.match(r'^[A-Za-z][A-Za-z0-9_]*$', space_key):
        raise ValidationError(
            f"{field_name} must start with a letter and contain only letters, numbers, and underscores",
            operation="validation", details={"field": field_name, "value": space_key}
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
    if query.count('"') % 2 != 0 or query.count("'") % 2 != 0 or query.count('(') != query.count(')'):
        raise ValidationError(
            f"{field_name} has unbalanced quotes or parentheses",
            operation="validation",
            details={"field": field_name, "value": query}
        )


def validate_cql(cql: str, field_name: str = "cql") -> str:
    """
    Basic validation for a CQL query.
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
    """
    if allowed is None:
        allowed = ['page', 'blogpost', 'comment', 'attachment']
    content_type = validate_required(content_type, field_name).lower()
    if content_type not in allowed:
        raise ValidationError(
            f"{field_name} must be one of: {', '.join(allowed)} (got: {content_type})",
            operation="validation", details={"field": field_name, "value": content_type}
        )
    return content_type


def validate_title(
    title: str,
    field_name: str = "title",
    max_length: int = 255,
) -> str:
    """
    Validate a page or content title.
    """
    title = validate_required(title, field_name)
    if len(title) > max_length:
        raise ValidationError(
            f"{field_name} must be at most {max_length} characters (got {len(title)})",
            operation="validation", details={"field": field_name, "value": title}
        )
    invalid_chars = [':', '|', '@', '/', '\\']
    for char in invalid_chars:
        if char in title:
            raise ValidationError(
                f"{field_name} cannot contain the character '{char}'",
                operation="validation", details={"field": field_name, "value": title}
            )
    return title


def validate_label(
    label: str,
    field_name: str = "label",
) -> str:
    """
    Validate a Confluence label.
    """
    label = validate_required(label, field_name).lower()
    if len(label) > 255:
        raise ValidationError(
            f"{field_name} must be at most 255 characters",
            operation="validation", details={"field": field_name, "value": label}
        )
    if ' ' in label:
        raise ValidationError(
            f"{field_name} cannot contain spaces (use hyphens or underscores)",
            operation="validation", details={"field": field_name, "value": label}
        )
    if not re.match(r'^[a-z0-9_-]+$', label):
        raise ValidationError(
            f"{field_name} can only contain letters, numbers, hyphens, and underscores",
            operation="validation", details={"field": field_name, "value": label}
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
    """
    issue_key = validate_required(issue_key, field_name).upper()
    pattern = r'^[A-Z][A-Z0-9_]{0,9}-\d+$'
    if not re.match(pattern, issue_key):
        raise ValidationError(
            f"{field_name} must be in format PROJECT-123 (got: {issue_key})",
            operation="validation", details={"field": field_name, "value": issue_key}
        )
    return issue_key


def validate_jql_query(
    jql: str,
    field_name: str = "jql",
) -> str:
    """
    Basic validation for a JQL query.
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
    allowed_extensions: Optional[List[str]] = None,
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
    # Use base validator with file-focused defaults
    resolved = base_validate_path(
        path,
        field_name=field_name,
        must_exist=must_exist,
        must_be_file=must_exist,  # Only check if file when it must exist
    )

    # Check allowed extensions if specified
    if allowed_extensions:
        ext = resolved.suffix.lower()
        allowed_lower = [e.lower() for e in allowed_extensions]
        if ext not in allowed_lower:
            raise ValidationError(
                f"{field_name} must have one of these extensions: {', '.join(allowed_extensions)} (got: {ext})",
                operation="validation",
                details={"field": field_name, "value": str(resolved), "allowed_extensions": allowed_extensions}
            )

    return resolved
