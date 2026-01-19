"""
Shared Markdown Parser

Provides a common Markdown parser that produces an intermediate representation (IR)
which can be converted to different output formats (ADF, XHTML, etc.).

This module consolidates the duplicate parsing logic from adf_helper and xhtml_helper.

Usage:
    from confluence_assistant_skills_lib.markdown_parser import parse_markdown

    blocks = parse_markdown("# Heading\n\nParagraph text")
    # Returns list of MarkdownBlock dicts
"""

import re
from typing import Optional, TypedDict


class MarkdownBlock(TypedDict, total=False):
    """
    Intermediate representation for a Markdown block element.

    Attributes:
        type: Block type ('heading', 'paragraph', 'code_block', 'blockquote',
              'bullet_list', 'ordered_list', 'horizontal_rule')
        content: Text content (for heading, paragraph, code_block, blockquote)
        level: Heading level 1-6 (for heading only)
        language: Programming language (for code_block only)
        items: List items (for bullet_list and ordered_list only)
    """

    type: str
    content: str
    level: int
    language: Optional[str]
    items: list[str]


def is_block_start(line: str) -> bool:
    """
    Check if a line starts a Markdown block element.

    This function is used during parsing to detect block boundaries
    and ensure consistent behavior across all Markdown processing.

    Args:
        line: A line of Markdown text (should be stripped)

    Returns:
        True if the line starts a block element (heading, code fence,
        blockquote, list item, or horizontal rule)
    """
    return bool(
        line.startswith("#")
        or line.startswith("```")
        or line.startswith(">")
        or re.match(r"^[-*]\s+", line)
        or re.match(r"^\d+\.\s+", line)
        or re.match(r"^[-*_]{3,}$", line)
    )


def parse_markdown(markdown: str) -> list[MarkdownBlock]:
    """
    Parse Markdown into a list of block elements.

    Supports:
    - Headings (# to ######)
    - Horizontal rules (---, ***, ___)
    - Code blocks (``` with optional language)
    - Blockquotes (>)
    - Bullet lists (- or *)
    - Ordered lists (1. 2. etc.)
    - Paragraphs (everything else)

    Args:
        markdown: Markdown content to parse

    Returns:
        List of MarkdownBlock dicts representing the document structure
    """
    if not markdown:
        return []

    blocks: list[MarkdownBlock] = []
    lines = markdown.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Empty line - skip
        if not stripped:
            i += 1
            continue

        # Heading
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading_match:
            blocks.append(
                {
                    "type": "heading",
                    "level": len(heading_match.group(1)),
                    "content": heading_match.group(2),
                }
            )
            i += 1
            continue

        # Horizontal rule
        if re.match(r"^[-*_]{3,}$", stripped):
            blocks.append({"type": "horizontal_rule"})
            i += 1
            continue

        # Code block (fenced)
        if stripped.startswith("```"):
            lang_match = re.match(r"^```(\w*)$", stripped)
            language = (
                lang_match.group(1) if lang_match and lang_match.group(1) else None
            )
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            blocks.append(
                {
                    "type": "code_block",
                    "content": "\n".join(code_lines),
                    "language": language,
                }
            )
            i += 1  # Skip closing ```
            continue

        # Blockquote
        if stripped.startswith(">"):
            quote_lines = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_text = re.sub(r"^>\s*", "", lines[i].strip())
                quote_lines.append(quote_text)
                i += 1
            blocks.append(
                {
                    "type": "blockquote",
                    "content": "\n".join(quote_lines),
                }
            )
            continue

        # Bullet list
        if re.match(r"^[-*]\s+", stripped):
            items = []
            while i < len(lines) and re.match(r"^[-*]\s+", lines[i].strip()):
                item_text = re.sub(r"^[-*]\s+", "", lines[i].strip())
                items.append(item_text)
                i += 1
            blocks.append(
                {
                    "type": "bullet_list",
                    "items": items,
                }
            )
            continue

        # Ordered list
        if re.match(r"^\d+\.\s+", stripped):
            items = []
            while i < len(lines) and re.match(r"^\d+\.\s+", lines[i].strip()):
                item_text = re.sub(r"^\d+\.\s+", "", lines[i].strip())
                items.append(item_text)
                i += 1
            blocks.append(
                {
                    "type": "ordered_list",
                    "items": items,
                }
            )
            continue

        # Regular paragraph - collect consecutive non-block lines
        para_lines = []
        while (
            i < len(lines) and lines[i].strip() and not is_block_start(lines[i].strip())
        ):
            para_lines.append(lines[i].strip())
            i += 1

        if para_lines:
            blocks.append(
                {
                    "type": "paragraph",
                    "content": " ".join(para_lines),
                }
            )

    return blocks
