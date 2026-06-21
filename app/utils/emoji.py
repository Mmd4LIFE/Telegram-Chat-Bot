"""Lightweight emoji extraction (no external dependency).

Covers the main Unicode emoji blocks. Good enough to learn a user's favourite
emojis for personalization without pulling in a heavy library.
"""
import re

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"  # symbols, pictographs, supplemental, extended-A
    "\U00002600-\U000027BF"  # misc symbols & dingbats
    "\U0001F1E6-\U0001F1FF"  # regional indicators (flags)
    "\U00002190-\U000021FF"  # arrows
    "\U00002B00-\U00002BFF"  # misc symbols & arrows
    "\U0000FE00-\U0000FE0F"  # variation selectors
    "\U0001F000-\U0001F0FF"  # mahjong/dominoes/cards
    "\U00002700-\U000027BF"
    "]",
    flags=re.UNICODE,
)


def extract_emojis(text: str | None) -> list[str]:
    """Return the list of emoji characters found in `text` (with repeats)."""
    if not text:
        return []
    # drop variation selectors so '❤️' and '❤' count the same
    found = [c for c in _EMOJI_RE.findall(text) if c not in "︎️"]
    return found
