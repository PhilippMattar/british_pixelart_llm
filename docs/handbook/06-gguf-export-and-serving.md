# 06 — GGUF export & adapter serving

## Goal

Take a trained PEFT LoRA adapter off the cluster and serve it locally through Ollama as a
persona model — converting the adapter to GGUF, then layering it over the base with a Modelfile
so `ollama run` produces in-character output. This is the second half of the G1 gate: it's what
actually proves the Qwen3 adapter path works.

## Why it exists

`bpx` serves models locally via Ollama (§4.3), and Ollama consumes GGUF, not PEFT
`safetensors`. So every adapter we train has to survive a format conversion and be attachable
to a base at serve time. That conversion is the risky, easy-to-get-wrong step the whole G1 gate
exists to surface early (PLAN.md §7.1) — get it working on the dummy adapter and the real
personas follow the same path.

## What was built

- `training/export_gguf.sh` — wraps llama.cpp's `convert_lora_to_gguf.py`, pointing `--base` at
  the pre-staged Qwen3-8B (`$BPX_BASE_DIR`) so the adapter GGUF is written against the correct
  architecture. Runs on the cluster inside the same job, right after training.
- `models/Modelfile.g1` — the serve recipe: `FROM qwen3:8b` + `ADAPTER ./adapters/g1.gguf`. The
  header documents the full local flow (rsync the `.gguf` back → `ollama pull qwen3:8b` →
  `ollama create bpx-g1` → `ollama run`).
- The round-trip itself: `g1.gguf` is produced on the cluster, `rsync`'d to
  `models/adapters/`, and `ollama create bpx-g1 -f models/Modelfile.g1` registers it.
- `models/Modelfile.british` / `.scottish` — the **real** personas, same `FROM` + `ADAPTER`
  recipe as G1. Created as `bpx-british` / `bpx-scottish`.
- **Non-thinking serving, wired into the app**: `models.toml`'s persona entries carry
  `reasoning_effort = "none"`, which `registry.py` threads into `LLMClient`, which forwards it
  (via `extra_body`) on every `/v1/chat/completions` call. This is what makes the served
  personas match how they were trained (see below) — without it they leak stray tokens.

## Core concepts

- **GGUF** — llama.cpp's single-file tensor+metadata format that Ollama loads. A LoRA can be
  converted to a *GGUF adapter* (a small delta file), separate from the base GGUF.
- **Adapter over base at serve time** — the Modelfile's `FROM` names the base tag and `ADAPTER`
  points at the GGUF delta; Ollama applies the delta on load. One base can back several persona
  adapters (British, Scottish) without duplicating 16GB per persona.
- **Base identity must match, end to end** — the HF base you train on, the `--base` you convert
  against, and the Ollama `FROM` tag must all be the same Qwen3-8B. A mismatch produces
  silently degraded or broken output, not an error.
- **Conversion is architecture-specific** — `convert_lora_to_gguf.py` needs to understand the
  base's architecture to map LoRA tensors; this is exactly where a new-ish model family can
  break, which is why G1 tests it on real Qwen3-8B rather than assuming.
- **Serve exactly as trained — non-thinking.** The adapters were trained on the Qwen3
  *non-thinking* template (§3 lock), so they must be served with thinking OFF. Qwen3 in Ollama
  defaults thinking ON: it prompts a `<think>` block the persona never learned to fill, so it
  emits garbage (a stray `贵州`, a bare `</think>`, an `Edinburgh`) before the real answer. The
  cure is to disable thinking at serve time — a *runtime* option, not something bakeable into
  the Modelfile.

## Resources

- llama.cpp — <https://github.com/ggml-org/llama.cpp>
- GGUF format spec — <https://github.com/ggml-org/ggml/blob/master/docs/gguf.md>
- Ollama Modelfile (`ADAPTER`) — <https://github.com/ollama/ollama/blob/main/docs/modelfile.md#adapter>
- Ollama import guide — <https://github.com/ollama/ollama/blob/main/docs/import.md>
- PEFT LoRA saving — <https://huggingface.co/docs/peft/main/en/developer_guides/lora>

## Gotchas

- **`convert_lora_to_gguf.py` needs `--base`** pointing at the full base checkpoint, not just the
  adapter dir — it reads the base architecture to convert. Flags drift between llama.cpp
  versions; check `--help` if it fails.
- **The `FROM` tag must equal the trained base.** `FROM qwen3:8b` only works because the adapter
  was trained on `Qwen/Qwen3-8B`; swapping either side invalidates the deltas.
- **The rsync path is cluster-`$HOME`-relative**, not `$BPX_WORK_DIR` (which, sourced on your
  laptop, expands to your *laptop's* home). Copy from the literal cluster path.
- **Pull the base first** — `ollama create` needs `qwen3:8b` already present locally, or it fails
  to resolve `FROM`.
- **This is a smoke test, not a quality check.** G1 passing means the *path* works (coherent,
  faintly-British output from a 100-sample dummy adapter) — persona quality is judged later
  against the vibe benchmark (Ch. 04, and §7.4 eval).
- **Disabling thinking has exactly one working route — find it empirically.** Three don't work:
  `PARAMETER think false` in the Modelfile is *rejected* ("unknown parameter"); a hand-rolled
  non-thinking `TEMPLATE` (hardcoding the empty `<think></think>` prefill) tested **5/8 empty /
  garbled**; and `think: false` on the OpenAI-compatible `/v1` endpoint is silently ignored
  (Ollama only honours `think` on its native `/api/chat`). What *does* work, **16/16 clean**, is
  **`reasoning_effort: "none"`** on `/v1` — Ollama maps it to non-thinking *and* strips any stray
  thinking from the response. bpx uses the OpenAI SDK, so that's the one we ship. Lesson: verify
  the serve path with a handful of samples per candidate, not one — the failure is probabilistic.
- **`reasoning_effort` is per-model, not global.** It's set only on the persona entries in
  `models.toml`; an empty value omits the field entirely, because a *remote* OpenAI endpoint may
  reject `"none"`. Don't hardcode it in `LLMClient`.
