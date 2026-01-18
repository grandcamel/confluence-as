"""
Confluence Assistant Skills Library

Python library for Confluence Cloud REST API - shared utilities for Confluence automation.

This module provides common utilities for all Confluence skills:
- ConfluenceClient: HTTP client with retry logic
- ConfigManager: Environment variable configuration
- Error handling: Exception hierarchy and decorators
- Validators: Input validation utilities
- Formatters: Output formatting utilities
- ADF Helper: Atlassian Document Format utilities
- XHTML Helper: Legacy storage format utilities
- Cache: Response caching

Required Environment Variables:
    CONFLUENCE_SITE_URL - Confluence Cloud URL (e.g., https://your-site.atlassian.net)
    CONFLUENCE_EMAIL - Email address for authentication
    CONFLUENCE_API_TOKEN - API token for authentication

Usage:
    from confluence_assistant_skills import (
        ConfluenceClient,
        get_confluence_client,
        handle_errors,
        ValidationError,
    )

    # Get a configured client (uses environment variables)
    client = get_confluence_client()

    # Or create directly
    client = ConfluenceClient(
        base_url="https://your-site.atlassian.net",
        email="your-email@example.com",
        api_token="your-api-token"
    )

    # Get a page
    page = client.get("/api/v2/pages/12345")
"""

__version__ = "0.3.0"

# Client
from .confluence_client import ConfluenceClient, create_client

# Config
from .config_manager import (
    ConfigManager,
    get_confluence_client,
)

# Errors
from .error_handler import (
    ConfluenceError,
    AuthenticationError,
    PermissionError,
    ValidationError,
    NotFoundError,
    RateLimitError,
    ConflictError,
    ServerError,
    handle_confluence_error,
    handle_errors,
    print_error,
    sanitize_error_message,
    extract_error_message,
    ErrorContext,
)

# Validators
from .validators import (
    validate_page_id,
    validate_space_key,
    validate_cql,
    validate_content_type,
    validate_file_path,
    validate_url,
    validate_email,
    validate_title,
    validate_label,
    validate_limit,
    validate_issue_key,
    validate_jql_query,
)

# Formatters
from .formatters import (
    Colors,
    format_page,
    format_blogpost,
    format_space,
    format_comment,
    format_comments,
    format_search_results,
    format_table,
    format_json,
    format_timestamp,
    format_attachment,
    format_label,
    format_version,
    export_csv,
    print_success,
    print_warning,
    print_info,
    truncate,
    strip_html_tags,
)

# Markdown Parser (shared)
from .markdown_parser import (
    parse_markdown,
    is_block_start,
)

# ADF Helper
from .adf_helper import (
    create_adf_doc,
    create_paragraph,
    create_text,
    create_heading,
    create_bullet_list,
    create_ordered_list,
    create_code_block,
    create_blockquote,
    create_rule,
    create_table,
    create_link,
    text_to_adf,
    markdown_to_adf,
    adf_to_text,
    adf_to_markdown,
    validate_adf,
    is_markdown_block_start,  # Re-exported alias for backward compatibility
)

# XHTML Helper
from .xhtml_helper import (
    xhtml_to_markdown,
    markdown_to_xhtml,
    xhtml_to_adf,
    adf_to_xhtml,
    extract_text_from_xhtml,
    wrap_in_storage_format,
    validate_xhtml,
)

# Cache (from base library)
from assistant_skills_lib.cache import (
    Cache,
    get_cache,
    cached,
    invalidate,
)

__all__ = [
    # Version
    "__version__",
    # Client
    "ConfluenceClient",
    "create_client",
    # Config
    "ConfigManager",
    "get_confluence_client",
    # Errors
    "ConfluenceError",
    "AuthenticationError",
    "PermissionError",
    "ValidationError",
    "NotFoundError",
    "RateLimitError",
    "ConflictError",
    "ServerError",
    "handle_confluence_error",
    "handle_errors",
    "print_error",
    "sanitize_error_message",
    "extract_error_message",
    "ErrorContext",
    # Validators
    "validate_page_id",
    "validate_space_key",
    "validate_cql",
    "validate_content_type",
    "validate_file_path",
    "validate_url",
    "validate_email",
    "validate_title",
    "validate_label",
    "validate_limit",
    "validate_issue_key",
    "validate_jql_query",
    # Formatters
    "Colors",
    "format_page",
    "format_blogpost",
    "format_space",
    "format_comment",
    "format_comments",
    "format_search_results",
    "format_table",
    "format_json",
    "format_timestamp",
    "format_attachment",
    "format_label",
    "format_version",
    "export_csv",
    "print_success",
    "print_warning",
    "print_info",
    "truncate",
    "strip_html_tags",
    # Markdown Parser
    "parse_markdown",
    "is_block_start",
    # ADF Helper
    "create_adf_doc",
    "create_paragraph",
    "create_text",
    "create_heading",
    "create_bullet_list",
    "create_ordered_list",
    "create_code_block",
    "create_blockquote",
    "create_rule",
    "create_table",
    "create_link",
    "text_to_adf",
    "markdown_to_adf",
    "adf_to_text",
    "adf_to_markdown",
    "validate_adf",
    "is_markdown_block_start",
    # XHTML Helper
    "xhtml_to_markdown",
    "markdown_to_xhtml",
    "xhtml_to_adf",
    "adf_to_xhtml",
    "extract_text_from_xhtml",
    "wrap_in_storage_format",
    "validate_xhtml",
    # Cache
    "Cache",
    "get_cache",
    "cached",
    "invalidate",
]
