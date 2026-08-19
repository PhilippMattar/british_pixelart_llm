"""Fetch a URL and extract its main text + in-page links (§11).

httpx for the request, trafilatura for boilerplate-free extraction. Built to be resilient: many
sites bot-block (403) or are JS-only (empty extraction), so failures return None and the agent
just tries the next candidate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# A realistic browser UA — a thin UA gets 403'd by many sites.
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"
)
_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
MAX_TEXT_CHARS = 6000
_MIN_TEXT_CHARS = 200


@dataclass(frozen=True)
class Page:
    url: str
    text: str
    links: list[tuple[str, str]]  # (anchor text, absolute url) found within the page


async def fetch_page(url: str, max_chars: int = MAX_TEXT_CHARS) -> Page | None:
    """Fetch + extract one page, or None if it can't be read (blocked, empty, error, timeout)."""
    import httpx
    import trafilatura

    try:
        async with httpx.AsyncClient(
            timeout=15, follow_redirects=True, headers={"User-Agent": _UA}
        ) as client:
            resp = await client.get(url)
    except Exception:
        return None
    if resp.status_code != 200 or "text/html" not in resp.headers.get("content-type", "text/html"):
        return None
    text = trafilatura.extract(resp.text) or ""
    if len(text) < _MIN_TEXT_CHARS:
        return None
    linked = trafilatura.extract(resp.text, include_links=True) or ""
    # Dedup in-page links, drop self-links, keep order.
    seen: set[str] = {url}
    links: list[tuple[str, str]] = []
    for anchor, href in _MD_LINK.findall(linked):
        if href not in seen:
            seen.add(href)
            links.append((anchor.strip()[:80], href))
    return Page(url=url, text=text[:max_chars], links=links[:40])
