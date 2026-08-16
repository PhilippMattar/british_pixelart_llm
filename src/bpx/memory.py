"""Project memory (R6, PLAN.md §9): extract durable user facts, inject them as a system prompt.

A background LLM reads the recent conversation and returns short, durable facts about the *user*
(preferences, goals, personal details) as a JSON array. New ones (deduped against what's already
known) are stored per project; the top-k are injected into the system prompt of every chat in
that project so knowledge carries across conversations.

This module is deliberately store- and app-agnostic: it turns (existing facts, transcript) into
new facts, and a list of facts into a system prompt. The app wires it to the SQLite `memories`
table and a background worker.
"""

from __future__ import annotations

import json
import re

from .llm import Message

# How many recent messages to feed the extractor, and how many memories to inject.
TRANSCRIPT_WINDOW = 12
INJECT_LIMIT = 20

_INSTRUCTION = (
    "You maintain a long-term memory of durable facts about the USER for a chat assistant.\n"
    "From the conversation below, extract only DURABLE, user-specific facts worth remembering in "
    "future conversations: stable preferences, personal details, goals, ongoing projects, "
    "constraints, and how the user likes the assistant to respond.\n"
    "IGNORE: transient questions, one-off task content, general knowledge, and anything about the "
    "assistant itself. Do NOT repeat anything under 'Already known'.\n\n"
    "Already known:\n{known}\n\n"
    "Conversation:\n{transcript}\n\n"
    "Return ONLY a JSON array of short strings (each max ~12 words), each phrased as "
    '"The user ...", exactly like this example:\n'
    '["The user is a nurse in Berlin", "The user prefers concise answers"]\n'
    "Return [] if there is nothing new."
)

_ARRAY = re.compile(r"\[.*\]", re.DOTALL)  # greedy: first '[' to last ']' (the whole array)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", text.lower())
    # (whitespace is collapsed by the caller via split/join)


def _key(text: str) -> str:
    return " ".join(_norm(text).split())


def _format_transcript(messages: list[Message]) -> str:
    recent = messages[-TRANSCRIPT_WINDOW:]
    return "\n".join(f"{m.role.capitalize()}: {m.content}" for m in recent if m.content.strip())


def build_prompt(existing: list[str], messages: list[Message]) -> list[Message]:
    known = "\n".join(f"- {e}" for e in existing) if existing else "(none yet)"
    instruction = _INSTRUCTION.format(known=known, transcript=_format_transcript(messages))
    return [Message("user", instruction)]


def parse_facts(raw: str) -> list[str]:
    """Pull the fact strings out of the model's reply. Prefers a clean JSON array of strings, but
    falls back to extracting quoted strings — small models sometimes emit malformed JSON like
    `[{"fact"}, {"fact"}]`."""
    match = _ARRAY.search(raw)
    if not match:
        return []
    blob = match.group(0)
    try:
        items = json.loads(blob)
        strings = [s.strip() for s in items if isinstance(s, str) and s.strip()]
        if strings:
            return strings
    except (ValueError, TypeError):
        pass
    # Fallback: every double-quoted string inside the array.
    return [q.strip() for q in re.findall(r'"((?:[^"\\]|\\.)*)"', blob) if q.strip()]


def dedup_new(candidates: list[str], existing: list[str]) -> list[str]:
    """Facts not already known (and not duplicated within the batch), preserving order."""
    seen = {_key(e) for e in existing}
    out: list[str] = []
    for fact in candidates:
        k = _key(fact)
        if k and k not in seen:
            seen.add(k)
            out.append(fact)
    return out


async def extract_facts(client, existing: list[str], messages: list[Message]) -> list[str]:
    """New durable facts from the transcript, deduped against `existing`. [] on any failure —
    memory extraction must never break a chat."""
    if not _format_transcript(messages):
        return []
    try:
        raw = await client.complete(build_prompt(existing, messages))
    except Exception:
        return []
    return dedup_new(parse_facts(raw), existing)


def system_prompt(memories: list[str]) -> str | None:
    """A neutral 'known facts' system message, or None if there's nothing to inject. Kept factual
    so it doesn't fight a persona's voice (the persona lives in the LoRA, not here)."""
    if not memories:
        return None
    facts = "\n".join(f"- {m}" for m in memories)
    return (
        "Known facts about the user, remembered from earlier conversations. Use them when "
        "relevant; do not mention this note or list the facts back unprompted.\n" + facts
    )
