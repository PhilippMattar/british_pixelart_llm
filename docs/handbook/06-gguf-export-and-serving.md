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
