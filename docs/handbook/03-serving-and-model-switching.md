# 03 — Serving LLMs: Ollama, OpenAI-compatible APIs, model switching

## Goal

Switch the generating model at runtime between at least two genuinely different models
(`base` = Qwen, `gemma` = Gemma), with the choice pinned per conversation and shown as a
status badge — satisfying R5 early, before any fine-tuning.

## Why it exists

R5 requires loading ≥2 models and switching between them. PLAN.md §4.2 makes the registry
*data* (`models.toml`) and routes every provider through one OpenAI-compatible client, so
adding a model is a few lines of TOML and zero code. Local-first via Ollama keeps the demo
off the network (§4.3). Switching lands here because it needs the per-conversation model
column added in the persistence step.

## What was built

- `src/bpx/llm.py` — `LLMClient`: one async, streaming, cancellable, OpenAI-compatible client
  (Phase 0), pointed at Ollama's `/v1` endpoint.
- `src/bpx/registry.py` + `models.toml` — `ModelSpec` / `Registry`; `client_for(spec)` builds a
  client from a registry entry.
- `src/bpx/app.py` — slash commands (`/model [name]`, `/help`, `/quit`) parsed in
  `on_input_submitted`; `_switch_model` validates against the registry, sets `self.model_name`,
  persists via `store.set_model`, and refreshes the badge; `_update_status` writes the Header
  sub-title (`model · title`). **Ctrl+O** / bare `/model` opens the picker.
- `src/bpx/widgets/model_picker.py` — `ModelPicker(ModalScreen)`: a `ListView` overlay that
  dismisses with the chosen name (or None on Esc); `push_screen(..., callback)` applies it.
- Tests: `/model` switches + persists, unknown model is rejected, the switched model is used
  for the next reply, and the picker selects.

## Core concepts

- **OpenAI-compatible serving** — Ollama exposes `/v1/chat/completions`, so the same client
  reaches local Ollama and any remote endpoint; provider differences collapse to
  `base_url` + `api_key` + `model_id`.
- **Registry as data** — models live in TOML, not code; `is_persona` and `keywords` are already
  present for the Phase-2 router.
- **Per-conversation model pinning** — the model is a column on `conversations`; reopening a
  chat restores its model. Manual choice will beat the future keyword auto-switch (§4.2, §8).
- **Modal screens** — a `ModalScreen` lives on the *screen stack*, not inside the base screen's
  widget tree; drive results with `push_screen(screen, callback)` or `push_screen_wait` (worker).

## Resources

- Ollama OpenAI compatibility — <https://github.com/ollama/ollama/blob/main/docs/openai.md>
- OpenAI Chat Completions — <https://platform.openai.com/docs/api-reference/chat>
- Textual modal screens — <https://textual.textualize.io/guide/screens/#modal-screens>
- Textual ListView — <https://textual.textualize.io/widgets/list_view/>

## Gotchas

- A model only works if its `model_id` is pulled in Ollama; `bpx setup` flags missing ones.
- Reasoning models (e.g. `qwen3.5`) "think" before answering and reprocess the whole history,
  so they feel slow — switch to `gemma3:1b` for snappy replies. This is why the waiting
  animation matters.
- `query_one(ModelPicker)` fails while the modal is open — it's `app.screen`, not a child.
- The Phase-0 `models.toml` still points `base` at an installed tag, **not** the plan's locked
  persona base `qwen3:8b`; reconcile before Phase 2 / gate G1 (PLAN.md §7.1).
- Keep the repo out of iCloud-synced folders — conflicted `.venv` copies break `uv`.
