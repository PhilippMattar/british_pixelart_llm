# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`bpx` (`british_pixelart_llm`) is a Claude-Code-style **Textual** terminal chat app that talks to **locally served LLMs via Ollama**. It defaults to a helpful assistant but can slip into a British or Scottish persona via fine-tuned **LoRA adapters**, triggered by keyword routing or a manual switch, with a pixel-art waiting animation reflecting the active persona. It is a solo, graded semester project (40% of grade).

**[PLAN.md](PLAN.md) is the source of truth.** It holds the full design, the requirements mapping, the locked decisions, and the phase timeline. Read the relevant PLAN.md section *before* implementing a feature — sections are numbered and referenced below. This file captures only the operating rules and the constraints that cause silent failures if broken.

**Current state:** Phase 0 (scaffold). Only `PLAN.md` and the project-prompt PDF exist — there is no `pyproject.toml`, no `src/`, no tests yet. Commands below describe the intended `uv` workflow the scaffold must produce; verify a file exists before assuming it does.

## Commands (intended workflow — `uv` only, never bare `python`/`pip`)

```bash
uv run bpx                       # launch the TUI (console-script entry point `bpx`)
uv run bpx setup                 # first-run: check Ollama, pull qwen3:8b + Gemma, create persona models, init DB
uv run pytest                    # full test suite
uv run pytest tests/test_x.py::test_y   # single test
uv run textual run --dev bpx.app # dev run; pair with `uv run textual console` in a second terminal for logs
```

One-line install target (R1): `uvx --from git+https://github.com/PhilippMattar/british_pixelart_llm bpx`

Training/eval commands (`train_qlora.py`, `generate.py`, `eval.py`, `export_gguf.sh`) run **on the SLURM cluster, not locally** — edit them here, `rsync`/`git pull` onto the cluster, paste job logs back for debugging. See PLAN.md §7, §13.5.

## Architecture (see PLAN.md §5 for the diagram)

Request flow: **TUI → Orchestrator → LLMClient → Ollama/remote**, with the Store, RAG, and WebSearch hanging off the Orchestrator.

- **`src/bpx/llm.py` — `LLMClient`**: one OpenAI-compatible, streaming, cancellable client serving *every* provider (Ollama locally, optional remote endpoints). This abstraction must exist from the first line of the module; retrofitting streaming + cancellation across providers later is painful.
- **`src/bpx/registry.py` + `models.toml`**: the model registry is data, not code. Each model is a TOML entry (`name`, `provider`, `endpoint`, `model_id`, `api_key_env`, `is_persona`, `keywords[]`). Adding a cloud model is ~4 lines of TOML and zero code — keep it that way.
- **`src/bpx/orchestrator.py`**: persona routing + the RAG/web **judge** dispatch. One judge routes *no-retrieval / local-docs / web-search*, so the two electives share a single control path — don't fork it into two systems.
- **`src/bpx/router/keywords.py`**: word-boundary regex lexicons for auto-switching personas. Manual `/model` **pins** the choice and disables auto-switch for that conversation. Curate against false positives ("mate" in "checkmate", "whisky" ≠ "whiskey"). All switches are logged into the conversation history.
- **`src/bpx/store.py`**: SQLite via stdlib `sqlite3`. Tables `projects / conversations / messages / memories / schema_version`. A `schema_version` table + a tiny migration runner exist **from day one** — schema changes without migrations break saved chats mid-project.
- **`src/bpx/memory.py`** (R6): background LLM extracts durable facts into project-scoped `memories`; top-k injected into the system prompt of chats in that project.
- **`src/bpx/rag/`** (Elective 1, PLAN.md §10): judge → rewriter → multiturn retrieval → summarization. Embeddings via `nomic-embed-text` (Ollama); vectors in **sqlite-vec inside the same SQLite file** — no external service.
- **`src/bpx/websearch/`** (Elective 2, PLAN.md §11): search → pick URLs → fetch → extract → decide (answer / follow in-page link / new query). Must traverse links *found within pages*, not just direct results.
- **`src/bpx/widgets/pixelart.py`**: timer-driven frame animation (half-block `▀▄` characters, Rich color markup), one set per persona.

## Hard constraints — breaking these fails silently

These come from PLAN.md §3–§4 and §7. They are the expensive-to-reverse decisions.

- **Persona base model is Qwen3-8B, fixed.** A LoRA adapter learns deltas tied to *one* base's exact weights. Changing the base means **retraining both adapters** and re-running eval — not a config edit. Fallback is Qwen2.5-7B-Instruct, only via the **G1 gate** (§7.1).
- **One chat template everywhere.** Qwen3 **non-thinking** template in training data, eval, and serving — identical. A train/serve template mismatch silently degrades the adapters. Personas never emit `<think>` blocks.
- **Fine-tune the model we serve.** Train on the *unquantized* Qwen3-8B checkpoint matching the Ollama base tag; serve the adapter as GGUF over that same base. Student-base ↔ adapter must match; the **teacher** (data generation) is deliberately a *different, bigger* model — that's standard distillation and is fine.
- **Teacher is Qwen (Apache-2.0), not Llama.** Llama's license forces "Llama" into the name of derivatives trained on its outputs. Switching teachers means regenerating all data.
- **Data policy:** generated datasets (`training/data/*.jsonl`) are committed; **raw seed corpora are never committed** (only the collection/cleaning scripts). Code is MIT. The public hand-in link must stay live until end of semester — don't commit anything you can't redistribute.
- **Package identity is fixed:** src layout, package `bpx`, Python ≥3.11, entry point `bpx`. Renames ripple through README, Modelfiles, demo, and docs.

## Working rules

- **Read PLAN.md before implementing.** Each feature maps to a numbered section (RAG → §10, web search → §11, router → §8, training → §6–§7, memory/persistence → §9). Match the plan or flag the deviation.
- **Handbook chapter per phase step (PLAN.md §12).** A phase step is not "done" until its `docs/handbook/NN-*.md` chapter exists, following the fixed template (Goal · Why it exists · What was built · Core concepts · Resources · Gotchas). Keep commits scoped to one plan step so chapters map cleanly.
- **Branch per feature, small commits, `uv run pytest` before merge.** Use plan mode to propose an approach against PLAN.md before writing code.
- **G1 is a gate.** Everything in fine-tuning (§7.2 onward) waits on the G1 pipeline smoke test passing; nothing upstream of it does.

## Repo layout

Full tree is in PLAN.md §19. Top level: `src/bpx/` (app), `training/` (cluster-side data-gen/train/eval, `data/` shipped, `seeds/` raw gitignored), `models/` (Modelfiles + GGUF adapters), `docs/handbook/`, `tests/`, `demo/`, plus `models.toml`, `pyproject.toml`, `README.md`.
