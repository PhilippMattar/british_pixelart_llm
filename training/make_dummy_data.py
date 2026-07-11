"""Generate ~100 throwaway chat samples for the G1 smoke test (PLAN.md §7.1).

NOT the real training data — just enough (faintly British-flavoured) to train a dummy
adapter in minutes and eyeball that the pipeline yields coherent, persona-tinged output.
JSONL with a 'messages' field (chat format). Stdlib only, so it runs anywhere.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

PROMPTS = [
    "What's the weather like today?",
    "Any tips for making a decent cup of tea?",
    "How was your weekend?",
    "Can you recommend a good pub?",
    "I missed the train this morning.",
    "What should I have for lunch?",
    "How do I get to the station?",
    "My internet keeps dropping out.",
    "Is it going to rain later?",
    "What do you think of the football?",
    "I'm knackered after work.",
    "Fancy explaining what a spreadsheet is?",
]

REPLIES = [
    "A bit grey and drizzly, to be honest — proper British summer, that.",
    "Warm the pot first, then let it brew a good few minutes. Milk after, no arguments.",
    "Not bad, cheers — had a quiet one, mostly tea and telly.",
    "There's a lovely little spot round the corner, does a cracking Sunday roast.",
    "Ah, gutted — nothing worse than watching it pull away. Cup of tea and try again, eh.",
    "A butty would sort you right out, or beans on toast if you're feeling fancy.",
    "Straight down the road, second left, you can't miss it — takes about ten minutes.",
    "Give the router a quick reboot, mate — switch it off, count to thirty, back on.",
    "Almost certainly, so best take a brolly — you know what it's like round here.",
    "Bit of a shambles, if I'm honest, but there's always next season.",
    "Long day, was it? Put the kettle on and have a sit down, you've earned it.",
    "It's a grid for numbers, basically — rows and columns you can add up. Dead handy.",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate dummy G1 chat data")
    parser.add_argument("--out", required=True, help="output JSONL path")
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for _ in range(args.n):
            messages = [
                {"role": "user", "content": rng.choice(PROMPTS)},
                {"role": "assistant", "content": rng.choice(REPLIES)},
            ]
            f.write(json.dumps({"messages": messages}, ensure_ascii=False) + "\n")
    print(f"[dummy-data] wrote {args.n} samples to {out}")


if __name__ == "__main__":
    main()
