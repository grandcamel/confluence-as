"""
Output Formatters for Confluence Assistant Skills

Provides Confluence-specific formatting functions for pages, spaces, comments, etc.
Inherits generic formatters from the base library.
"""

import re
from typing import Any, Optional

# Import generic formatters and color utilities from the base library
# Re-exported for convenience - these are used by __init__.py
from assistant_skills_lib.formatters import (  # noqa: F401
    Colors,
    _colorize,
    export_csv,
    format_json,
    format_table,
    format_timestamp,
    print_error,
    print_info,
    print_success,
    print_warning,
)


def truncate(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate text to a maximum length.

    Args:
        text: The text to truncate.
        max_length: Maximum length of the result.
        suffix: Suffix to append when truncating.

    Returns:
        Truncated text with suffix if it was shortened.
    """
    if not text or len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def strip_html_tags(text: str, collapse_whitespace: bool = False) -> str:
    """
    Remove HTML tags from text.

    This is a shared utility used by both formatters and xhtml_helper
    for cleaning HTML/XHTML content.

    Args:
        text: Text containing HTML tags.
        collapse_whitespace: If True, collapse multiple whitespace to single space.

    Returns:
        Text with HTML tags removed and optionally whitespace collapsed.
    """
    if not text:
        return text
    # Remove HTML tags
    result = re.sub(r"<[^>]+>", "", text)
    if collapse_whitespace:
        result = re.sub(r"\s+", " ", result)
    return result.strip()


def format_page(page: dict[str, Any], detailed: bool = False) -> str:
    """
    Format a Confluence page for display.
    """
    lines = []
    title = page.get("title", "Untitled")
    page_id = page.get("id", "Unknown")
    status = page.get("status", "current")

    lines.append(_colorize(f"Page: {title}", Colors.BOLD))
    lines.append(f"  ID: {page_id}")
    lines.append(f"  Status: {status}")

    if space_id := page.get("spaceId"):
        lines.append(f"  Space ID: {space_id}")
    if parent_id := page.get("parentId"):
        lines.append(f"  Parent ID: {parent_id}")

    if version := page.get("version", {}):
        lines.append(f"  Version: {version.get('number', 1)}")
        if msg := version.get("message"):
            lines.append(f"  Version Message: {msg}")

    if created := page.get("createdAt"):
        lines.append(f"  Created: {format_timestamp(created)}")
    if author_id := page.get("authorId"):
        lines.append(f"  Author ID: {author_id}")
    if web_ui := page.get("_links", {}).get("webui"):
        lines.append(f"  URL: {web_ui}")

    if detailed:
        if labels := page.get("labels", {}).get("results", []):
            label_names = [lbl.get("name", lbl.get("label", "")) for lbl in labels]
            lines.append(f"  Labels: {', '.join(label_names)}")
        if storage := page.get("body", {}).get("storage", {}).get("value", ""):
            preview = truncate(storage.replace("\n", " "), 200)
            lines.append(f"  Content Preview: {preview}")

    return "\n".join(lines)


def format_blogpost(blogpost: dict[str, Any], detailed: bool = False) -> str:
    """
    Format a Confluence blog post for display.
    """
    lines = []
    title = blogpost.get("title", "Untitled")
    post_id = blogpost.get("id", "Unknown")
    status = blogpost.get("status", "current")

    lines.append(_colorize(f"Blog Post: {title}", Colors.BOLD))
    lines.append(f"  ID: {post_id}")
    lines.append(f"  Status: {status}")
    if space_id := blogpost.get("spaceId"):
        lines.append(f"  Space ID: {space_id}")
    if created := blogpost.get("createdAt"):
        lines.append(f"  Created: {format_timestamp(created)}")
    if web_ui := blogpost.get("_links", {}).get("webui"):
        lines.append(f"  URL: {web_ui}")

    return "\n".join(lines)


def format_space(space: dict[str, Any], detailed: bool = False) -> str:
    """
    Format a Confluence space for display.
    """
    lines = []
    name = space.get("name", "Unnamed")
    key = space.get("key", space.get("id", "Unknown"))
    space_type = space.get("type", "global")
    status = space.get("status", "current")

    lines.append(_colorize(f"Space: {name}", Colors.BOLD))
    lines.append(f"  Key: {key}")
    lines.append(f"  Type: {space_type}")
    lines.append(f"  Status: {status}")

    if desc := space.get("description", {}):
        desc_text = (
            desc.get("plain", {}).get("value", "")
            if isinstance(desc, dict)
            else str(desc)
        )
        if desc_text:
            lines.append(f"  Description: {truncate(desc_text, 100)}")

    if homepage_id := space.get("homepageId"):
        lines.append(f"  Homepage ID: {homepage_id}")

    if detailed:
        if web_ui := space.get("_links", {}).get("webui"):
            lines.append(f"  URL: {web_ui}")

    return "\n".join(lines)


def format_comment(comment: dict[str, Any], show_body: bool = True) -> str:
    """
    Format a Confluence comment for display.
    """
    lines = []
    comment_id = comment.get("id", "Unknown")
    created = comment.get("createdAt", "")
    author_id = comment.get("authorId", "Unknown")

    lines.append(_colorize(f"Comment {comment_id}", Colors.BOLD))
    lines.append(f"  Author ID: {author_id}")
    lines.append(f"  Created: {format_timestamp(created)}")

    if show_body:
        if storage := comment.get("body", {}).get("storage", {}).get("value", ""):
            text = truncate(strip_html_tags(storage), 200)
            lines.append(f"  Content: {text}")

    return "\n".join(lines)


def format_comments(
    comments: list[dict[str, Any]],
    limit: Optional[int] = None,
    show_body: bool = True,
) -> str:
    """
    Format multiple comments for display.
    """
    if not comments:
        return "No comments found."

    display_comments = comments[:limit] if limit else comments
    formatted = [
        f"{i}. {format_comment(c, show_body=show_body)}"
        for i, c in enumerate(display_comments, 1)
    ]
    return "\n\n".join(formatted)


def format_search_results(
    results: list[dict[str, Any]],
    show_labels: bool = False,
    show_ancestors: bool = False,
    show_excerpt: bool = True,
) -> str:
    """
    Format search results for display.
    """
    if not results:
        return "No results found."

    lines = [_colorize(f"Found {len(results)} result(s)", Colors.BOLD), ""]
    for i, result in enumerate(results, 1):
        content = result.get("content", result)
        title = content.get("title", "Untitled")
        content_id = content.get("id", "Unknown")
        content_type = content.get("type", "page")
        space_key = content.get("space", {}).get(
            "key", content.get("spaceId", "Unknown")
        )

        lines.append(f"{i}. {_colorize(title, Colors.CYAN)}")
        lines.append(f"   ID: {content_id} | Type: {content_type} | Space: {space_key}")

        if show_excerpt and (excerpt := result.get("excerpt", "")):
            clean = truncate(strip_html_tags(excerpt), 150)
            if clean:
                lines.append(f"   Excerpt: {clean}...")

        if show_ancestors and (ancestors := content.get("ancestors", [])):
            ancestor_titles = [a.get("title", "") for a in ancestors]
            lines.append(f"   Path: {' > '.join(ancestor_titles)}")

        if show_labels and (
            labels := content.get("metadata", {}).get("labels", {}).get("results", [])
        ):
            label_names = [lbl.get("name", "") for lbl in labels if lbl.get("name")]
            if label_names:
                lines.append(f"   Labels: {', '.join(label_names)}")

        if web_ui := content.get("_links", {}).get("webui"):
            lines.append(f"   URL: {web_ui}")
        lines.append("")

    return "\n".join(lines)


def format_attachment(attachment: dict[str, Any]) -> str:
    """
    Format an attachment for display.
    """
    from assistant_skills_lib.formatters import format_file_size

    lines = []
    title = attachment.get("title", "Unnamed")
    att_id = attachment.get("id", "Unknown")
    media_type = attachment.get("mediaType", "unknown")
    file_size = attachment.get("fileSize", 0)

    lines.append(_colorize(f"Attachment: {title}", Colors.BOLD))
    lines.append(f"  ID: {att_id}")
    lines.append(f"  Type: {media_type}")
    lines.append(f"  Size: {format_file_size(file_size)}")

    if download := attachment.get("_links", {}).get("download"):
        lines.append(f"  Download: {download}")

    return "\n".join(lines)


def format_label(label: dict[str, Any]) -> str:
    """
    Format a label for display.
    """
    name = label.get("name", label.get("label", "Unknown"))
    prefix = label.get("prefix", "")
    label_id = label.get("id", "")
    return f"{prefix}:{name} (ID: {label_id})" if prefix else f"{name} (ID: {label_id})"


def format_version(version: dict[str, Any]) -> str:
    """
    Format a version for display.
    """
    number = version.get("number", "Unknown")
    message = version.get("message", "")
    when = version.get("when", version.get("createdAt", ""))
    author = version.get("by", {}).get(
        "displayName", version.get("authorId", "Unknown")
    )

    line = f"v{number}"
    if when:
        line += f" ({format_timestamp(when)})"
    if author:
        line += f" by {author}"
    if message:
        line += f" - {message}"
    return line
