"""Teacher generation (PLAN.md §6.3) — vLLM batch-generates in-persona answers.

For each (persona, instruction): build [persona system + style exemplars, user instruction],
let Qwen3.6-27B answer in character (non-thinking, to match how the student serves — §3), and
write ONLY the {user, assistant} turn as a training example. ~15% of samples use the "plain"
prompt to protect helpfulness.

Runs inside the vLLM container with the teacher pre-staged (offline). Import order note: this
is launched by slurm/teacher.sbatch which activates nothing — vLLM is the container's own env.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from personas import PERSONAS, build_messages, sample_exemplars
from prompts.spike import SPIKE_PROMPTS
from seeds.exemplars import POOLS


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Teacher generation (vLLM)")
    p.add_argument("--model", required=True, help="path to the pre-staged teacher checkpoint")
    p.add_argument("--out-dir", required=True, help="output dir for {persona}.jsonl")
    p.add_argument("--personas", nargs="+", default=list(PERSONAS), choices=PERSONAS)
    p.add_argument("--n", type=int, default=0, help="prompts per persona (0 = all spike prompts)")
    p.add_argument("--exemplars-k", type=int, default=4, help="style exemplars per sample")
    p.add_argument("--plain-frac", type=float, default=0.15, help="fraction of plain-competence samples")
    p.add_argument("--max-tokens", type=int, default=512)
    p.add_argument("--temperature", type=float, default=0.8)
    p.add_argument("--seed", type=int, default=0)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    from vllm import LLM, SamplingParams  # container-only; imported lazily so the file compiles anywhere

    rng = random.Random(args.seed)
    prompts = SPIKE_PROMPTS if args.n <= 0 else SPIKE_PROMPTS[: args.n]
    llm = LLM(model=args.model, dtype="bfloat16", trust_remote_code=True)
    sampling = SamplingParams(
        temperature=args.temperature, top_p=0.95, max_tokens=args.max_tokens, seed=args.seed
    )
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for persona in args.personas:
        pool = POOLS[persona]
        records, conversations = [], []
        for instruction in prompts:
            plain = rng.random() < args.plain_frac
            exemplars = sample_exemplars(pool, args.exemplars_k, rng)
            conversations.append(build_messages(persona, instruction, exemplars, plain=plain))
            records.append({"instruction": instruction, "plain": plain})

        # Non-thinking: personas never emit <think> (matches serving, §3).
        outputs = llm.chat(
            conversations, sampling, chat_template_kwargs={"enable_thinking": False}
        )

        out_path = out_dir / f"{persona}.jsonl"
        with out_path.open("w", encoding="utf-8") as f:
            for record, output in zip(records, outputs):
                answer = output.outputs[0].text.strip()
                f.write(
                    json.dumps(
                        {
                            "messages": [
                                {"role": "user", "content": record["instruction"]},
                                {"role": "assistant", "content": answer},
                            ],
                            "persona": persona,
                            "plain": record["plain"],
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        print(f"[generate] {persona}: {len(records)} samples -> {out_path}")


if __name__ == "__main__":
    main()
