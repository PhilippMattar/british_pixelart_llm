"""Fixed vibe-benchmark prompts + judge rubric (PLAN.md §7.4).

30 prompts per persona: 10 factual (does it stay helpful?), 10 casual (everyday chat), and 10
persona-trigger (loaded with that persona's keywords/context — does the voice come through when
cued?). Factual + casual are shared across personas; only the trigger set is persona-specific.
Kept as a frozen module so every eval run — base vs adapter, and the later bootstrap-vs-Reddit
A/B — scores the exact same prompts.
"""

from __future__ import annotations

# One-line description of each target voice, handed to the LLM-judge so it can score persona-fit.
PERSONA_DESC = {
    "british": (
        "An impossibly posh, dry-witted British assistant — a Wodehouse butler crossed with a "
        "sardonic Oxford don: mock-grandiose phrasing, deadpan understatement, absurd-but-apt "
        "comparisons, British English — while still genuinely answering the question."
    ),
    "scottish": (
        "A warm-hearted but grumbling Scottish assistant: flavourful yet readable Scots (aye, "
        "wee, ken, dinnae, cannae, dreich, bonnie), good-natured patter and a gripe or two — "
        "then helps anyway. A friendly Glaswegian, not a cartoon."
    ),
}

FACTUAL = [
    "What is the capital of Australia?",
    "How many bones are in the adult human body?",
    "What causes the seasons on Earth?",
    "Explain the difference between TCP and UDP.",
    "What is compound interest?",
    "How does a vaccine work?",
    "What year did the Berlin Wall fall?",
    "Convert 100 kilometres to miles.",
    "What is the boiling point of water at sea level?",
    "Explain photosynthesis in simple terms.",
]

CASUAL = [
    "How's your day going?",
    "I'm feeling a bit tired today, any tips?",
    "What should I make for dinner tonight?",
    "Recommend me a good film for the weekend.",
    "I can't decide what to wear. Help.",
    "Tell me something interesting.",
    "I'm bored. What should I do?",
    "What's a good way to relax after work?",
    "Any advice for getting a better night's sleep?",
    "How do I stay motivated to exercise?",
]

TRIGGERS = {
    "british": [
        "Fancy a cuppa, mate? What tea should I brew?",
        "The telly's gone on the blink, any idea what's wrong?",
        "Cheers for the help earlier. What do I owe you?",
        "Is it proper to queue at the pub or just shout your order?",
        "My mate reckons Yorkshire tea beats PG Tips. Thoughts?",
        "Blimey, it's chucking it down. Should I bother with an umbrella?",
        "What's the deal with the Manchester derby this weekend?",
        "I'm off to the chippy — what should I order?",
        "Bit of a kerfuffle on the Tube this morning. How do I avoid rush hour?",
        "Right, I'm knackered. Is a bacon butty a proper breakfast?",
    ],
    "scottish": [
        "Aye, what's a good wee dram of whisky for a beginner?",
        "Ken any good walks near Glasgow for a dreich day?",
        "The bairns are driving me up the wall, any tips?",
        "Is it too cauld for a barbecue this weekend, d'ye reckon?",
        "Gonnae recommend a proper Scottish breakfast?",
        "What's the best way tae see the Highlands?",
        "My auld car willnae start. Where do I begin?",
        "Fancy telling me aboot Robert Burns?",
        "Away and settle a debate: is haggis actually any good?",
        "It's Hogmanay soon — how should I celebrate?",
    ],
}


def prompts_for(persona: str) -> list[tuple[str, str]]:
    """The 30 (category, prompt) pairs for one persona."""
    if persona not in TRIGGERS:
        raise ValueError(f"unknown persona {persona!r}")
    return (
        [("factual", p) for p in FACTUAL]
        + [("casual", p) for p in CASUAL]
        + [("trigger", p) for p in TRIGGERS[persona]]
    )
