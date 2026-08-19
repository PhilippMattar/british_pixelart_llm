"""The agentic web-search loop (§11): search -> decide -> fetch (or follow an in-page link, or
re-search) -> summarize into a source-tagged context. Control calls go through a NON-thinking
client. Every step is fail-soft so a blocked page or a flaky model reply can't wedge the loop.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass

from ..llm import Message
from .fetch import Page, fetch_page
from .search import web_search

FETCH_BUDGET = 6  # max pages actually fetched
MAX_STEPS = 10  # max decision iterations (search + fetch)
TOP_RESULTS = 6
_NOTE_CHARS = 400  # per-page snippet shown to the decision step
_SUMMARY_PAGE_CHARS = 2500  # per-page text fed to the final summarizer
_ACTION = re.compile(r"\b(ANSWER|FETCH|SEARCH)\b", re.IGNORECASE)

StatusFn = Callable[[str], None]


@dataclass(frozen=True)
class WebResult:
    context: str  # system-prompt block to inject
    sources: list[str]  # ["[1] https://…", …]


def _status(on_status: StatusFn | None, message: str) -> None:
    if on_status:
        on_status(message)


async def _make_query(client, query: str) -> str:
    prompt = (
        "Turn the user's question into a concise web search query (a few keywords). "
        f"Output ONLY the query.\n\nQuestion: {query}\n\nSearch query:"
    )
    try:
        out = (await client.complete([Message("user", prompt)])).strip().strip('"')
    except Exception:
        out = ""
    return out or query


async def _decide(client, query: str, pages: list[Page], frontier: list[tuple[str, str]]):
    """Return the next action: ("answer", None) | ("fetch", idx|None) | ("search", query)."""
    notes = "\n".join(f"- {p.url}: {p.text[:_NOTE_CHARS]}" for p in pages) or "(nothing read yet)"
    cands = "\n".join(f"{i}: {label} — {url}" for i, (label, url) in enumerate(frontier[:20]))
    prompt = (
        f"You are researching to answer: {query}\n\n"
        f"Notes gathered so far:\n{notes}\n\n"
        f"Links you can fetch (some were found inside pages you already read):\n{cands}\n\n"
        "Choose ONE next action. Reply with EXACTLY one line:\n"
        "ANSWER — the notes already answer the question\n"
        "FETCH <number> — read a candidate link (pick the one most likely to answer)\n"
        "SEARCH <query> — run a new web search for different terms"
    )
    try:
        reply = (await client.complete([Message("user", prompt)])).strip()
    except Exception:
        return ("answer", None)
    match = _ACTION.search(reply)
    action = match.group(1).lower() if match else "fetch"
    if action == "search":
        q = re.sub(r"(?is)^.*?SEARCH\s*", "", reply).splitlines()[0].strip().strip('"')
        return ("search", q or None)
    if action == "answer":
        return ("answer", None)
    num = re.search(r"\d+", reply)
    return ("fetch", int(num.group()) if num else None)


def _pick_fetch(frontier, visited, idx):
    """The chosen candidate if valid+unvisited, else the first unvisited one, else None."""
    if idx is not None and 0 <= idx < len(frontier) and frontier[idx][1] not in visited:
        return frontier[idx]
    return next((cand for cand in frontier if cand[1] not in visited), None)


async def _summarize(client, query: str, numbered: list[tuple[int, Page]]) -> str:
    sources = "\n\n".join(f"[{n}] {p.url}\n{p.text[:_SUMMARY_PAGE_CHARS]}" for n, p in numbered)
    prompt = (
        "From the numbered web sources, extract the information relevant to the question as concise "
        "bullet points, tagging each with its source number like [1]. Include only what is relevant; "
        f"do not invent anything.\n\nQuestion: {query}\n\nSources:\n{sources}\n\nRelevant notes:"
    )
    try:
        out = (await client.complete([Message("user", prompt)])).strip()
    except Exception:
        out = ""
    return out or sources


async def build_web_context(
    client, query: str, history: list[Message], on_status: StatusFn | None = None
) -> WebResult | None:
    """Run the search loop and return an injectable source-tagged context, or None if nothing
    usable was found."""
    search_query = await _make_query(client, query)
    _status(on_status, f"🔎 Searching: {search_query}")
    results = await asyncio.to_thread(web_search, search_query, TOP_RESULTS)
    frontier: list[tuple[str, str]] = [(r.title or r.url, r.url) for r in results]
    if not frontier:
        return None

    pages: list[Page] = []
    visited: set[str] = set()
    fetches = 0
    for _ in range(MAX_STEPS):
        if fetches >= FETCH_BUDGET:
            break
        action, arg = await _decide(client, query, pages, frontier)
        if action == "answer" and pages:
            break
        if action == "search" and arg:
            _status(on_status, f"🔎 Searching: {arg}")
            more = await asyncio.to_thread(web_search, arg, TOP_RESULTS)
            frontier.extend((r.title or r.url, r.url) for r in more if r.url not in visited)
            continue
        target = _pick_fetch(frontier, visited, arg if action == "fetch" else None)
        if target is None:
            break
        _, url = target
        visited.add(url)
        _status(on_status, f"📄 Reading: {url}")
        page = await fetch_page(url)
        fetches += 1
        if page:
            pages.append(page)
            # In-page links become new candidates — the "traverse links within pages" requirement.
            frontier.extend((anchor, href) for anchor, href in page.links if href not in visited)

    if not pages:
        return None
    _status(on_status, "✍️ Summarising sources…")
    numbered = list(enumerate(pages, start=1))
    summary = await _summarize(client, query, numbered)
    sources = [f"[{n}] {p.url}" for n, p in numbered]
    context = (
        "Use the following web sources to answer the user's question, and cite them inline as [n]. "
        "If they do not contain the answer, say so plainly.\n\n"
        f"{summary}\n\nSources:\n" + "\n".join(sources)
    )
    return WebResult(context=context, sources=sources)
