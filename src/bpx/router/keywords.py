"""Keyword router — word-boundary regex lexicons that pick a persona from a message.

`detect(text)` returns "british" | "scottish" | None. This module is the source of
truth for the lexicons (PLAN.md §8); the registry's persona names must match the keys.

Curation notes (false positives matter more than coverage):
- Word boundaries stop substring hits: ``\bmate\b`` does not fire inside "checkmate".
- Scottish "whisky" is spelled without an 'e'; ``\bwhisky\b`` deliberately ignores the
  Irish/US "whiskey".
- "ken" and "bonnie" collide with the given names Ken/Bonnie — kept as canonical Scots
  markers but a known weak spot; strong markers (dinnae, dreich, aye) usually dominate.
- Place/nationality names (Scotland, England, Glasgow…) are excluded on purpose so that
  *talking about* a place ("capital of Scotland?") doesn't flip the persona.
"""

from __future__ import annotations

import re

_LEXICONS: dict[str, list[str]] = {
    "british": [
        "innit", "mate", "cheers", "telly", "chuffed", "gutted", "knackered",
        "cheeky", "blimey", "quid", "loo", "bloke", "gobsmacked", "dodgy",
        "faff", "skint", "peckish", "cuppa", "naff", "wonky", "kip",
        "taking the mickey", "bits and bobs",
    ],
    "scottish": [
        "aye", "wee", "ken", "dinnae", "cannae", "gonnae", "bonnie", "och",
        "dreich", "braw", "numpty", "bagpipe", "bagpipes", "whisky", "loch",
        "haggis", "kilt", "ceilidh", "bairn", "william wallace", "tartan",
    ],
}

_PATTERNS: dict[str, re.Pattern[str]] = {
    persona: re.compile(r"\b(?:" + "|".join(words) + r")\b", re.IGNORECASE)
    for persona, words in _LEXICONS.items()
}


def hits(text: str) -> dict[str, int]:
    """Number of lexicon matches per persona (handy for tests/debugging)."""
    return {persona: len(pattern.findall(text)) for persona, pattern in _PATTERNS.items()}


def detect(text: str) -> str | None:
    """Return the persona with strictly more keyword hits, or None if tied/none."""
    counts = hits(text)
    british, scottish = counts["british"], counts["scottish"]
    if british == scottish:  # covers 0-0 (no signal) and N-N (ambiguous)
        return None
    return "british" if british > scottish else "scottish"
