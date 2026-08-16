"""Adaptive-RAG orchestration (§10): judge -> rewrite -> multiturn retrieval -> summarize.

Ingestion embeds chunks into the store. At query time a judge decides whether the user's docs
are needed; if so, a rewriter turns the question into a search query, retrieval pulls the nearest
chunks (brute-force cosine), and — if an LLM judges the context insufficient — it rewrites and
retrieves again (up to MAX_ROUNDS). A summarizer compresses the hits into a source-tagged block
that the app injects so the final answer cites its sources.

Every control call goes through a NON-thinking client (`complete`), so the pipeline stays fast.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from ..llm import Message
from ..store import RagChunk, Store
from .chunk import chunk_text, read_document
from .embed import Embedder, from_blob, to_blob

TOP_K = 5
MAX_ROUNDS = 3
EMBED_BATCH = 64
_SUMMARY_CHUNK_CHARS = 1200  # cap each chunk fed to the summarizer


@dataclass(frozen=True)
class RagResult:
    context: str  # system-prompt block to inject
    sources: list[str]  # ["[1] title (part 3)", ...] for the toast/citation legend


# --------------------------------------------------------------------------- ingestion
async def ingest_document(
    store: Store, embedder: Embedder, project_id: int, path: str
) -> tuple[int, int]:
    """Read + chunk + embed a document into the store. Returns (document_id, n_chunks)."""
    text = read_document(path)
    pieces = chunk_text(text)
    if not pieces:
        raise ValueError(f"No extractable text in {path}")
    doc_id = store.add_document(project_id, path, Path(path).name)
    rows: list[tuple[int, str, bytes]] = []
    for start in range(0, len(pieces), EMBED_BATCH):
        batch = pieces[start : start + EMBED_BATCH]
        vectors = await embedder.embed(batch)
        for offset, (piece, vec) in enumerate(zip(batch, vectors)):
            rows.append((start + offset, piece, to_blob(vec)))
    store.add_chunks(doc_id, project_id, rows)
    return doc_id, len(pieces)


# --------------------------------------------------------------------------- retrieval
def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


async def retrieve(
    store: Store, embedder: Embedder, project_id: int, query: str, k: int = TOP_K
) -> list[RagChunk]:
    chunks = store.rag_chunks_for_search(project_id)
    if not chunks:
        return []
    qvec = await embedder.embed_one(query)
    ranked = sorted(chunks, key=lambda c: cosine(qvec, from_blob(c.embedding)), reverse=True)
    return ranked[:k]


# --------------------------------------------------------------------------- LLM control steps
def _history_snippet(history: list[Message], turns: int = 4) -> str:
    recent = [m for m in history if m.role in ("user", "assistant") and m.content][-turns:]
    return "\n".join(f"{m.role.capitalize()}: {m.content}" for m in recent) or "(none)"


def library_summary(store: Store, project_id: int) -> str:
    """A short 'what's on file' description (title + opening snippet per document) so the judge
    knows what the user's documents are about."""
    firsts: dict[str, str] = {}
    for chunk in sorted(store.rag_chunks_for_search(project_id), key=lambda c: c.chunk_index):
        firsts.setdefault(chunk.document_title, chunk.content[:200])
    return "\n".join(f"- {title}: {snippet}…" for title, snippet in firsts.items()) or "(none)"


async def judge(client, query: str, history: list[Message], library: str) -> str:
    """Route the query: 'local' (needs the user's docs), else 'none'. (Web arrives in §11.)"""
    prompt = (
        "The user has uploaded these documents (title: opening excerpt):\n"
        f"{library}\n\n"
        "Decide how to answer the user's latest message. Reply with ONE word:\n"
        "- LOCAL if the message could be answered using these documents — their topics, facts, "
        "or figures — or explicitly refers to them.\n"
        "- DIRECT if it is general knowledge, chit-chat, about the assistant, or unrelated to the "
        "documents above.\n\n"
        f"Recent context:\n{_history_snippet(history)}\n\nUser message: {query}\n\nOne word:"
    )
    try:
        reply = (await client.complete([Message("user", prompt)])).strip().upper()
    except Exception:
        return "none"
    return "local" if "LOCAL" in reply else "none"


async def rewrite(client, query: str, history: list[Message], note: str = "") -> str:
    hint = f"\n{note}" if note else ""
    prompt = (
        "Rewrite the user's question into a concise search query for retrieving passages from "
        "their documents. Resolve pronouns/references using the context. Output ONLY the query."
        f"{hint}\n\nContext:\n{_history_snippet(history)}\n\nQuestion: {query}\n\nSearch query:"
    )
    try:
        out = (await client.complete([Message("user", prompt)])).strip().strip('"')
    except Exception:
        out = ""
    return out or query


async def sufficient(client, query: str, chunks: list[RagChunk]) -> bool:
    passages = "\n\n".join(c.content[:_SUMMARY_CHUNK_CHARS] for c in chunks)
    prompt = (
        f"Passages:\n{passages}\n\nQuestion: {query}\n\n"
        "Do the passages contain enough information to answer the question? Reply only YES or NO."
    )
    try:
        reply = (await client.complete([Message("user", prompt)])).strip().upper()
    except Exception:
        return True  # don't loop forever on errors
    return "YES" in reply


async def summarize(client, query: str, numbered: list[tuple[int, RagChunk]]) -> str:
    sources = "\n\n".join(f"[{n}] {c.content[:_SUMMARY_CHUNK_CHARS]}" for n, c in numbered)
    prompt = (
        "From the numbered sources below, extract the information relevant to the question as "
        "concise bullet points. Tag each bullet with its source number(s) like [1]. Include only "
        f"what is relevant; do not invent anything.\n\nQuestion: {query}\n\nSources:\n{sources}\n\n"
        "Relevant notes:"
    )
    try:
        out = (await client.complete([Message("user", prompt)])).strip()
    except Exception:
        out = ""
    # Fall back to the raw tagged sources if summarization fails.
    return out or sources


# --------------------------------------------------------------------------- orchestration
async def build_context(
    client, embedder: Embedder, store: Store, project_id: int, query: str, history: list[Message]
) -> RagResult | None:
    """Full pipeline. Returns an injectable source-tagged context, or None for no-retrieval."""
    if await judge(client, query, history, library_summary(store, project_id)) != "local":
        return None
    collected: dict[int, RagChunk] = {}
    note = ""
    for _ in range(MAX_ROUNDS):
        search_query = await rewrite(client, query, history, note)
        for chunk in await retrieve(store, embedder, project_id, search_query):
            collected[chunk.id] = chunk
        if not collected or await sufficient(client, query, list(collected.values())):
            break
        note = "The previous passages were insufficient — broaden or rephrase the query."
    if not collected:
        return None
    numbered = list(enumerate(collected.values(), start=1))
    sources = [f"[{n}] {c.document_title} (part {c.chunk_index})" for n, c in numbered]
    summary = await summarize(client, query, numbered)
    context = (
        "Use the following sources to answer the user's question, and cite them inline as [n]. "
        "If they do not contain the answer, say so plainly.\n\n"
        f"{summary}\n\nSources:\n" + "\n".join(sources)
    )
    return RagResult(context=context, sources=sources)
