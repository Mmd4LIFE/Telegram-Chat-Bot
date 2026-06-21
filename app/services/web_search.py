"""Web search + AI summarization for the `@web` command.

Uses DuckDuckGo (free, no API key) to fetch results, then summarizes them with
the LLM and returns an answer plus the source links. Best-effort: any failure
degrades to a clear message rather than crashing the chat.
"""
from __future__ import annotations

import asyncio

import httpx

from app.config import settings
from app.logger import get_logger
from app.services.openai_service import client

log = get_logger(__name__)

try:  # the package is `ddgs` (successor of duckduckgo-search)
    from ddgs import DDGS
except Exception:  # noqa: BLE001
    try:
        from duckduckgo_search import DDGS  # type: ignore
    except Exception:  # noqa: BLE001
        DDGS = None


def _normalize(rows) -> list[dict]:
    out = []
    for r in rows or []:
        out.append(
            {
                "title": r.get("title") or "",
                "href": r.get("href") or r.get("url") or "",
                "body": r.get("body") or "",
            }
        )
    return out


def _search_blocking(query: str, max_results: int) -> list[dict]:
    """Try several backends; DuckDuckGo rate-limits aggressively from servers."""
    with DDGS() as ddg:
        for backend in ("auto", "html", "lite"):
            try:
                rows = ddg.text(query, max_results=max_results, backend=backend)
            except TypeError:  # older signature without `backend`
                rows = ddg.text(query, max_results=max_results)
            except Exception as e:  # noqa: BLE001
                log.warning("ddg backend %s failed: %s", backend, e)
                continue
            results = _normalize(rows)
            if results:
                return results
    return []


async def _google(query: str, max_results: int) -> list[dict]:
    """Google Programmable Search (Custom Search JSON API). Reliable, needs a key."""
    if not (settings.google_api_key and settings.google_cx):
        return []
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": settings.google_api_key,
                    "cx": settings.google_cx,
                    "q": query,
                    "num": min(max_results, 10),
                },
            )
        if resp.status_code != 200:
            log.warning("Google CSE returned %s: %s", resp.status_code, resp.text[:200])
            return []
        items = (resp.json() or {}).get("items", []) or []
        return [
            {"title": it.get("title", ""), "href": it.get("link", ""), "body": it.get("snippet", "")}
            for it in items
        ]
    except Exception as e:  # noqa: BLE001
        log.warning("Google CSE failed: %s", e)
        return []


async def _duckduckgo(query: str, max_results: int, retries: int = 3) -> list[dict]:
    if DDGS is None:
        return []
    for attempt in range(1, retries + 1):
        try:
            results = await asyncio.to_thread(_search_blocking, query, max_results)
            if results:
                return results
        except Exception as e:  # noqa: BLE001
            log.warning("web search attempt %s failed: %s", attempt, e)
        if attempt < retries:
            await asyncio.sleep(1.5 * attempt)
    return []


async def search(query: str, max_results: int = 6) -> list[dict]:
    """Return web results: list of {title, href, body}. Google first (if keyed),
    then DuckDuckGo as a no-key fallback."""
    return await _google(query, max_results) or await _duckduckgo(query, max_results)


async def answer(query: str) -> tuple[str, list[dict]] | None:
    """Search the web for `query`, summarize with the LLM, return (answer, results)."""
    results = await search(query, max_results=6)
    if not results:
        return None

    context = "\n\n".join(
        f"[{i + 1}] {r['title']}\n{r['body']}\n{r['href']}"
        for i, r in enumerate(results)
    )
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a web research assistant. Using ONLY the search "
                    "results provided, answer the user's question accurately and "
                    "concisely. Cite sources inline like [1], [2]. If the results "
                    "don't contain the answer, say so."
                ),
            },
            {"role": "user", "content": f"Question: {query}\n\nSearch results:\n{context}"},
        ],
        temperature=0.3,
        max_tokens=600,
    )
    return (resp.choices[0].message.content or "").strip(), results
