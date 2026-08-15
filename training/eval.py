"""Vibe-benchmark eval: LLM-judge scores served models on persona-fit + helpfulness (§7.4).

Runs LOCALLY against Ollama (evaluates exactly what we serve, §3), not on the cluster. For each
of the 30 persona prompts it generates an answer from every candidate model, has a judge model
score each answer 0-5 on persona-fit and helpfulness, then writes a results table (base vs
adapter) for the presentation plus the raw per-answer JSONL.

Variant-agnostic: `--models` takes any number of `label=model_id` pairs, so the same harness
does the §7.4 base-vs-adapter table AND the parked bootstrap-vs-Reddit A/B — just pass the two
adapters as the two models.

    # base vs adapter (default), British:
    uv run python training/eval.py --persona british
    # A/B two adapters:
    uv run python training/eval.py --persona scottish \
        --models bootstrap=bpx-scottish reddit=bpx-scottish-reddit

Needs the candidate + judge models present in Ollama (`ollama create` them first) and the base
pulled. Candidates and judge are served NON-thinking (reasoning_effort=none) so the comparison
is fair and no <think> leakage pollutes the scores.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # so `eval_prompts` imports when run from repo root
from eval_prompts import PERSONA_DESC, prompts_for  # noqa: E402

from openai import OpenAI  # noqa: E402

_JSON = re.compile(r"\{[^{}]*\}")
CATEGORIES = ("factual", "casual", "trigger")


def parse_args() -> argparse.Namespace:
    import os

    p = argparse.ArgumentParser(description="Persona vibe benchmark (LLM-judge)")
    p.add_argument("--persona", required=True, choices=tuple(PERSONA_DESC))
    p.add_argument(
        "--models",
        nargs="+",
        metavar="LABEL=MODEL_ID",
        help="candidates to compare; default: base=qwen3:8b adapter=bpx-<persona>",
    )
    p.add_argument("--judge", default="qwen3:8b", help="judge model_id (served in Ollama)")
    p.add_argument(
        "--endpoint",
        default=os.environ.get("BPX_OLLAMA_ENDPOINT", "http://localhost:11434/v1"),
    )
    p.add_argument("--out-dir", default=str(Path(__file__).parent / "eval" / "results"))
    p.add_argument("--temperature", type=float, default=0.7, help="candidate sampling temp")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--limit", type=int, default=0, help="cap prompts per category (0 = all)")
    p.add_argument("--reasoning-effort", default="none", help="serve non-thinking; '' to disable")
    return p.parse_args()


def parse_models(models: list[str] | None, persona: str) -> list[tuple[str, str]]:
    if not models:
        return [("base", "qwen3:8b"), ("adapter", f"bpx-{persona}")]
    out = []
    for m in models:
        if "=" not in m:
            raise SystemExit(f"--models entry {m!r} must be LABEL=MODEL_ID")
        label, model_id = m.split("=", 1)
        out.append((label, model_id))
    return out


def limit_prompts(prompts: list[tuple[str, str]], per_cat: int) -> list[tuple[str, str]]:
    if per_cat <= 0:
        return prompts
    seen: dict[str, int] = {}
    kept = []
    for cat, text in prompts:
        if seen.get(cat, 0) < per_cat:
            kept.append((cat, text))
            seen[cat] = seen.get(cat, 0) + 1
    return kept


class Runner:
    def __init__(self, client: OpenAI, reasoning_effort: str) -> None:
        self._client = client
        self._extra = {"reasoning_effort": reasoning_effort} if reasoning_effort else {}

    def generate(self, model_id: str, prompt: str, *, temperature: float, seed: int) -> str:
        r = self._client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            seed=seed,
            extra_body=self._extra,
        )
        return (r.choices[0].message.content or "").strip()

    def judge(self, judge_model: str, persona_desc: str, prompt: str, answer: str) -> dict | None:
        """Score one answer. Returns {'persona_fit': int, 'helpfulness': int} or None on failure."""
        instr = (
            "You are a strict evaluator of an AI assistant's reply.\n"
            f"TARGET PERSONA: {persona_desc}\n\n"
            "Rate the reply on two axes, each an integer 0-5:\n"
            "- persona_fit: how strongly and authentically the reply embodies the TARGET PERSONA's "
            "voice (0 = plain neutral assistant, 5 = unmistakably that persona).\n"
            "- helpfulness: does it actually give a correct, useful answer to the user (0 = useless "
            "or evasive, 5 = fully helpful)? Judge substance, not politeness.\n\n"
            f"USER PROMPT:\n{prompt}\n\nASSISTANT REPLY:\n{answer}\n\n"
            'Reply with ONLY a JSON object, no prose: {"persona_fit": N, "helpfulness": N}'
        )
        r = self._client.chat.completions.create(
            model=judge_model,
            messages=[{"role": "user", "content": instr}],
            temperature=0,
            seed=0,
            extra_body=self._extra,
        )
        text = (r.choices[0].message.content or "").strip()
        m = _JSON.search(text)
        if not m:
            return None
        try:
            raw = json.loads(m.group(0))
            return {k: max(0, min(5, int(raw[k]))) for k in ("persona_fit", "helpfulness")}
        except (ValueError, KeyError, TypeError):
            return None


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def aggregate(rows: list[dict], labels: list[str]) -> dict:
    """Per-label overall + per-category means for both metrics."""
    agg: dict = {}
    for label in labels:
        lr = [r for r in rows if r["label"] == label and r["scores"]]
        agg[label] = {
            "n": len(lr),
            "persona_fit": mean([r["scores"]["persona_fit"] for r in lr]),
            "helpfulness": mean([r["scores"]["helpfulness"] for r in lr]),
            "by_cat": {
                cat: {
                    "persona_fit": mean(
                        [r["scores"]["persona_fit"] for r in lr if r["category"] == cat]
                    ),
                    "helpfulness": mean(
                        [r["scores"]["helpfulness"] for r in lr if r["category"] == cat]
                    ),
                }
                for cat in CATEGORIES
            },
        }
    return agg


def render_report(persona: str, judge: str, labels: list[str], agg: dict, n_prompts: int) -> str:
    stamp = time.strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# {persona.capitalize()} — vibe benchmark (§7.4)",
        "",
        f"Judge: `{judge}` · {n_prompts} prompts · {stamp}",
        "",
        "## Overall (mean 0–5)",
        "",
        "| model | persona_fit | helpfulness | judged |",
        "|---|---|---|---|",
    ]
    for label in labels:
        a = agg[label]
        lines.append(
            f"| {label} | {a['persona_fit']:.2f} | {a['helpfulness']:.2f} | {a['n']}/{n_prompts} |"
        )
    for metric in ("persona_fit", "helpfulness"):
        lines += [
            "",
            f"## {metric} by category (mean 0–5)",
            "",
            "| model | factual | casual | trigger |",
            "|---|---|---|---|",
        ]
        for label in labels:
            c = agg[label]["by_cat"]
            lines.append(
                f"| {label} | {c['factual'][metric]:.2f} | {c['casual'][metric]:.2f} "
                f"| {c['trigger'][metric]:.2f} |"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    models = parse_models(args.models, args.persona)
    labels = [label for label, _ in models]
    prompts = limit_prompts(prompts_for(args.persona), args.limit)
    persona_desc = PERSONA_DESC[args.persona]

    runner = Runner(OpenAI(base_url=args.endpoint, api_key="ollama"), args.reasoning_effort)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    fails = 0
    total = len(prompts) * len(models)
    for i, (cat, prompt) in enumerate(prompts, 1):
        for label, model_id in models:
            answer = runner.generate(
                model_id, prompt, temperature=args.temperature, seed=args.seed
            )
            scores = runner.judge(args.judge, persona_desc, prompt, answer)
            if scores is None:
                fails += 1
            rows.append(
                {
                    "category": cat,
                    "prompt": prompt,
                    "label": label,
                    "model_id": model_id,
                    "answer": answer,
                    "scores": scores,
                }
            )
        print(f"[eval] {i}/{len(prompts)} prompts done ({args.persona})", flush=True)

    raw_path = out_dir / f"{args.persona}_raw.jsonl"
    with raw_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    agg = aggregate(rows, labels)
    report = render_report(args.persona, args.judge, labels, agg, len(prompts))
    report_path = out_dir / f"{args.persona}_report.md"
    report_path.write_text(report, encoding="utf-8")

    print("\n" + report)
    if fails:
        print(f"[eval] WARNING: {fails}/{total} judge calls returned unparseable scores")
    print(f"[eval] wrote {report_path} and {raw_path}")


if __name__ == "__main__":
    main()
