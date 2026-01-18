"""Tests for adf_helper module."""

import pytest

from confluence_assistant_skills import (
    adf_to_markdown,
    adf_to_text,
    create_adf_doc,
    create_blockquote,
    create_bullet_list,
    create_code_block,
    create_heading,
    create_link,
    create_ordered_list,
    create_paragraph,
    create_rule,
    create_table,
    create_text,
    markdown_to_adf,
    text_to_adf,
    validate_adf,
)


class TestCreateAdfDoc:
    """Tests for create_adf_doc."""

    def test_creates_doc_structure(self):
        content = [create_paragraph(text="Hello")]
        doc = create_adf_doc(content)

        assert doc["type"] == "doc"
        assert doc["version"] == 1
        assert len(doc["content"]) == 1

    def test_empty_content(self):
        doc = create_adf_doc([])
        assert doc["content"] == []


class TestCreateParagraph:
    """Tests for create_paragraph."""

    def test_with_text(self):
        para = create_paragraph(text="Hello, World!")
        assert para["type"] == "paragraph"
        assert len(para["content"]) == 1
        assert para["content"][0]["text"] == "Hello, World!"

    def test_with_content(self):
        content = [create_text("Bold", marks=[{"type": "strong"}])]
        para = create_paragraph(content=content)
        assert para["content"][0]["marks"][0]["type"] == "strong"


class TestCreateText:
    """Tests for create_text."""

    def test_simple_text(self):
        text = create_text("Hello")
        assert text["type"] == "text"
        assert text["text"] == "Hello"
        assert "marks" not in text

    def test_with_marks(self):
        text = create_text("Bold", marks=[{"type": "strong"}])
        assert text["marks"][0]["type"] == "strong"


class TestCreateHeading:
    """Tests for create_heading."""

    def test_heading_level_1(self):
        heading = create_heading("Title", level=1)
        assert heading["type"] == "heading"
        assert heading["attrs"]["level"] == 1
        assert heading["content"][0]["text"] == "Title"

    def test_clamps_level(self):
        heading = create_heading("Title", level=10)
        assert heading["attrs"]["level"] == 6

        heading = create_heading("Title", level=0)
        assert heading["attrs"]["level"] == 1


class TestCreateLists:
    """Tests for list creation functions."""

    def test_bullet_list(self):
        items = ["Item 1", "Item 2", "Item 3"]
        bullet_list = create_bullet_list(items)

        assert bullet_list["type"] == "bulletList"
        assert len(bullet_list["content"]) == 3
        assert bullet_list["content"][0]["type"] == "listItem"

    def test_ordered_list(self):
        items = ["First", "Second"]
        ordered_list = create_ordered_list(items)

        assert ordered_list["type"] == "orderedList"
        assert ordered_list["attrs"]["order"] == 1

    def test_ordered_list_custom_start(self):
        ordered_list = create_ordered_list(["Item"], start=5)
        assert ordered_list["attrs"]["order"] == 5


class TestCreateCodeBlock:
    """Tests for create_code_block."""

    def test_without_language(self):
        code = create_code_block("print('hello')")
        assert code["type"] == "codeBlock"
        assert "attrs" not in code

    def test_with_language(self):
        code = create_code_block("print('hello')", language="python")
        assert code["attrs"]["language"] == "python"


class TestCreateBlockquote:
    """Tests for create_blockquote."""

    def test_creates_blockquote(self):
        quote = create_blockquote("Quote text")
        assert quote["type"] == "blockquote"
        assert quote["content"][0]["type"] == "paragraph"


class TestCreateRule:
    """Tests for create_rule."""

    def test_creates_rule(self):
        rule = create_rule()
        assert rule["type"] == "rule"


class TestCreateTable:
    """Tests for create_table."""

    def test_table_with_header(self):
        rows = [["Header 1", "Header 2"], ["Value 1", "Value 2"]]
        table = create_table(rows, header=True)

        assert table["type"] == "table"
        assert table["content"][0]["content"][0]["type"] == "tableHeader"
        assert table["content"][1]["content"][0]["type"] == "tableCell"

    def test_table_without_header(self):
        rows = [["A", "B"], ["C", "D"]]
        table = create_table(rows, header=False)

        assert table["content"][0]["content"][0]["type"] == "tableCell"


class TestCreateLink:
    """Tests for create_link."""

    def test_creates_link(self):
        link = create_link("Click here", "https://example.com")
        assert link["text"] == "Click here"
        assert link["marks"][0]["type"] == "link"
        assert link["marks"][0]["attrs"]["href"] == "https://example.com"


class TestTextToAdf:
    """Tests for text_to_adf."""

    def test_simple_text(self):
        adf = text_to_adf("Hello, World!")
        assert adf["type"] == "doc"
        assert adf["content"][0]["content"][0]["text"] == "Hello, World!"

    def test_paragraphs(self):
        adf = text_to_adf("Para 1\n\nPara 2")
        assert len(adf["content"]) == 2

    def test_empty_text(self):
        adf = text_to_adf("")
        assert adf["type"] == "doc"


class TestMarkdownToAdf:
    """Tests for markdown_to_adf."""

    def test_heading(self):
        adf = markdown_to_adf("# Title")
        assert adf["content"][0]["type"] == "heading"
        assert adf["content"][0]["attrs"]["level"] == 1

    def test_bold(self):
        adf = markdown_to_adf("This is **bold** text")
        content = adf["content"][0]["content"]
        assert any(
            node.get("marks", [{}])[0].get("type") == "strong"
            for node in content
            if "marks" in node
        )

    def test_bullet_list(self):
        adf = markdown_to_adf("- Item 1\n- Item 2")
        assert adf["content"][0]["type"] == "bulletList"

    def test_code_block(self):
        adf = markdown_to_adf("```python\nprint('hello')\n```")
        assert adf["content"][0]["type"] == "codeBlock"
        assert adf["content"][0]["attrs"]["language"] == "python"

    def test_horizontal_rule(self):
        adf = markdown_to_adf("---")
        assert adf["content"][0]["type"] == "rule"


class TestAdfToText:
    """Tests for adf_to_text."""

    def test_simple_paragraph(self):
        adf = create_adf_doc([create_paragraph(text="Hello")])
        assert adf_to_text(adf) == "Hello"

    def test_multiple_paragraphs(self):
        adf = create_adf_doc(
            [
                create_paragraph(text="Para 1"),
                create_paragraph(text="Para 2"),
            ]
        )
        text = adf_to_text(adf)
        assert "Para 1" in text
        assert "Para 2" in text

    def test_empty_adf(self):
        assert adf_to_text({}) == ""
        assert adf_to_text(None) == ""


class TestAdfToMarkdown:
    """Tests for adf_to_markdown."""

    def test_heading(self):
        adf = create_adf_doc([create_heading("Title", level=2)])
        md = adf_to_markdown(adf)
        assert md == "## Title"

    def test_bullet_list(self):
        adf = create_adf_doc([create_bullet_list(["Item 1", "Item 2"])])
        md = adf_to_markdown(adf)
        assert "- Item 1" in md
        assert "- Item 2" in md

    def test_code_block(self):
        adf = create_adf_doc([create_code_block("code", language="python")])
        md = adf_to_markdown(adf)
        assert "```python" in md
        assert "code" in md


class TestValidateAdf:
    """Tests for validate_adf."""

    def test_valid_adf(self):
        adf = create_adf_doc([create_paragraph(text="Hello")])
        assert validate_adf(adf) is True

    def test_invalid_type(self):
        with pytest.raises(ValueError):
            validate_adf("not a dict")

    def test_missing_doc_type(self):
        with pytest.raises(ValueError):
            validate_adf({"type": "paragraph", "content": []})

    def test_missing_content(self):
        with pytest.raises(ValueError):
            validate_adf({"type": "doc"})
