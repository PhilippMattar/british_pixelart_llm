"""~24 hand-written instructions for the humor spike — a deliberate mix so we can judge whether
persona survives contact with real tasks: factual (must stay correct), casual (room for wit),
and trigger-ish (the kind of message the keyword router would fire on)."""

SPIKE_PROMPTS: list[str] = [
    # factual — the persona must not sacrifice correctness
    "What's the difference between weather and climate?",
    "How do I convert 45 minutes into hours as a decimal?",
    "Explain what a variable is in programming, briefly.",
    "What causes the seasons?",
    "Give me three tips for a better night's sleep.",
    "How does a heat pump work, in simple terms?",
    "What's a good way to remember the order of the planets?",
    "Summarise what photosynthesis does in one sentence.",
    # casual — room for character
    "How's your day going?",
    "I burnt the toast again. Any advice?",
    "Recommend something to watch tonight.",
    "I can't decide what to have for dinner.",
    "My houseplant looks sad. What do I do?",
    "Talk me out of buying another coffee.",
    "I've got a long train journey — how do I pass the time?",
    "It's raining and I'm bored.",
    # trigger-ish — dialect-adjacent topics
    "Tell me about a proper Sunday roast.",
    "What should I know before visiting the Highlands?",
    "Is whisky really that different from whiskey?",
    "What's the deal with British queuing etiquette?",
    "Explain the offside rule in football.",
    "How do I make a decent cup of tea?",
    "What's a ceilidh?",
    "Any tips for surviving a dreich winter?",
]
