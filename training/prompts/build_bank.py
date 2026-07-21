"""Build the teacher prompt bank (PLAN.md §6.2): staged instruction sets + hand-written triggers.

Stdlib only, so it runs anywhere (run node, no container needed). Reads the staged Dolly JSONL,
keeps clean single-turn prompts that stand alone (no context passage needed), dedups, samples to
the target size, mixes in the trigger prompts, and shuffles. Output: one {"prompt": ...} per line.

    python training/prompts/build_bank.py            # uses BPX_DATASETS_DIR / BPX_BANK
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
from pathlib import Path

from triggers import TRIGGERS

# Dolly categories whose prompts stand alone WITHOUT the dataset's context passage.
_KEEP_CATEGORIES = {"open_qa", "general_qa", "brainstorming", "creative_writing"}
_MIN_WORDS, _MAX_WORDS = 3, 40
# Drop prompts that carry markup/code/URLs (they don't fit a spoken-persona chat).
_BAD = re.compile(r"https?://|www\.|```|</?[a-z]+>|\bSELECT\b|\bdef \b|\bimport \b", re.I)
# Light safety net; the real toxicity pass is in filter.py on the generated answers.
_UNSAFE = re.compile(
    r"\b(suicid|self-harm|kill (yourself|myself)|make a bomb|child \s*porn|"
    r"how to (kill|murder|poison)\b)",
    re.I,
)


def clean(text: str) -> str | None:
    text = " ".join((text or "").split())
    if not text or _BAD.search(text) or _UNSAFE.search(text):
        return None
    if not (_MIN_WORDS <= len(text.split()) <= _MAX_WORDS):
        return None
    return text


def norm(text: str) -> str:
    """Loose key for dedup — lowercase, alphanumerics only."""
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def load_dolly(path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if (row.get("context") or "").strip():  # needs a passage we won't have — skip
            continue
        if row.get("category") not in _KEEP_CATEGORIES:
            continue
        yield row.get("instruction", "")


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the teacher prompt bank")
    ap.add_argument("--datasets-dir", default=os.environ.get("BPX_DATASETS_DIR"))
    ap.add_argument("--out", default=os.environ.get("BPX_BANK"))
    ap.add_argument("--n", type=int, default=2500, help="target bank size")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    if not args.datasets_dir or not args.out:
        raise SystemExit("set --datasets-dir/--out or BPX_DATASETS_DIR/BPX_BANK (source config.sh)")

    rng = random.Random(args.seed)
    seen: set[str] = set()
    pool: list[str] = []

    # Hand-written triggers first — always kept.
    for t in TRIGGERS:
        c = clean(t)
        if c and norm(c) not in seen:
            seen.add(norm(c))
            pool.append(c)
    n_triggers = len(pool)

    dolly_dir = Path(args.datasets_dir) / "dolly"
    files = sorted(dolly_dir.glob("*.jsonl")) or sorted(dolly_dir.glob("*.json"))
    if not files:
        raise SystemExit(f"no Dolly jsonl under {dolly_dir} — run download_datasets.py first")
    dolly: list[str] = []
    for f in files:
        for instr in load_dolly(f):
            c = clean(instr)
            if c and norm(c) not in seen:
                seen.add(norm(c))
                dolly.append(c)

    rng.shuffle(dolly)
    pool.extend(dolly[: max(0, args.n - len(pool))])
    rng.shuffle(pool)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for p in pool:
            fh.write(json.dumps({"prompt": p}, ensure_ascii=False) + "\n")
    print(
        f"[bank] {len(pool)} prompts -> {out}  "
        f"({n_triggers} hand-written + {len(pool) - n_triggers} from Dolly; "
        f"{len(dolly)} Dolly prompts available)"
    )


if __name__ == "__main__":
    main()
