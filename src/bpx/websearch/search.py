"""DuckDuckGo search via ddgs (§11). Sync library; the agent calls it off the event loop."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


def web_search(query: str, max_results: int = 6) -> list[SearchResult]:
    """Top results for a query, or [] on any failure (rate limits, no network)."""
    from ddgs import DDGS

    try:
        hits = DDGS().text(query, max_results=max_results)
    except Exception:
        return []
    out = []
    for h in hits:
        url = h.get("href") or h.get("url") or ""
        if url:
            out.append(SearchResult(h.get("title", ""), url, h.get("body", "")))
    return out
