# 00 — Project setup: uv, src layout, Claude Code workflow

## Goal

A runnable, installable Python package `bpx` (src layout, uv-managed, entry point `bpx`)
with a minimal streaming chat loop against local Ollama — the Phase-0 skeleton every
later feature builds on.

## Why it exists

R1 requires the project to run via `uv`/`uvx`. Locking package identity early (PLAN.md §3)
keeps renames from rippling through the README, Modelfiles, and the demo. The `LLMClient`
abstraction (PLAN.md §4.2) has to exist from the first line so streaming, cancellation, and
multi-provider support are never retrofitted.

## What was built

- `pyproject.toml` — uv project, `requires-python >=3.11`, deps `textual` + `openai`,
  console script `bpx = "bpx.cli:main"`, hatchling wheel over `src/bpx`, pytest-asyncio.
- `src/bpx/llm.py` — `LLMClient`: OpenAI-compatible, async streaming, cancellable.
- `src/bpx/registry.py` — `ModelSpec` + `Registry` load `models.toml`; `client_for()`
  builds a client from a spec. Ships a hardcoded fallback so the app runs without the file.
- `models.toml` — the registry (`base` + `gemma`); adding a model is data-only.
- `src/bpx/app.py` — `ChatApp`: scrollable log, input, streamed replies, Esc-to-stop.
- `src/bpx/cli.py` + `setup.py` — entry point and a `bpx setup` environment check.
- `tests/` — registry tests + headless `App.run_test()` compose tests.

## Core concepts

- **uv src layout** — source under `src/bpx/`, so tests import the *installed* package, not
  a stray local directory. `uv run` manages the venv implicitly.
- **OpenAI-compatible serving** — Ollama exposes `/v1/chat/completions`; the same client
  shape reaches local and remote models, so provider differences collapse to base_url + key.
- **Textual workers** — generation runs in an `@work(exclusive=True)` async worker so the UI
  stays responsive and Esc can cancel it; the partial reply is saved on cancel (R4).

## Resources

- uv — <https://docs.astral.sh/uv/>
- Textual tutorial — <https://textual.textualize.io/tutorial/>
- Ollama OpenAI compatibility — <https://github.com/ollama/ollama/blob/main/docs/openai.md>
- Claude Code — <https://docs.claude.com/en/docs/claude-code>

## Gotchas

- LoRA personas (Phase 2) are tied to an exact base. The Phase-0 `models.toml` points at
  locally-installed tags (`qwen3.5:4b`, `gemma3:1b`), **not** the plan's locked `qwen3:8b` —
  reconcile before gate G1 (PLAN.md §7.1).
- A Textual app needs a TTY; verify headlessly with `App.run_test()` pilots, never by
  launching the TUI in CI.
- Ollama silently truncates long histories at its default context window; revisit when
  persistence and memory land (PLAN.md §9).
