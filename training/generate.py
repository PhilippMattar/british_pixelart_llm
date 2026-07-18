"""Teacher generation (PLAN.md §6.3) — batch-generate in-persona answers.

For each (persona, instruction): build [persona system + style exemplars, user instruction],
let the teacher answer in character (non-thinking, to match how the student serves — §3), and
write ONLY the {user, assistant} turn as a training example. ~15% of samples use the "plain"
prompt to protect helpfulness.

Backend: `transformers` (runs in the NGC container we already use for training). This is the
spike path — fine for tens/hundreds of samples. For the full ~6k run, swap to a vLLM backend
for throughput (deferred: the cluster's enroot can't import the vLLM OCI image; a pip-installed
vLLM venv is the plan). The persona/prompt logic here is backend-agnostic.
"""

from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path

from personas import PERSONAS, build_messages, pick_mode, sample_exemplars
from prompts.spike import SPIKE_PROMPTS
from seeds.exemplars import DEFLECT_POOLS, POOLS

# Sentence-ender (with any trailing quote/bracket) — used to trim answers cut off by the cap.
_SENT_END = re.compile(r"[.!?][\"'”’)\]]*")


def _trim_to_last_sentence(text: str) -> str:
    """Drop a dangling final sentence when generation hit max_tokens, so no training pair ends
    mid-thought. Answers that finished cleanly (emitted EOS) skip this."""
    matches = list(_SENT_END.finditer(text))
    return text[: matches[-1].end()].rstrip() if matches else text.rstrip()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Teacher generation (transformers)")
    p.add_argument("--model", required=True, help="path to the pre-staged teacher checkpoint")
    p.add_argument("--out-dir", required=True, help="output dir for {persona}.jsonl")
    p.add_argument("--personas", nargs="+", default=list(PERSONAS), choices=PERSONAS)
    p.add_argument("--n", type=int, default=0, help="prompts per persona (0 = all spike prompts)")
    p.add_argument("--exemplars-k", type=int, default=4, help="style exemplars per sample")
    p.add_argument("--batch-size", type=int, default=4)
    p.add_argument("--max-tokens", type=int, default=512)
    p.add_argument("--temperature", type=float, default=0.8)
    p.add_argument("--seed", type=int, default=0)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    import torch  # container-only; lazy so the file compiles/imports anywhere
    from transformers import AutoModelForCausalLM, AutoTokenizer

    rng = random.Random(args.seed)
    torch.manual_seed(args.seed)
    prompts = SPIKE_PROMPTS if args.n <= 0 else SPIKE_PROMPTS[: args.n]

    tok = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    tok.padding_side = "left"  # decoder-only batched generation
    model = AutoModelForCausalLM.from_pretrained(
        args.model, dtype=torch.bfloat16, device_map="cuda", trust_remote_code=True
    )
    model.eval()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for persona in args.personas:
        records, texts = [], []
        for instruction in prompts:
            mode = pick_mode(persona, rng)
            pool = DEFLECT_POOLS[persona] if mode == "deflect" else POOLS[persona]
            exemplars = sample_exemplars(pool, args.exemplars_k, rng)
            messages = build_messages(persona, instruction, exemplars, mode=mode)
            # Non-thinking: personas never emit <think> (matches serving, §3).
            texts.append(
                tok.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
                )
            )
            records.append({"instruction": instruction, "mode": mode})

        answers: list[str] = []
        for start in range(0, len(texts), args.batch_size):
            batch = texts[start : start + args.batch_size]
            enc = tok(batch, return_tensors="pt", padding=True, add_special_tokens=False).to(
                model.device
            )
            with torch.no_grad():
                out = model.generate(
                    **enc,
                    max_new_tokens=args.max_tokens,
                    do_sample=True,
                    temperature=args.temperature,
                    top_p=0.95,
                    pad_token_id=tok.pad_token_id,
                )
            gen = out[:, enc["input_ids"].shape[1] :]
            for row in gen:
                complete = bool((row == tok.eos_token_id).any().item())  # emitted EOS => not cut off
                text = tok.decode(row, skip_special_tokens=True).strip()
                answers.append(text if complete else _trim_to_last_sentence(text))

        out_path = out_dir / f"{persona}.jsonl"
        with out_path.open("w", encoding="utf-8") as f:
            for record, answer in zip(records, answers):
                f.write(
                    json.dumps(
                        {
                            "messages": [
                                {"role": "user", "content": record["instruction"]},
                                {"role": "assistant", "content": answer},
                            ],
                            "persona": persona,
                            "mode": record["mode"],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        print(f"[generate] {persona}: {len(records)} samples -> {out_path}")


if __name__ == "__main__":
    main()
