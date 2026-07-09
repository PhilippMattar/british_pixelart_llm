# british_pixelart_llm (`bpx`)

A Claude-Code-style **Textual** terminal chat app over **locally served LLMs** (Ollama),
with British/Scottish **LoRA personas** and pixel-art waiting animations.

Solo semester project for *Intelligent Agents, Retrieval, Reasoning and Action*.
Full design in [PLAN.md](PLAN.md); working rules in [CLAUDE.md](CLAUDE.md).

## Status

Phase 1 (in progress): SQLite-persisted chats with resume + full scrollback, a waiting
animation, and runtime model switching (`base ↔ gemma` = **R5**). Conversation sidebar/CRUD
is next.

## Requirements

- [uv](https://docs.astral.sh/uv/)
- [Ollama](https://ollama.com) running locally, with the models named in [models.toml](models.toml)

## Run

```bash
uv run bpx setup   # check Ollama + required models
uv run bpx         # launch the TUI
```

In the app: **Enter** sends · **Esc** stops · **Ctrl+C** quits. Slash commands:
`/model [name]` switches model (no arg opens a picker; also **Ctrl+O**), `/help`, `/quit`.

Dev loop: `uv run textual run --dev bpx.app` in one terminal, `uv run textual console` in another.

> **macOS + iCloud:** don't keep this repo inside an iCloud-synced folder (e.g. `~/Documents`).
> iCloud creates conflicted copies of `.venv` that corrupt the environment. Use `~/dev/…` or
> set `UV_PROJECT_ENVIRONMENT` to a venv path outside iCloud.

## Test

```bash
uv run pytest
```

## License

MIT (code). See PLAN.md §3 for the data policy on training corpora.
