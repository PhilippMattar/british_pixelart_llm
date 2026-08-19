"""Retrieval orchestrator (PLAN.md §5, §10, §11): one judge routes a query to no-retrieval /
local-docs / web-search, then dispatches to the right pipeline. This is the single control path
the two electives share — RAG and web search hang off the same decision, never forked.
"""

from __future__ import annotations

from .llm import Message
from .rag import pipeline as rag
from .rag.embed import Embedder
from .store import Store
from .websearch import agent as websearch
from .websearch.agent import StatusFn


def _history_snippet(history: list[Message], turns: int = 4) -> str:
    recent = [m for m in history if m.role in ("user", "assistant") and m.content][-turns:]
    return "\n".join(f"{m.role.capitalize()}: {m.content}" for m in recent) or "(none)"


async def judge(
    client, query: str, history: list[Message], library: str, *, web_enabled: bool
) -> str:
    """Route to 'local', 'web', or 'none'. `web_enabled` gates the web option."""
    web_line = (
        "- WEB if it needs current, real-time, or external information that isn't in the documents "
        "and isn't stable general knowledge (news, prices, weather, recent events, specific facts "
        "to look up online).\n"
        if web_enabled
        else ""
    )
    prompt = (
        "The user has uploaded these documents (title: opening excerpt):\n"
        f"{library}\n\n"
        "Decide how to answer the user's latest message. Reply with ONE word:\n"
        "- LOCAL if it could be answered using those documents.\n"
        f"{web_line}"
        "- DIRECT if it is stable general knowledge, chit-chat, or about the assistant.\n\n"
        f"Recent context:\n{_history_snippet(history)}\n\nUser message: {query}\n\nOne word:"
    )
    try:
        reply = (await client.complete([Message("user", prompt)])).strip().upper()
    except Exception:
        return "none"
    if "LOCAL" in reply:
        return "local"
    if web_enabled and "WEB" in reply:
        return "web"
    return "none"


async def build_context(
    client,
    embedder: Embedder,
    store: Store,
    project_id: int,
    query: str,
    history: list[Message],
    *,
    web_enabled: bool = False,
    force_route: str | None = None,
    on_status: StatusFn | None = None,
):
    """Judge + dispatch. Returns a source-tagged context (RagResult/WebResult, both have `.context`
    and `.sources`) or None for no-retrieval. `force_route="web"` skips the judge (the /search
    command)."""
    if force_route == "web":
        return await websearch.build_web_context(client, query, history, on_status)

    has_docs = bool(store.list_documents(project_id))
    if not has_docs and not web_enabled:
        return None  # nothing to route to
    route = await judge(
        client, query, history, rag.library_summary(store, project_id), web_enabled=web_enabled
    )
    if route == "local" and has_docs:
        return await rag.build_local_context(client, embedder, store, project_id, query, history)
    if route == "web" and web_enabled:
        return await websearch.build_web_context(client, query, history, on_status)
    return None
