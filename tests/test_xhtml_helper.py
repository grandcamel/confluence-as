"""Tests for xhtml_helper module."""

from confluence_as import (
    adf_to_xhtml,
    extract_text_from_xhtml,
    markdown_to_xhtml,
    validate_xhtml,
    xhtml_to_adf,
    xhtml_to_markdown,
)


class TestXhtmlToMarkdown:
    """Tests for xhtml_to_markdown function."""

    def test_empty_input(self):
        """Empty input returns empty string."""
        assert xhtml_to_markdown("") == ""
        assert xhtml_to_markdown(None) == ""  # type: ignore[arg-type]

    def test_headings(self):
        """Headings are converted correctly."""
        assert "# Heading 1" in xhtml_to_markdown("<h1>Heading 1</h1>")
        assert "## Heading 2" in xhtml_to_markdown("<h2>Heading 2</h2>")
        assert "### Heading 3" in xhtml_to_markdown("<h3>Heading 3</h3>")
        assert "#### Heading 4" in xhtml_to_markdown("<h4>Heading 4</h4>")
        assert "##### Heading 5" in xhtml_to_markdown("<h5>Heading 5</h5>")
        assert "###### Heading 6" in xhtml_to_markdown("<h6>Heading 6</h6>")

    def test_paragraphs(self):
        """Paragraphs are converted correctly."""
        result = xhtml_to_markdown("<p>Hello world</p>")
        assert "Hello world" in result

    def test_bold(self):
        """Bold text is converted correctly."""
        assert "**bold**" in xhtml_to_markdown("<strong>bold</strong>")
        assert "**bold**" in xhtml_to_markdown("<b>bold</b>")

    def test_italic(self):
        """Italic text is converted correctly."""
        assert "*italic*" in xhtml_to_markdown("<em>italic</em>")
        assert "*italic*" in xhtml_to_markdown("<i>italic</i>")

    def test_underline(self):
        """Underline is converted to emphasis."""
        assert "_underlined_" in xhtml_to_markdown("<u>underlined</u>")

    def test_strikethrough(self):
        """Strikethrough is converted correctly."""
        assert "~~deleted~~" in xhtml_to_markdown("<s>deleted</s>")
        assert "~~deleted~~" in xhtml_to_markdown("<del>deleted</del>")

    def test_inline_code(self):
        """Inline code is converted correctly."""
        assert "`code`" in xhtml_to_markdown("<code>code</code>")

    def test_links(self):
        """Links are converted correctly."""
        result = xhtml_to_markdown('<a href="https://example.com">Link</a>')
        assert "[Link](https://example.com)" in result

    def test_images(self):
        """Images are converted correctly."""
        result = xhtml_to_markdown('<img src="image.png" alt="Alt text" />')
        assert "![Alt text](image.png)" in result

        result = xhtml_to_markdown('<img src="image.png" />')
        assert "![](image.png)" in result

    def test_code_block(self):
        """Code blocks are converted correctly."""
        result = xhtml_to_markdown("<pre>code block</pre>")
        assert "```" in result
        assert "code block" in result

    def test_unordered_list(self):
        """Unordered lists are converted correctly."""
        result = xhtml_to_markdown("<ul><li>Item 1</li><li>Item 2</li></ul>")
        assert "- Item 1" in result
        assert "- Item 2" in result

    def test_ordered_list(self):
        """Ordered lists are converted correctly."""
        result = xhtml_to_markdown("<ol><li>First</li><li>Second</li></ol>")
        assert "1. First" in result
        assert "2. Second" in result

    def test_blockquote(self):
        """Blockquotes are converted correctly."""
        result = xhtml_to_markdown("<blockquote>Quote text</blockquote>")
        assert "> Quote text" in result

    def test_horizontal_rule(self):
        """Horizontal rules are converted correctly."""
        result = xhtml_to_markdown("<hr />")
        assert "---" in result

    def test_line_break(self):
        """Line breaks are converted correctly."""
        result = xhtml_to_markdown("Line 1<br/>Line 2")
        assert "Line 1" in result
        assert "Line 2" in result

    def test_table(self):
        """Tables are converted correctly."""
        table = """
        <table>
            <tr><th>Header 1</th><th>Header 2</th></tr>
            <tr><td>Cell 1</td><td>Cell 2</td></tr>
        </table>
        """
        result = xhtml_to_markdown(table)
        assert "| Header 1 | Header 2 |" in result
        assert "| --- | --- |" in result
        assert "| Cell 1 | Cell 2 |" in result

    def test_xml_declaration_removed(self):
        """XML declaration is removed."""
        result = xhtml_to_markdown('<?xml version="1.0"?><p>Text</p>')
        assert "<?xml" not in result
        assert "Text" in result

    def test_namespace_prefixes_removed(self):
        """Namespace prefixes are handled."""
        result = xhtml_to_markdown("<ac:macro><p>Text</p></ac:macro>")
        assert "ac:" not in result

    def test_html_entities_unescaped(self):
        """HTML entities are unescaped."""
        result = xhtml_to_markdown("<p>&amp; &quot;text&quot;</p>")
        assert "&" in result
        assert '"text"' in result


class TestConfluenceMacros:
    """Tests for Confluence macro handling.

    Note: These tests use the format expected after namespace stripping.
    The actual Confluence XHTML uses ac: prefixes which are stripped first.
    """

    def test_code_macro(self):
        """Code macro is converted correctly."""
        # Using format with language as attribute (as parsed by regex)
        xhtml = """
        <structured-macro name="code" language="python">
            <plain-text-body>print("hello")</plain-text-body>
        </structured-macro>
        """
        result = xhtml_to_markdown(xhtml)
        assert "```python" in result
        assert 'print("hello")' in result

    def test_code_macro_no_language(self):
        """Code macro without language works."""
        xhtml = """
        <structured-macro name="code">
            <plain-text-body>print("hello")</plain-text-body>
        </structured-macro>
        """
        result = xhtml_to_markdown(xhtml)
        assert "```" in result
        assert 'print("hello")' in result

    def test_info_panel(self):
        """Info panel macro is converted correctly."""
        xhtml = """
        <structured-macro name="info">
            <rich-text-body>Information text</rich-text-body>
        </structured-macro>
        """
        result = xhtml_to_markdown(xhtml)
        assert "**Info:**" in result
        assert "Information text" in result

    def test_warning_panel(self):
        """Warning panel macro is converted correctly."""
        xhtml = """
        <structured-macro name="warning">
            <rich-text-body>Warning text</rich-text-body>
        </structured-macro>
        """
        result = xhtml_to_markdown(xhtml)
        assert "**Warning:**" in result
        assert "Warning text" in result

    def test_note_panel(self):
        """Note panel macro is converted correctly."""
        xhtml = """
        <structured-macro name="note">
            <rich-text-body>Note text</rich-text-body>
        </structured-macro>
        """
        result = xhtml_to_markdown(xhtml)
        assert "**Note:**" in result
        assert "Note text" in result

    def test_status_macro(self):
        """Status macro is converted correctly."""
        xhtml = """
        <structured-macro name="status">
            <parameter name="title">In Progress</parameter>
        </structured-macro>
        """
        result = xhtml_to_markdown(xhtml)
        assert "`In Progress`" in result

    def test_toc_macro(self):
        """TOC macro is converted correctly."""
        xhtml = '<structured-macro name="toc"></structured-macro>'
        result = xhtml_to_markdown(xhtml)
        assert "[Table of Contents]" in result

    def test_tip_panel(self):
        """Tip panel macro is converted correctly."""
        xhtml = """
        <structured-macro name="tip">
            <rich-text-body>Tip text</rich-text-body>
        </structured-macro>
        """
        result = xhtml_to_markdown(xhtml)
        assert "**Tip:**" in result
        assert "Tip text" in result


class TestMarkdownToXhtml:
    """Tests for markdown_to_xhtml function."""

    def test_empty_input(self):
        """Empty input returns empty string."""
        assert markdown_to_xhtml("") == ""

    def test_heading(self):
        """Headings are converted correctly."""
        assert "<h1>Heading</h1>" in markdown_to_xhtml("# Heading")
        assert "<h2>Heading</h2>" in markdown_to_xhtml("## Heading")
        assert "<h3>Heading</h3>" in markdown_to_xhtml("### Heading")

    def test_paragraph(self):
        """Paragraphs are converted correctly."""
        result = markdown_to_xhtml("Hello world")
        assert "<p>Hello world</p>" in result

    def test_bold(self):
        """Bold text is converted correctly."""
        result = markdown_to_xhtml("**bold**")
        assert "<strong>bold</strong>" in result

    def test_italic(self):
        """Italic text is converted correctly."""
        result = markdown_to_xhtml("*italic*")
        assert "<em>italic</em>" in result

    def test_strikethrough(self):
        """Strikethrough is converted correctly."""
        result = markdown_to_xhtml("~~deleted~~")
        assert "<s>deleted</s>" in result

    def test_inline_code(self):
        """Inline code is converted correctly."""
        result = markdown_to_xhtml("`code`")
        assert "<code>code</code>" in result

    def test_link(self):
        """Links are converted correctly."""
        result = markdown_to_xhtml("[Link](https://example.com)")
        assert '<a href="https://example.com">Link</a>' in result

    def test_image(self):
        """Images are converted correctly."""
        result = markdown_to_xhtml("![Alt](image.png)")
        assert "ri:url" in result or "ac:image" in result

    def test_code_block_with_language(self):
        """Code blocks with language are converted correctly."""
        result = markdown_to_xhtml("```python\nprint('hello')\n```")
        assert "ac:structured-macro" in result
        assert "language" in result
        assert "python" in result

    def test_code_block_without_language(self):
        """Code blocks without language use pre tag."""
        result = markdown_to_xhtml("```\ncode\n```")
        assert "<pre>" in result

    def test_blockquote(self):
        """Blockquotes are converted correctly."""
        result = markdown_to_xhtml("> Quote")
        assert "<blockquote>" in result
        assert "Quote" in result

    def test_unordered_list(self):
        """Unordered lists are converted correctly."""
        result = markdown_to_xhtml("- Item 1\n- Item 2")
        assert "<ul>" in result
        assert "<li>Item 1</li>" in result
        assert "<li>Item 2</li>" in result

    def test_ordered_list(self):
        """Ordered lists are converted correctly."""
        result = markdown_to_xhtml("1. First\n2. Second")
        assert "<ol>" in result
        assert "<li>First</li>" in result
        assert "<li>Second</li>" in result

    def test_horizontal_rule(self):
        """Horizontal rules are converted correctly."""
        result = markdown_to_xhtml("---")
        assert "<hr />" in result

    def test_html_escaping(self):
        """HTML characters are escaped."""
        result = markdown_to_xhtml("Use <tag> & stuff")
        assert "&lt;tag&gt;" in result
        assert "&amp;" in result


class TestCrossFormatConversion:
    """Tests for xhtml_to_adf and adf_to_xhtml."""

    def test_xhtml_to_adf(self):
        """XHTML to ADF conversion works."""
        xhtml = "<p>Hello <strong>world</strong></p>"
        adf = xhtml_to_adf(xhtml)
        assert adf["type"] == "doc"
        assert "content" in adf

    def test_adf_to_xhtml(self):
        """ADF to XHTML conversion works."""
        adf = {
            "version": 1,
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Hello"}]}
            ],
        }
        xhtml = adf_to_xhtml(adf)
        assert "<p>" in xhtml
        assert "Hello" in xhtml

    def test_roundtrip_xhtml_to_adf_to_xhtml(self):
        """XHTML can be converted to ADF and back."""
        original = "<p>Hello world</p>"
        adf = xhtml_to_adf(original)
        result = adf_to_xhtml(adf)
        assert "Hello world" in result


class TestExtractText:
    """Tests for extract_text_from_xhtml."""

    def test_basic_extraction(self):
        """Basic text extraction works."""
        result = extract_text_from_xhtml("<p>Hello <strong>world</strong></p>")
        assert "Hello" in result
        assert "world" in result

    def test_whitespace_collapsed(self):
        """Whitespace is collapsed."""
        result = extract_text_from_xhtml("<p>Hello    world</p>")
        assert "Hello world" in result

    def test_entities_unescaped(self):
        """HTML entities are unescaped."""
        result = extract_text_from_xhtml("<p>&amp; &lt; &gt;</p>")
        assert "&" in result
        assert "<" in result
        assert ">" in result


class TestValidateXhtml:
    """Tests for validate_xhtml."""

    def test_valid_xhtml(self):
        """Valid XHTML passes validation."""
        is_valid, error = validate_xhtml("<p>Hello <strong>world</strong></p>")
        assert is_valid is True
        assert error is None

    def test_nested_tags(self):
        """Nested tags are validated correctly."""
        is_valid, error = validate_xhtml("<div><p><span>Text</span></p></div>")
        assert is_valid is True
        assert error is None

    def test_self_closing_tags(self):
        """Self-closing tags are handled correctly."""
        is_valid, error = validate_xhtml("<p>Line 1<br />Line 2</p>")
        assert is_valid is True
        assert error is None

    def test_void_elements(self):
        """Void elements are handled correctly."""
        is_valid, error = validate_xhtml('<p>Image: <img src="x.png" alt="test"></p>')
        assert is_valid is True
        assert error is None

    def test_unclosed_tag(self):
        """Unclosed tags are detected."""
        is_valid, error = validate_xhtml("<p>Hello <strong>world</p>")
        assert is_valid is False
        assert "Unclosed tags" in error or "Unexpected" in error

    def test_mismatched_tags(self):
        """Mismatched tags are detected."""
        is_valid, error = validate_xhtml("<p>Hello</div>")
        assert is_valid is False
        assert error is not None

    def test_extra_closing_tag(self):
        """Extra closing tags are detected."""
        is_valid, error = validate_xhtml("<p>Hello</p></p>")
        assert is_valid is False
        assert "Unexpected closing tag" in error


class TestNamespaceNormalization:
    """Regression tests for ac:/ri: namespace handling on real storage XHTML.

    Opening namespaced tags must normalize to opening tags (not be mangled
    into closing-tag form), so macro handlers work on real Confluence input.
    """

    REAL_CODE_MACRO = (
        '<ac:structured-macro ac:name="code" ac:schema-version="1" '
        'ac:macro-id="m1"><ac:parameter ac:name="language">python'
        "</ac:parameter><ac:plain-text-body><![CDATA[def f():\n"
        "    return 1]]></ac:plain-text-body></ac:structured-macro>"
    )

    def test_code_macro_on_namespaced_input(self):
        """Real namespaced code macro produces a fenced code block."""
        result = xhtml_to_markdown(self.REAL_CODE_MACRO)
        assert "```python" in result
        assert "def f():" in result
        assert "    return 1" in result

    def test_info_panel_on_namespaced_input(self):
        """Real namespaced info panel is converted."""
        xhtml = (
            '<ac:structured-macro ac:name="info" ac:schema-version="1">'
            "<ac:rich-text-body><p>Information text</p></ac:rich-text-body>"
            "</ac:structured-macro>"
        )
        result = xhtml_to_markdown(xhtml)
        assert "**Info:**" in result
        assert "Information text" in result

    def test_status_macro_on_namespaced_input(self):
        """Real namespaced status macro with ac:name parameter converts."""
        xhtml = (
            '<ac:structured-macro ac:name="status" ac:schema-version="1">'
            '<ac:parameter ac:name="title">In Progress</ac:parameter>'
            '<ac:parameter ac:name="colour">Yellow</ac:parameter>'
            "</ac:structured-macro>"
        )
        result = xhtml_to_markdown(xhtml)
        assert "`In Progress`" in result

    def test_expand_macro_on_namespaced_input(self):
        """Real namespaced expand macro keeps its title."""
        xhtml = (
            '<ac:structured-macro ac:name="expand" ac:schema-version="1">'
            '<ac:parameter ac:name="title">More details</ac:parameter>'
            "<ac:rich-text-body><p>Hidden text</p></ac:rich-text-body>"
            "</ac:structured-macro>"
        )
        result = xhtml_to_markdown(xhtml)
        assert "More details" in result
        assert "Hidden text" in result

    def test_opening_tags_not_mangled(self):
        """Opening namespaced tags do not become closing tags."""
        xhtml = '<ac:link><ri:page ri:content-title="Target" /></ac:link>Text'
        result = xhtml_to_markdown(xhtml)
        assert "Text" in result
        assert "ac:" not in result
        assert "ri:" not in result


class TestUnhandledMacroDrop:
    """Regression tests: unhandled structured-macros are dropped wholesale."""

    def test_unhandled_macro_params_do_not_leak(self):
        """Parameter bodies of unhandled macros never reach the output."""
        xhtml = (
            '<ac:structured-macro ac:name="jira" ac:schema-version="1">'
            '<ac:parameter ac:name="server">SECRETSERVER</ac:parameter>'
            '<ac:parameter ac:name="key">PROJ-1</ac:parameter>'
            "</ac:structured-macro><p>Visible</p>"
        )
        result = xhtml_to_markdown(xhtml)
        assert "SECRETSERVER" not in result
        assert "PROJ-1" not in result
        assert "Visible" in result

    def test_nested_unhandled_inside_handled(self):
        """An unhandled macro inside a handled macro's body is dropped."""
        xhtml = (
            '<ac:structured-macro ac:name="info">'
            "<ac:rich-text-body>Keep this "
            '<ac:structured-macro ac:name="unknown-widget">'
            '<ac:parameter ac:name="cfg">LEAKED</ac:parameter>'
            "</ac:structured-macro>"
            "</ac:rich-text-body></ac:structured-macro>"
        )
        result = xhtml_to_markdown(xhtml)
        assert "**Info:**" in result
        assert "Keep this" in result
        assert "LEAKED" not in result

    def test_nested_unhandled_inside_unhandled_with_tail(self):
        """Nested unhandled macros: parameters vanish, body content stays."""
        xhtml = (
            '<ac:structured-macro ac:name="outer-unknown">'
            "<ac:rich-text-body>"
            '<ac:structured-macro ac:name="inner-unknown">'
            '<ac:parameter ac:name="a">INNER</ac:parameter>'
            "</ac:structured-macro>"
            " TAIL"
            "</ac:rich-text-body></ac:structured-macro><p>After</p>"
        )
        result = xhtml_to_markdown(xhtml)
        assert "INNER" not in result
        assert "TAIL" in result  # rich-text content is page-visible material
        assert "After" in result

    def test_known_prefix_name_is_not_treated_as_known(self):
        """A macro sharing a known prefix (expand-foo) is still unhandled."""
        xhtml = (
            '<ac:structured-macro ac:name="expand-foo">'
            '<ac:parameter ac:name="title">Should vanish</ac:parameter>'
            "<ac:rich-text-body>Hidden body</ac:rich-text-body>"
            "</ac:structured-macro><p>Kept</p>"
        )
        result = xhtml_to_markdown(xhtml)
        # Not rendered as an expand macro; the title parameter is dropped
        # while the rich-text content is preserved.
        assert "<details>" not in result
        assert "Should vanish" not in result
        assert "Hidden body" in result
        assert "Kept" in result

    def test_self_closing_unhandled_macro_dropped(self):
        """Self-closing unhandled macros are removed cleanly."""
        xhtml = '<p>Before</p><ac:structured-macro ac:name="anchor"/><p>After</p>'
        result = xhtml_to_markdown(xhtml)
        assert "Before" in result
        assert "After" in result
        assert "structured-macro" not in result


class TestTableCellLineBreaks:
    """Regression tests: multiline table cell structure is preserved."""

    def test_paragraph_separated_cell_content(self):
        """Paragraph-separated cell content keeps line breaks as <br>."""
        xhtml = (
            "<table><tr><th>K</th></tr>"
            "<tr><td><p>line one</p><p>line two</p></td></tr></table>"
        )
        result = xhtml_to_markdown(xhtml)
        assert "| line one<br>line two |" in result

    def test_br_separated_cell_content(self):
        """<br>-separated cell content keeps line breaks as <br>."""
        xhtml = "<table><tr><th>K</th></tr><tr><td>a<br/>b</td></tr></table>"
        result = xhtml_to_markdown(xhtml)
        assert "| a<br>b |" in result

    def test_single_paragraph_cell_unchanged(self):
        """A single-paragraph cell has no stray <br> markers."""
        xhtml = "<table><tr><th>K</th></tr><tr><td><p>only</p></td></tr></table>"
        result = xhtml_to_markdown(xhtml)
        assert "| only |" in result
        assert "<br>" not in result

    def test_cell_text_starting_with_sentinel_like_characters(self):
        """Legitimate cell text resembling a sentinel token is untouched."""
        xhtml = (
            "<table><tr><th>K</th></tr>"
            "<tr><td><p>%%BR%% leading token</p><p>second</p></td></tr></table>"
        )
        result = xhtml_to_markdown(xhtml)
        assert "| %%BR%% leading token<br>second |" in result

    def test_table_rows_stay_single_line(self):
        """Multiline cells never break Markdown table row structure."""
        xhtml = (
            "<table><tr><th>A</th><th>B</th></tr>"
            "<tr><td><p>x</p><p>y</p></td><td>z</td></tr></table>"
        )
        result = xhtml_to_markdown(xhtml)
        table_lines = [ln for ln in result.splitlines() if ln.startswith("|")]
        assert len(table_lines) == 3  # header, separator, one data row
        assert "| x<br>y | z |" in result


class TestContentPreservation:
    """Regression tests from review: conversion must never delete content."""

    def test_section_column_layout_content_preserved(self):
        """Layout macros (section/column) keep their page content."""
        xhtml = (
            '<ac:structured-macro ac:name="section">'
            "<ac:rich-text-body>"
            '<ac:structured-macro ac:name="column">'
            "<ac:rich-text-body><p>Important page content</p></ac:rich-text-body>"
            "</ac:structured-macro>"
            "</ac:rich-text-body></ac:structured-macro>"
        )
        result = xhtml_to_markdown(xhtml)
        assert "Important page content" in result

    def test_excerpt_macro_body_preserved(self):
        """Excerpt macro bodies are page-visible and must survive."""
        xhtml = (
            '<ac:structured-macro ac:name="excerpt">'
            "<ac:rich-text-body><p>Reusable intro text</p></ac:rich-text-body>"
            "</ac:structured-macro>"
        )
        result = xhtml_to_markdown(xhtml)
        assert "Reusable intro text" in result

    def test_cdata_containing_macro_markup_is_inert(self):
        """Macro-looking text inside CDATA never consumes real content."""
        xhtml = (
            "<p>Intro</p>"
            '<ac:structured-macro ac:name="code">'
            "<ac:plain-text-body><![CDATA["
            '<ac:structured-macro ac:name="mymacro">'
            "]]></ac:plain-text-body></ac:structured-macro>"
            "<p>After</p>"
        )
        result = xhtml_to_markdown(xhtml)
        assert "Intro" in result
        assert "After" in result
        assert '<ac:structured-macro ac:name="mymacro">' in result  # verbatim code

    def test_escaped_macro_example_in_prose_stays_literal(self):
        """HTML-escaped markup examples render as text, not live macros."""
        xhtml = (
            "<p>To embed an issue write "
            "&lt;ac:structured-macro ac:name=&quot;jira&quot;&gt;PROJ-1"
            "&lt;/ac:structured-macro&gt; in the storage body.</p>"
        )
        result = xhtml_to_markdown(xhtml)
        assert "PROJ-1" in result
        assert 'ac:name="jira"' in result

    def test_code_with_angle_brackets_survives(self):
        """Angle brackets in code (C++ templates, comparisons) are kept."""
        xhtml = (
            '<ac:structured-macro ac:name="code">'
            '<ac:parameter ac:name="language">cpp</ac:parameter>'
            "<ac:plain-text-body><![CDATA[std::vector<int> v;]]>"
            "</ac:plain-text-body></ac:structured-macro>"
        )
        result = xhtml_to_markdown(xhtml)
        assert "std::vector<int> v;" in result

    def test_code_comparison_does_not_eat_following_content(self):
        """An unmatched '<' in code must not delete later document text."""
        xhtml = (
            '<ac:structured-macro ac:name="code">'
            "<ac:plain-text-body><![CDATA[if a < b: pass]]>"
            "</ac:plain-text-body></ac:structured-macro>"
            "<p>Everything here should survive</p><p>x &gt; y sentence</p>"
        )
        result = xhtml_to_markdown(xhtml)
        assert "if a < b: pass" in result
        assert "Everything here should survive" in result
        assert "x > y sentence" in result

    def test_expand_details_markup_survives_to_output(self):
        """Expand renders a <details>/<summary> block in the final output."""
        xhtml = (
            '<ac:structured-macro ac:name="expand">'
            '<ac:parameter ac:name="title">More</ac:parameter>'
            "<ac:rich-text-body><p>Hidden text</p></ac:rich-text-body>"
            "</ac:structured-macro>"
        )
        result = xhtml_to_markdown(xhtml)
        assert "<details>" in result
        assert "<summary>More</summary>" in result
        assert "Hidden text" in result
        assert "</details>" in result

    def test_empty_panel_does_not_swallow_following_content(self):
        """A panel without a body must not consume text up to the next macro."""
        xhtml = (
            '<ac:structured-macro ac:name="info"><ac:rich-text-body />'
            "</ac:structured-macro>"
            "<p>REAL CONTENT BETWEEN</p>"
            '<ac:structured-macro ac:name="warning">'
            "<ac:rich-text-body>warn body</ac:rich-text-body>"
            "</ac:structured-macro>"
        )
        result = xhtml_to_markdown(xhtml)
        assert "REAL CONTENT BETWEEN" in result
        assert "**Warning:** warn body" in result

    def test_status_without_title_does_not_span_macros(self):
        """A title-less status macro must not consume the next macro's title."""
        xhtml = (
            '<ac:structured-macro ac:name="status"></ac:structured-macro>'
            "<p>MIDDLE TEXT</p>"
            '<ac:structured-macro ac:name="status">'
            '<ac:parameter ac:name="title">Done</ac:parameter>'
            "</ac:structured-macro>"
        )
        result = xhtml_to_markdown(xhtml)
        assert "MIDDLE TEXT" in result
        assert "`Done`" in result

    def test_self_closing_toc_renders_marker(self):
        """A parameterless self-closing toc still renders its marker."""
        xhtml = (
            "<p>Before</p>"
            '<ac:structured-macro ac:name="toc" ac:schema-version="1" '
            'ac:macro-id="t1"/><p>After</p>'
        )
        result = xhtml_to_markdown(xhtml)
        assert "[Table of Contents]" in result
        assert "Before" in result
        assert "After" in result

    def test_macro_lookalike_tag_not_matched(self):
        """Tags like <structured-macro-ext> are not treated as macros."""
        xhtml = (
            "<p>Start</p><ac:structured-macro-ext>kept text"
            "</ac:structured-macro-ext><p>End</p>"
        )
        result = xhtml_to_markdown(xhtml)
        assert "Start" in result
        assert "kept text" in result
        assert "End" in result

    def test_unhandled_outer_with_handled_inner_drops_outer_params(self):
        """Unhandled macro wrapping a handled one: params gone, inner kept."""
        xhtml = (
            '<ac:structured-macro ac:name="unknown-outer">'
            '<ac:parameter ac:name="server">SECRETSERVER</ac:parameter>'
            "<ac:rich-text-body>"
            '<ac:structured-macro ac:name="status">'
            '<ac:parameter ac:name="title">OK</ac:parameter>'
            "</ac:structured-macro>"
            "</ac:rich-text-body></ac:structured-macro><p>After</p>"
        )
        result = xhtml_to_markdown(xhtml)
        assert "SECRETSERVER" not in result
        assert "`OK`" in result
        assert "After" in result

    def test_table_cell_pipe_is_escaped(self):
        """A literal pipe in a cell must not create extra columns."""
        xhtml = (
            "<table><tr><th>K</th></tr><tr><td><p>a | b</p><p>c</p></td></tr></table>"
        )
        result = xhtml_to_markdown(xhtml)
        assert "| a \\| b<br>c |" in result
