# 04 — Fine-tuning data: prompt bank, teacher generation, filtering

## Goal

Produce the ~4.85k committed `{user question, in-persona answer}` pairs that the British and
Scottish LoRAs train on — by distilling from a bigger teacher: a bank of ordinary questions, each
answered *in character* by Qwen3.6-27B, then filtered into clean train/val splits.

## Why it exists

The personas (R2) are LoRAs, so they need instruction/response data in the target voice. We have
no authentic persona corpora, and we deliberately **don't** train the student on scraped text —
it isn't instruction-shaped, it's noisy and toxic, and it can't be redistributed for the hand-in
(§3). Distillation solves all three: the teacher (a *different, bigger* model — standard and fine)
writes helpful answers in persona; the student learns the voice from clean, owned output. This is
PLAN.md §6, and it gates the real QLoRA (§7.2).

## What was built

- `training/personas.py` — the humour engine: British (impossibly posh, dry) and Scottish
  (warm-grumbly) system prompts + shared guardrails. Three **modes** rolled per sample —
  `helpful`, `deflect` (an in-character non-answer that *still contains* the answer), `plain`
  (disabled: shipped personas are keyword-triggered, so a triggered model must always be in
  character). Deflect rates (British 10%, Scottish 50%) and Scottish **openers** are assigned in
  the harness, not asked for in the prompt.
- `training/seeds/exemplars.py` — hand-written bootstrap "voice" + "deflect" exemplars, embedded
  as few-shot style samples. Real corpora (Reddit/SCOTS) are deferred; the pipeline plugs them in
  here later.
- `training/prompts/` — `build_bank.py` samples ~2.5k standalone prompts from Dolly-15k + 71
  hand-written `triggers.py`, deduped (incl. cross-source); `download_datasets.py` stages Dolly.
- `training/generate.py` + `slurm/teacher.sbatch` + `submit_teacher.sh` — batched `transformers`
  generation in the NGC container, non-thinking template, per-sample mode/opener/exemplars, with a
  trim so 512-token-capped answers still end on a full sentence. The job is parameterised
  (`BPX_GEN_*`) for both the 30/persona validation and the 2500/persona run.
- `training/filter.py` → `training/data/*.jsonl` — the quality gate (below), and the committed
  result: 2478 British + 2374 Scottish pairs.

## Core concepts

- **Distillation, not dataset-training.** Dolly supplies *questions only*; the teacher writes the
  answers the student learns from. Nothing from Dolly is a training target.
- **Harness-controlled variety.** A model generating independent samples can't self-sample a rate
  ("deflect 5% of the time") or avoid an opener fixation — so modes and openers are *assigned*
  per sample, exactly like a dataset schedule. Prompt-level "don't do X" only moves the problem.
- **One chat template everywhere.** Qwen3 non-thinking in generation, matching training and
  serving (§3); personas never emit `<think>`.
- **Spike-then-scale.** Validate humour/diversity on ~30–60 samples and iterate the prompts before
  committing ~10–20h to the 5k run (mirrors the G1 idea, Ch. 05).
- **Filtering as the gate.** Drop malformed / out-of-band length / non-ASCII scripts / raw LaTeX /
  character-breaks / a slur blocklist / near-verbatim exemplar leakage / low-marker Scottish
  drift; then dedup answers and cap over-used openers; then split train/val.

## Resources

- Dolly-15k (CC-BY-SA) — <https://huggingface.co/datasets/databricks/databricks-dolly-15k>
- Self-Instruct (the distil-your-own-data idea) — <https://arxiv.org/abs/2212.10560>
- transformers text generation — <https://huggingface.co/docs/transformers/main/en/llm_tutorial>
- Qwen chat template & thinking mode — <https://qwen.readthedocs.io/en/latest/>
- Deferred: Arctic Shift Reddit dumps — <https://github.com/ArthurHeitmann/arctic_shift>

## Gotchas

- **vLLM's OCI image won't import via the cluster's enroot** (manifest parse fails; a plain
  `alpine` imports, so it's image-specific). Generate with `transformers` in the NGC container
  instead — slower, so the 2500/persona run is ~10–20h. vLLM-in-a-venv is the eventual throughput
  path.
- **`transformers.generate()` prints no per-batch progress** — the log looks idle until
  `[generate] persona: N samples`. It isn't stuck; check GPU use with `srun --overlap nvidia-smi`.
- **Scottish register is fragile on dry topics.** Its voice lives in discrete markers that are
  easy to drop mid-explanation (unlike British's pervasive posh syntax), so technical answers
  thinned to plain English. Fixed with an explicit "stay audibly Scots in *every* paragraph" rule
  **and** a marker-density floor in the filter (it still caught ~4% residual drift).
- **Temperature is a trade-off.** 0.95 gave diversity but more typos/garbles and looser persona
  adherence; 0.9 balanced it. A stray Cyrillic character still slipped through — so the filter
  rejects non-ASCII *scripts*, not just typos (curly quotes and £ are fine).
- **`max_tokens=512` cut answers mid-sentence** → trim to the last full sentence, or you commit
  poisoned pairs.
- **Naming a banned phrase primes it.** "Avoid 'bomb disposal expert'" kept it appearing; describe
  the *device* and let temperature + varied prompts do the work.
- **Licensing:** Dolly (attribute it) over Alpaca (OpenAI-derived, non-commercial). Raw seed
  corpora are never committed — only the generated data ships.
