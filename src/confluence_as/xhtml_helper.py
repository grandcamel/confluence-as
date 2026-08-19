"""
XHTML Storage Format Helper

Provides utilities for working with Confluence's legacy XHTML storage format,
which is used by the v1 API and for content that predates the v2 API.

Features:
- Convert XHTML storage format to Markdown
- Convert Markdown to XHTML storage format
- Convert XHTML to ADF (for v1 to v2 migration)
- Handle Confluence-specific macros

XHTML Storage Format Documentation:
https://confluence.atlassian.com/doc/confluence-storage-format-790796544.html

Usage:
    from confluence_as import xhtml_to_markdown, markdown_to_xhtml

    # Convert XHTML to Markdown
    markdown = xhtml_to_markdown(storage_format_html)

    # Convert Markdown to XHTML
    xhtml = markdown_to_xhtml("# Heading\n\nParagraph")
"""

import html
import re
from typing import Any

from .formatters import strip_html_tags
from .markdown_parser import is_block_start, parse_markdown


def xhtml_to_markdown(xhtml: str) -> str:
    """
    Convert Confluence XHTML storage format to Markdown.

    Handles:
    - Paragraphs, headings, lists
    - Bold, italic, underline, strikethrough
    - Links and images
    - Code blocks and inline code
    - Tables
    - Common Confluence macros

    Args:
        xhtml: XHTML storage format content

    Returns:
        Markdown content
    """
    if not xhtml:
        return ""

    # Verbatim segments (CDATA contents, rendered code fences, emitted HTML
    # like <details>) are stashed here and re-inserted only at the very end,
    # so no later pass can strip or rewrite them.
    literals: list[str] = []

    # Protect CDATA sections before any other processing: their contents are
    # verbatim and must never be parsed as markup or unescaped.
    text = re.sub(
        r"<!\[CDATA\[(.*?)\]\]>",
        lambda m: _stash_literal(m.group(1), literals),
        xhtml,
        flags=re.DOTALL,
    )

    # Remove XML declaration and namespace prefixes.
    # The opening/closing distinction must be preserved: "<ac:foo>" becomes
    # "<foo>" while "</ac:foo>" becomes "</foo>". Rewriting both to closing
    # form would turn every opening namespaced tag into a closing tag and
    # break macro handling on real storage-format input.
    text = re.sub(r"<\?xml[^>]*\?>", "", text)
    text = re.sub(r"<(/?)ac:", r"<\1", text)
    text = re.sub(r"<(/?)ri:", r"<\1", text)

    # Process macros before general HTML. Entities are still escaped at this
    # point, so escaped markup in prose (e.g. "&lt;ac:structured-macro ...")
    # is never mistaken for live macros.
    text = _process_macros(text, literals)

    # Headings (h1-h6)
    def make_heading_replacer(lv: int):
        def replacer(m: re.Match[str]) -> str:
            return f"\n{'#' * lv} {_clean_text(m.group(1))}\n"

        return replacer

    for level in range(1, 7):
        pattern = rf"<h{level}[^>]*>(.*?)</h{level}>"
        text = re.sub(pattern, make_heading_replacer(level), text, flags=re.DOTALL)

    # Paragraphs
    text = re.sub(
        r"<p[^>]*>(.*?)</p>",
        lambda m: f"\n{_clean_text(m.group(1))}\n",
        text,
        flags=re.DOTALL,
    )

    # Line breaks
    text = re.sub(r"<br\s*/?\s*>", "  \n", text)

    # Bold
    text = re.sub(r"<strong[^>]*>(.*?)</strong>", r"**\1**", text, flags=re.DOTALL)
    text = re.sub(r"<b[^>]*>(.*?)</b>", r"**\1**", text, flags=re.DOTALL)

    # Italic
    text = re.sub(r"<em[^>]*>(.*?)</em>", r"*\1*", text, flags=re.DOTALL)
    text = re.sub(r"<i[^>]*>(.*?)</i>", r"*\1*", text, flags=re.DOTALL)

    # Underline (Markdown doesn't support, use HTML or emphasis)
    text = re.sub(r"<u[^>]*>(.*?)</u>", r"_\1_", text, flags=re.DOTALL)

    # Strikethrough
    text = re.sub(r"<s[^>]*>(.*?)</s>", r"~~\1~~", text, flags=re.DOTALL)
    text = re.sub(r"<del[^>]*>(.*?)</del>", r"~~\1~~", text, flags=re.DOTALL)

    # Inline code
    text = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`", text, flags=re.DOTALL)

    # Links
    text = re.sub(
        r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
        lambda m: f"[{_clean_text(m.group(2))}]({m.group(1)})",
        text,
        flags=re.DOTALL,
    )

    # Images
    text = re.sub(
        r'<img[^>]*src="([^"]*)"[^>]*alt="([^"]*)"[^>]*/?>', r"![\2](\1)", text
    )
    text = re.sub(r'<img[^>]*src="([^"]*)"[^>]*/?>', r"![](\1)", text)

    # Preformatted/code blocks
    text = re.sub(
        r"<pre[^>]*>(.*?)</pre>",
        lambda m: f"\n```\n{_clean_text(m.group(1))}\n```\n",
        text,
        flags=re.DOTALL,
    )

    # Process lists
    text = _process_lists(text)

    # Process tables
    text = _process_tables(text)

    # Blockquotes
    text = re.sub(
        r"<blockquote[^>]*>(.*?)</blockquote>",
        lambda m: (
            "\n"
            + "\n".join(f"> {line}" for line in _clean_text(m.group(1)).split("\n"))
            + "\n"
        ),
        text,
        flags=re.DOTALL,
    )

    # Horizontal rules
    text = re.sub(r"<hr\s*/?\s*>", "\n---\n", text)

    # Remove remaining HTML tags (still-escaped entities are untouched)
    text = re.sub(r"<[^>]+>", "", text)

    # Unescape HTML entities only now, after tag processing, so escaped
    # markup in prose renders as literal text instead of being parsed.
    text = html.unescape(text)

    # Render table-cell line-break sentinels as literal <br> now that the
    # generic tag strip can no longer remove them.
    text = text.replace(_CELL_LINE_BREAK, "<br>")

    # Re-insert protected verbatim segments. A literal may embed tokens of
    # earlier-stashed literals (an expand body containing a code fence), so
    # substitute repeatedly. Nesting depth is finite; the iteration bound
    # only guards against pathological token-like bytes in source content.
    for _ in range(len(literals) + 1):
        if not _TOKEN_RE.search(text):
            break
        text = _TOKEN_RE.sub(
            lambda m: (
                literals[int(m.group(1))] if int(m.group(1)) < len(literals) else ""
            ),
            text,
        )

    # Clean up whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    return text


def _clean_text(text: str) -> str:
    """Clean text content, removing extra whitespace."""
    return strip_html_tags(text, collapse_whitespace=True)


# Verbatim-segment protection tokens: \x01<index>\x02 markers survive every
# text pass (they contain no tags and no regex-whitespace) and are replaced
# with their stashed content at the very end of xhtml_to_markdown.
_TOKEN_RE = re.compile(r"\x01(\d+)\x02")


def _stash_literal(content: str, literals: list[str]) -> str:
    """Stash verbatim content and return its protection token."""
    literals.append(content)
    return f"\x01{len(literals) - 1}\x02"


# One structured-macro block (paired or self-closing) that contains no nested
# structured-macro opening tag, so repeated resolution runs innermost-first.
# The (?=[\s/>]) boundaries keep look-alike tags such as
# <structured-macro-ext> from matching.
_MACRO_BLOCK_RE = re.compile(
    r"<structured-macro(?=[\s/>])(?P<attrs>[^>]*?)"
    r"(?:/>|>(?P<body>(?:(?!<structured-macro[\s/>]).)*?)</structured-macro>)",
    re.DOTALL,
)

_PANEL_MACROS = frozenset({"info", "warning", "note", "tip", "panel"})


def _macro_parameter(block: str, name: str) -> str | None:
    """Extract a <parameter name="...">value</parameter> from a macro block."""
    param = re.search(rf'<parameter[^>]*name="{name}"[^>]*>([^<]*)</parameter>', block)
    return param.group(1) if param else None


def _rich_text_content(body: str) -> str:
    """Concatenate the rich-text-body contents of one macro block."""
    return "".join(
        re.findall(r"<rich-text-body[^>]*>(.*?)</rich-text-body>", body, re.DOTALL)
    )


def _render_macro(match: re.Match[str], literals: list[str]) -> str:
    """Render one innermost structured-macro block to Markdown.

    Handled macros (code, the panel family, status, toc, expand) get real
    renderings; any other macro is replaced by its rich-text-body content —
    preserving page-visible material inside layout macros such as section,
    column, and excerpt — while parameters and other internals are dropped
    so they never leak into the output.
    """
    attrs = match.group("attrs") or ""
    body = match.group("body") or ""
    block = match.group(0)
    name_match = re.search(r'name="([^"]*)"', attrs)
    name = name_match.group(1) if name_match else ""

    if name == "code":
        language = _macro_parameter(block, "language")
        if language is None:
            attr_lang = re.search(r'language="([^"]*)"', attrs)
            language = attr_lang.group(1) if attr_lang else ""
        content_match = re.search(
            r"<plain-text-body[^>]*>(.*?)</plain-text-body>", body, re.DOTALL
        )
        content = content_match.group(1) if content_match else ""
        token = _TOKEN_RE.fullmatch(content.strip())
        if token:
            # CDATA contents were stashed verbatim before any processing.
            code = literals[int(token.group(1))]
        else:
            code = html.unescape(content)
        fence = f"\n```{language}\n{code.strip(chr(10))}\n```\n"
        return _stash_literal(fence, literals)

    if name in _PANEL_MACROS:
        return f"\n> **{name.title()}:** {_clean_text(_rich_text_content(body))}\n"

    if name == "status":
        title = _macro_parameter(block, "title")
        return f"`{title}`" if title else ""

    if name == "toc":
        return "\n[Table of Contents]\n"

    if name == "expand":
        title = html.unescape(_macro_parameter(block, "title") or "Details")
        detail_body = html.unescape(_clean_text(_rich_text_content(body)))
        return _stash_literal(
            f"\n<details>\n<summary>{title}</summary>\n\n{detail_body}\n</details>\n",
            literals,
        )

    return _rich_text_content(body)


def _process_macros(text: str, literals: list[str]) -> str:
    """Resolve Confluence structured-macros innermost-first.

    Handled macros: code (fenced block), info/warning/note/tip/panel
    (quoted callout), status (inline code), toc (marker), expand
    (<details> block). Unhandled macros keep their rich-text content and
    lose their parameters. A macro name must match exactly — names that
    merely share a known prefix (e.g. "expand-foo") are unhandled.
    """
    while True:
        match = _MACRO_BLOCK_RE.search(text)
        if match is None:
            return text
        text = (
            text[: match.start()] + _render_macro(match, literals) + text[match.end() :]
        )


def _process_lists(text: str) -> str:
    """Process HTML lists to Markdown."""

    # Unordered lists
    def ul_handler(match):
        items = re.findall(r"<li[^>]*>(.*?)</li>", match.group(1), re.DOTALL)
        return "\n" + "\n".join(f"- {_clean_text(item)}" for item in items) + "\n"

    text = re.sub(r"<ul[^>]*>(.*?)</ul>", ul_handler, text, flags=re.DOTALL)

    # Ordered lists
    def ol_handler(match):
        items = re.findall(r"<li[^>]*>(.*?)</li>", match.group(1), re.DOTALL)
        return (
            "\n"
            + "\n".join(f"{i + 1}. {_clean_text(item)}" for i, item in enumerate(items))
            + "\n"
        )

    text = re.sub(r"<ol[^>]*>(.*?)</ol>", ol_handler, text, flags=re.DOTALL)

    return text


# Sentinel marking an intended line break inside a table cell. NUL cannot
# appear in legitimate XHTML text content, so replacing exact occurrences
# (never stripping character classes from the ends) cannot eat real content
# even when a cell's text starts with sentinel-like characters.
_CELL_LINE_BREAK = "\x00"


def _format_table_cell(cell_html: str) -> str:
    """Convert one table cell's content to Markdown-safe single-line text.

    Paragraph boundaries and explicit <br> tags become literal "<br>" so the
    cell's multiline structure survives inside a one-line Markdown table row.
    By the time tables are processed the earlier paragraph and <br> passes
    have usually rewritten cell internals into newline-separated text, so
    interior newline runs are treated as intended breaks; raw <p>/<br> forms
    are handled as well.
    """
    text = re.sub(r"</p>\s*<p[^>]*>", _CELL_LINE_BREAK, cell_html)
    text = re.sub(r"<br\s*/?\s*>", _CELL_LINE_BREAK, text)
    text = re.sub(r"\s*\n\s*", _CELL_LINE_BREAK, text.strip())
    text = _clean_text(text)
    # A literal pipe would split the cell into extra Markdown columns.
    text = text.replace("|", "\\|")
    # Drop breaks that would render as leading/trailing <br> in the cell,
    # replacing exact sentinel occurrences only (no character-class strip
    # that could eat legitimate cell text).
    text = re.sub(rf"\A(?:\s*{_CELL_LINE_BREAK})+\s*", "", text)
    text = re.sub(rf"(?:{_CELL_LINE_BREAK}\s*)+\Z", "", text)
    # Collapse each break run to a single sentinel; xhtml_to_markdown renders
    # sentinels as "<br>" after its generic tag strip (a literal "<br>"
    # inserted here would be removed by that strip).
    return re.sub(rf"\s*(?:{_CELL_LINE_BREAK}\s*)+", _CELL_LINE_BREAK, text)


def _process_tables(text: str) -> str:
    """Process HTML tables to Markdown."""

    def table_handler(match):
        table_html = match.group(0)
        rows = []

        # Find all rows
        row_matches = re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.DOTALL)

        for i, row_html in enumerate(row_matches):
            # Find cells (th or td)
            cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row_html, re.DOTALL)
            cells = [_format_table_cell(c) for c in cells]

            if cells:
                row = "| " + " | ".join(cells) + " |"
                rows.append(row)

                # Add header separator after first row
                if i == 0:
                    separator = "| " + " | ".join(["---"] * len(cells)) + " |"
                    rows.append(separator)

        return "\n" + "\n".join(rows) + "\n" if rows else ""

    text = re.sub(r"<table[^>]*>.*?</table>", table_handler, text, flags=re.DOTALL)

    return text


def markdown_to_xhtml(markdown: str) -> str:
    """
    Convert Markdown to Confluence XHTML storage format.

    Args:
        markdown: Markdown content

    Returns:
        XHTML storage format content
    """
    if not markdown:
        return ""

    # Parse markdown into intermediate representation
    blocks = parse_markdown(markdown)

    if not blocks:
        return ""

    # Convert blocks to XHTML
    result = []
    for block in blocks:
        block_type = block["type"]

        if block_type == "heading":
            level = block["level"]
            text = _markdown_inline_to_xhtml(block["content"])
            result.append(f"<h{level}>{text}</h{level}>")

        elif block_type == "horizontal_rule":
            result.append("<hr />")

        elif block_type == "code_block":
            # Escape HTML in code content
            code = html.escape(block["content"])
            language = block.get("language")

            if language:
                result.append(
                    f'<ac:structured-macro ac:name="code">'
                    f'<ac:parameter ac:name="language">{language}</ac:parameter>'
                    f"<ac:plain-text-body><![CDATA[{block['content']}]]></ac:plain-text-body>"
                    f"</ac:structured-macro>"
                )
            else:
                result.append(f"<pre>{code}</pre>")

        elif block_type == "blockquote":
            # Join lines with space for blockquote
            quote_content = _markdown_inline_to_xhtml(
                block["content"].replace("\n", " ")
            )
            result.append(f"<blockquote><p>{quote_content}</p></blockquote>")

        elif block_type == "bullet_list":
            items = [
                f"<li>{_markdown_inline_to_xhtml(item)}</li>" for item in block["items"]
            ]
            result.append("<ul>" + "".join(items) + "</ul>")

        elif block_type == "ordered_list":
            items = [
                f"<li>{_markdown_inline_to_xhtml(item)}</li>" for item in block["items"]
            ]
            result.append("<ol>" + "".join(items) + "</ol>")

        elif block_type == "paragraph":
            para_content = _markdown_inline_to_xhtml(block["content"])
            result.append(f"<p>{para_content}</p>")

    return "".join(result)


# Alias for internal use - uses shared function from markdown_parser
_is_block_start = is_block_start


def _markdown_inline_to_xhtml(text: str) -> str:
    """
    Convert inline Markdown elements to XHTML.

    Handles bold, italic, code, links, images.
    """
    # Escape HTML entities first
    text = html.escape(text)

    # Bold **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__(.+?)__", r"<strong>\1</strong>", text)

    # Italic *text* or _text_
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    text = re.sub(r"_(.+?)_", r"<em>\1</em>", text)

    # Strikethrough ~~text~~
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)

    # Code `text`
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)

    # Images ![alt](url)
    text = re.sub(
        r"!\[([^\]]*)\]\(([^)]+)\)",
        r'<ac:image><ri:url ri:value="\2" /></ac:image>',
        text,
    )

    # Links [text](url)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)

    return text


def xhtml_to_adf(xhtml: str) -> dict[str, Any]:
    """
    Convert Confluence XHTML storage format to ADF.

    This is useful for migrating content from v1 API format to v2 API format.

    Args:
        xhtml: XHTML storage format content

    Returns:
        ADF document
    """
    # First convert to Markdown (intermediate format)
    markdown = xhtml_to_markdown(xhtml)

    # Then convert Markdown to ADF
    from .adf_helper import markdown_to_adf

    return markdown_to_adf(markdown)


def adf_to_xhtml(adf: dict[str, Any]) -> str:
    """
    Convert ADF to XHTML storage format.

    This is useful for using v2 content with v1 API endpoints.

    Args:
        adf: ADF document

    Returns:
        XHTML storage format content
    """
    # First convert to Markdown
    from .adf_helper import adf_to_markdown

    markdown = adf_to_markdown(adf)

    # Then convert Markdown to XHTML
    return markdown_to_xhtml(markdown)


def extract_text_from_xhtml(xhtml: str) -> str:
    """
    Extract plain text from XHTML content.

    Args:
        xhtml: XHTML storage format content

    Returns:
        Plain text content
    """
    # Remove all HTML tags
    text = re.sub(r"<[^>]+>", " ", xhtml)
    # Unescape HTML entities
    text = html.unescape(text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def wrap_in_storage_format(content: str) -> str:
    """
    Wrap content in proper Confluence storage format structure.

    Args:
        content: XHTML content

    Returns:
        Complete storage format with proper namespaces
    """
    return content


def validate_xhtml(xhtml: str) -> tuple[bool, str | None]:
    """
    Validate XHTML storage format.

    Args:
        xhtml: XHTML content to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Basic validation - check for unbalanced tags
    tag_stack: list[str] = []
    tag_pattern = re.compile(r"<(/?)(\w+)[^>]*(/?)>")

    for match in tag_pattern.finditer(xhtml):
        is_closing = match.group(1) == "/"
        tag_name = match.group(2).lower()
        is_self_closing = match.group(3) == "/"

        # Skip self-closing tags
        if is_self_closing:
            continue

        # Skip void elements
        void_elements = {"br", "hr", "img", "input", "meta", "link"}
        if tag_name in void_elements:
            continue

        if is_closing:
            if not tag_stack or tag_stack[-1] != tag_name:
                expected = tag_stack[-1] if tag_stack else "none"
                return (
                    False,
                    f"Unexpected closing tag </{tag_name}>, expected </{expected}>",
                )
            tag_stack.pop()
        else:
            tag_stack.append(tag_name)

    if tag_stack:
        return False, f"Unclosed tags: {', '.join(tag_stack)}"

    return True, None
