"""Lyrics extraction for music files.

Strategy:
  1. If the audio carries performer + title metadata, look the lyrics up via free
     no-key APIs — LRCLIB (fast, reliable) first, then lyrics.ovh as a fallback.
  2. Otherwise (or if not found), the caller transcribes the audio with Whisper —
     which captures the sung lyrics directly.
"""
from __future__ import annotations

import httpx

from app.logger import get_logger

log = get_logger(__name__)


async def _from_lrclib(performer: str, title: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://lrclib.net/api/get",
                params={"artist_name": performer, "track_name": title},
                headers={"User-Agent": "TelegramChatBot (lyrics lookup)"},
            )
        if resp.status_code == 200:
            lyrics = (resp.json() or {}).get("plainLyrics") or ""
            return lyrics.replace("\r\n", "\n").strip() or None
    except Exception as e:  # noqa: BLE001
        log.warning("LRCLIB lookup failed: %s", e)
    return None


async def _from_lyrics_ovh(performer: str, title: str) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(f"https://api.lyrics.ovh/v1/{performer}/{title}")
        if resp.status_code == 200:
            lyrics = (resp.json() or {}).get("lyrics") or ""
            return lyrics.replace("\r\n", "\n").strip() or None
    except Exception as e:  # noqa: BLE001
        log.warning("lyrics.ovh lookup failed: %s", e)
    return None


async def fetch_lyrics(performer: str, title: str) -> str | None:
    """Look up lyrics by artist + title via free no-key APIs."""
    if not performer or not title:
        return None
    performer, title = performer.strip(), title.strip()
    return await _from_lrclib(performer, title) or await _from_lyrics_ovh(performer, title)
