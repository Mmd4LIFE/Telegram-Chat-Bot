"""Convert model Markdown output into Telegram-safe HTML.

Telegram's HTML parse mode does NOT understand Markdown (`**bold**`, `# heading`,
fenced code, etc.), so we translate the common Markdown the models emit into the
small subset of HTML tags Telegram supports, while escaping everything else so
stray `<`, `>` and `&` can never break the message.
"""
from __future__ import annotations

import html
import re

_CODE_BLOCK = re.compile(r"```[ \t]*([\w+-]*)\n?(.*?)```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*(.+?)\s*#*$", re.MULTILINE)
_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_BOLD_ALT = re.compile(r"__(.+?)__", re.DOTALL)
_ITALIC = re.compile(r"(?<![\*\w])\*(?!\s)([^\*\n]+?)\*(?![\*\w])")
_ITALIC_ALT = re.compile(r"(?<![_\w])_(?!\s)([^_\n]+?)_(?![_\w])")
_STRIKE = re.compile(r"~~(.+?)~~", re.DOTALL)


def to_telegram_html(text: str) -> str:
    if not text:
        return ""

    stash: list[str] = []

    def keep(fragment: str) -> str:
        stash.append(fragment)
        return f"\x00{len(stash) - 1}\x00"

    # 1) Pull code out first so its contents are never markdown-processed.
    def _block(m: re.Match) -> str:
        code = m.group(2).rstrip("\n")
        return keep(f"<pre>{html.escape(code)}</pre>")

    text = _CODE_BLOCK.sub(_block, text)
    text = _INLINE_CODE.sub(lambda m: keep(f"<code>{html.escape(m.group(1))}</code>"), text)

    # 2) Escape everything else.
    text = html.escape(text, quote=False)

    # 3) Re-introduce the supported inline formatting.
    text = _LINK.sub(lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>', text)
    text = _HEADING.sub(lambda m: f"<b>{m.group(1)}</b>", text)
    text = _BOLD.sub(r"<b>\1</b>", text)
    text = _BOLD_ALT.sub(r"<b>\1</b>", text)
    text = _STRIKE.sub(r"<s>\1</s>", text)
    text = _ITALIC.sub(r"<i>\1</i>", text)
    text = _ITALIC_ALT.sub(r"<i>\1</i>", text)

    # 4) Restore code fragments.
    for i, fragment in enumerate(stash):
        text = text.replace(f"\x00{i}\x00", fragment)

    return text
