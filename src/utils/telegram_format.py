"""Convert LLM Markdown output to Telegram-compatible HTML.

Telegram supports a limited subset of HTML: <b>, <i>, <code>, <pre>,
<a href="">, <s>, <u>, <blockquote>.  This module converts common
Markdown patterns to that subset so messages render nicely in Telegram.
"""

from __future__ import annotations

import re
from html import escape


def md_to_telegram_html(text: str) -> str:
    """Convert Markdown-formatted text to Telegram HTML.

    Handles: bold, italic, inline code, code blocks, headers, links,
    strikethrough, and blockquotes.  HTML special characters are escaped
    first so the output is safe for ``parse_mode="HTML"``.

    Args:
        text: Raw Markdown text from the LLM.

    Returns:
        Telegram-safe HTML string.
    """
    # 1. Extract code blocks and inline code to protect them from other transformations
    code_blocks: list[str] = []
    inline_codes: list[str] = []

    def _stash_code_block(m: re.Match) -> str:
        lang = m.group(1) or ""
        code = escape(m.group(2))
        code_blocks.append(
            f"<pre>{code}</pre>" if not lang else f"<pre><code>{code}</code></pre>"
        )
        return f"\x00CODEBLOCK{len(code_blocks) - 1}\x00"

    def _stash_inline_code(m: re.Match) -> str:
        code = escape(m.group(1))
        inline_codes.append(f"<code>{code}</code>")
        return f"\x00INLINE{len(inline_codes) - 1}\x00"

    # Extract fenced code blocks (``` ... ```)
    text = re.sub(r"```(\w*)\n(.*?)```", _stash_code_block, text, flags=re.DOTALL)
    # Extract inline code (` ... `)
    text = re.sub(r"`([^`\n]+)`", _stash_inline_code, text)

    # 2. Escape HTML special characters in the remaining text
    text = escape(text)

    # 3. Markdown headings → bold (### Header → <b>Header</b>)
    text = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    # 4. Bold: **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)

    # 5. Italic: *text* or _text_ (but not inside words like some_var_name)
    text = re.sub(r"(?<!\w)\*([^\*\n]+?)\*(?!\w)", r"<i>\1</i>", text)
    text = re.sub(r"(?<!\w)_([^_\n]+?)_(?!\w)", r"<i>\1</i>", text)

    # 6. Strikethrough: ~~text~~
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)

    # 7. Links: [text](url)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', text)

    # 8. Blockquotes: > text
    text = re.sub(
        r"^&gt;\s?(.+)$", r"<blockquote>\1</blockquote>", text, flags=re.MULTILINE
    )
    # Merge consecutive blockquote tags
    text = re.sub(r"</blockquote>\n<blockquote>", "\n", text)

    # 9. Restore code blocks and inline code
    for i, block in enumerate(code_blocks):
        text = text.replace(f"\x00CODEBLOCK{i}\x00", block)
    for i, code in enumerate(inline_codes):
        text = text.replace(f"\x00INLINE{i}\x00", code)

    return text
