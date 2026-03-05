"""Tests for the Markdown → Telegram HTML converter."""

from __future__ import annotations

from src.utils.telegram_format import md_to_telegram_html


class TestMdToTelegramHtml:
    def test_bold_asterisks(self) -> None:
        assert md_to_telegram_html("**hello**") == "<b>hello</b>"

    def test_bold_underscores(self) -> None:
        assert md_to_telegram_html("__hello__") == "<b>hello</b>"

    def test_italic_asterisk(self) -> None:
        assert md_to_telegram_html("*hello*") == "<i>hello</i>"

    def test_italic_underscore(self) -> None:
        assert md_to_telegram_html("_hello_") == "<i>hello</i>"

    def test_underscore_in_word_not_italic(self) -> None:
        result = md_to_telegram_html("some_var_name")
        assert "<i>" not in result

    def test_inline_code(self) -> None:
        assert (
            md_to_telegram_html("`print('hi')`") == "<code>print(&#x27;hi&#x27;)</code>"
        )

    def test_code_block(self) -> None:
        text = "```python\nprint('hi')\n```"
        result = md_to_telegram_html(text)
        assert "<pre>" in result
        assert "print(&#x27;hi&#x27;)" in result

    def test_heading(self) -> None:
        assert md_to_telegram_html("## Title") == "<b>Title</b>"

    def test_strikethrough(self) -> None:
        assert md_to_telegram_html("~~removed~~") == "<s>removed</s>"

    def test_link(self) -> None:
        result = md_to_telegram_html("[click](https://example.com)")
        assert result == '<a href="https://example.com">click</a>'

    def test_blockquote(self) -> None:
        result = md_to_telegram_html("> quoted text")
        assert "<blockquote>" in result
        assert "quoted text" in result

    def test_html_entities_escaped(self) -> None:
        result = md_to_telegram_html("1 < 2 & 3 > 0")
        assert "&lt;" in result
        assert "&amp;" in result
        assert "&gt;" in result

    def test_mixed_formatting(self) -> None:
        text = "# Hello\n\nThis is **bold** and *italic*."
        result = md_to_telegram_html(text)
        assert "<b>Hello</b>" in result
        assert "<b>bold</b>" in result
        assert "<i>italic</i>" in result

    def test_plain_text_passthrough(self) -> None:
        text = "Just a normal message with no formatting."
        result = md_to_telegram_html(text)
        assert result == text

    def test_code_block_preserves_html_chars(self) -> None:
        text = "```\nif (a < b) { return a; }\n```"
        result = md_to_telegram_html(text)
        assert "&lt;" in result
        assert "&gt;" not in result or "<pre>" in result

    def test_consecutive_blockquotes_merged(self) -> None:
        text = "> line one\n> line two"
        result = md_to_telegram_html(text)
        assert result.count("<blockquote>") == 1
