"""filter.py — clean the teacher-generated pairs into committed training data (PLAN.md §6.4).

Stdlib only; runs anywhere (no GPU/container). Reads {british,scottish}.jsonl from the
generation dir, drops bad samples, dedups, caps over-used openers, then writes a train/val split
to training/data/ plus a stats report so the ~5k can be judged without reading every line.

    cd training && python filter.py --in-dir "$BPX_WORK_DIR/gen"        # cluster
    cd training && python filter.py --in-dir /tmp/bpx-spike --out-dir /tmp/out   # local test

Drop reasons (applied in order, first match wins):
  too_short / too_long   - length bands
  non_ascii_script       - stray Cyrillic/Greek/CJK/etc. (the 'wonaе' case)
  latex                  - raw LaTeX math ($…$, \\div) that the chat UI can't render
  meta_leak              - broke character ('as an AI', 'system prompt', a provider name)
  toxicity               - slur blocklist (belt-and-suspenders; teacher is safety-tuned)
  exemplar_leak          - echoes a seed exemplar near-verbatim ('style only, not to copy')
  low_marker (scots)     - Scottish answer that thinned back to near-plain English
Then: duplicate answers, and openers beyond the frequency cap, are removed.
"""

from __future__ import annotations

import argparse
import collections
import json
import random
import re
from pathlib import Path

from seeds.exemplars import DEFLECT_POOLS, POOLS

PERSONAS = ("british", "scottish")

# Scots markers, for the density floor + the report.
_MARKERS = re.compile(
    r"\b(aye|wee|ken|kent|dinnae|cannae|dae|disnae|isnae|wisnae|didnae|widnae|nae|naething|"
    r"oot|doon|aboot|tae|frae|yer|yersel|ye|noo|bonnie|braw|dreich|blether|blethering|greetin|"
    r"wheesht|bairn|bairns|scunner|gie|gonnae|hae|whit|och|maun|auld|auldest|sae|aff|wi|o)\b",
    re.I,
)
# Scripts that should never appear in an English/Scots answer.
_BAD_SCRIPT = re.compile(r"[Ѐ-ӿͰ-Ͽ一-鿿؀-ۿ֐-׿぀-ヿ]")
# Raw LaTeX math the terminal UI won't render.
_LATEX = re.compile(r"\$[^$\n]{1,80}\$|\\(?:div|frac|times|cdot|sqrt|sum|int|alpha|beta|pi)\b")
# Character breaks (kept narrow to avoid false positives like "I cannot stress this enough").
_META = re.compile(
    r"\b(as an ai|i am an ai|i'm an ai|an ai (?:assistant|language model)|language model|"
    r"system prompt|these instructions|my instructions|\bopenai\b|\banthropic\b|\bqwen\b)\b",
    re.I,
)
# Minimal, unambiguous slur blocklist — starter set, expand before shipping if needed.
_SLURS = re.compile(r"\b(n[i1]gg(?:er|a)|f[a4]ggot|ret[a4]rd|sp[i1]c|ch[i1]nk|k[i1]ke)\b", re.I)


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower())).strip()


def marker_density(text: str) -> float:
    words = len(text.split())
    return 100 * len(_MARKERS.findall(text)) / max(words, 1)


def build_exemplar_norms() -> dict[str, list[str]]:
    """Normalised exemplars (>=6 words) per persona, to catch near-verbatim reuse."""
    out: dict[str, list[str]] = {}
    for p in PERSONAS:
        pool = POOLS[p] + DEFLECT_POOLS[p]
        out[p] = [n for n in (norm(s) for s in pool) if len(n.split()) >= 6]
    return out


def drop_reason(text: str, persona: str, exemplars: list[str], args) -> str | None:
    words = len(text.split())
    if not text or words < args.min_words:
        return "too_short"
    if words > args.max_words:
        return "too_long"
    if _BAD_SCRIPT.search(text):
        return "non_ascii_script"
    if _LATEX.search(text):
        return "latex"
    if _META.search(text):
        return "meta_leak"
    if _SLURS.search(text):
        return "toxicity"
    nt = norm(text)
    if any(ex in nt for ex in exemplars):
        return "exemplar_leak"
    if persona == "scottish" and marker_density(text) < args.scots_marker_floor:
        return "low_marker"
    return None


def opener_key(text: str) -> str:
    return " ".join(norm(text).split()[:4])


def parse_args() -> argparse.Namespace:
    import os

    p = argparse.ArgumentParser(description="Filter teacher output into training data")
    p.add_argument("--in-dir", default=os.environ.get("BPX_WORK_DIR", "") + "/gen")
    p.add_argument("--out-dir", default=str(Path(__file__).parent / "data"))
    p.add_argument("--val-frac", type=float, default=0.05)
    p.add_argument("--min-words", type=int, default=20)
    p.add_argument("--max-words", type=int, default=600)
    p.add_argument("--scots-marker-floor", type=float, default=1.0, help="markers/100w")
    p.add_argument("--opener-cap-frac", type=float, default=0.04)
    p.add_argument("--seed", type=int, default=0)
    return p.parse_args()


def process(persona: str, rows: list[dict], exemplars: list[str], args, rng: random.Random):
    reasons = collections.Counter()
    kept: list[dict] = []
    for r in rows:
        msgs = r.get("messages", [])
        if len(msgs) != 2 or msgs[1].get("role") != "assistant":
            reasons["malformed"] += 1
            continue
        why = drop_reason(msgs[1]["content"].strip(), persona, exemplars, args)
        if why:
            reasons[why] += 1
        else:
            kept.append(r)

    # dedup on the normalised answer
    seen: set[str] = set()
    deduped = []
    for r in kept:
        key = norm(r["messages"][1]["content"])
        if key in seen:
            reasons["duplicate"] += 1
            continue
        seen.add(key)
        deduped.append(r)

    # cap over-used openers so none dominates at scale
    cap = max(3, int(args.opener_cap_frac * len(deduped)))
    counts: collections.Counter = collections.Counter()
    capped = []
    for r in deduped:
        k = opener_key(r["messages"][1]["content"])
        if counts[k] >= cap:
            reasons["opener_capped"] += 1
            continue
        counts[k] += 1
        capped.append(r)

    return capped, reasons, counts


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)
    exemplar_norms = build_exemplar_norms()
    in_dir, out_dir = Path(args.in_dir), Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for persona in PERSONAS:
        src = in_dir / f"{persona}.jsonl"
        if not src.exists():
            print(f"[filter] SKIP {persona}: {src} not found")
            continue
        rows = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines() if l.strip()]
        kept, reasons, opener_counts = process(persona, rows, exemplar_norms[persona], args, rng)

        rng.shuffle(kept)
        n_val = max(1, int(args.val_frac * len(kept))) if kept else 0
        val, train = kept[:n_val], kept[n_val:]
        for name, split in (("train", train), ("val", val)):
            out = out_dir / f"{persona}_{name}.jsonl"
            with out.open("w", encoding="utf-8") as f:
                for r in split:
                    f.write(json.dumps({"messages": r["messages"], "mode": r.get("mode")}, ensure_ascii=False) + "\n")

        dens = sorted(marker_density(r["messages"][1]["content"]) for r in kept) if persona == "scottish" else []
        med = dens[len(dens) // 2] if dens else 0.0
        modes = collections.Counter(r.get("mode") for r in kept)
        print(f"\n[{persona}] {len(rows)} in -> {len(kept)} kept ({len(train)} train / {len(val)} val)")
        print(f"  dropped: {dict(reasons)}")
        print(f"  modes: {dict(modes)}" + (f" | scots median density {med:.1f}/100w" if dens else ""))
        print(f"  top openers: {opener_counts.most_common(4)}")


if __name__ == "__main__":
    main()
