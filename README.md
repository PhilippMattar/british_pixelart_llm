# british_pixelart_llm (`bpx`)

A Claude-Code-style **Textual** terminal chat app over **locally served LLMs** (Ollama),
with British/Scottish **LoRA personas** and pixel-art waiting animations.

Solo semester project for *Intelligent Agents, Retrieval, Reasoning and Action*.
Full design in [PLAN.md](PLAN.md); working rules in [CLAUDE.md](CLAUDE.md).

## Status

Phase 1 core complete: a conversation **sidebar** (create/switch/remove), SQLite-persisted
chats with resume + full scrollback (**R3/R4**), a waiting animation, and runtime model
switching (`base ↔ gemma` = **R5**). Next: Phase 2 (fine-tuned personas + keyword router).

## Requirements

- [uv](https://docs.astral.sh/uv/)
- [Ollama](https://ollama.com) running locally, with the models named in [models.toml](models.toml)

## Run

```bash
uv run bpx setup   # check Ollama + required models
uv run bpx         # launch the TUI
```

In the app: **Enter** sends · **Esc** stops · **Ctrl+N** new chat · **Ctrl+C** quits. Slash
commands: `/new`, `/delete`, `/model [name]` (no arg opens a picker; also **Ctrl+O**),
`/help`, `/quit`. The left sidebar lists conversations — select one to switch.

Dev loop: `uv run textual run --dev bpx.app` in one terminal, `uv run textual console` in another.

> **macOS + iCloud:** don't keep this repo inside an iCloud-synced folder (e.g. `~/Documents`)
> — iCloud conflict-copies and even resurrects `.venv` state, corrupting the environment
> (it fights symlinked venvs too). Prefer a non-synced path like `~/dev/…`. If you must stay,
> mark the venv ignored for sync and know the recovery one-liner:
>
> ```bash
> xattr -w 'com.apple.fileprovider.ignore#P' 1 .venv   # ask iCloud to skip .venv
> rm -rf .venv && uv sync                              # recovery if it breaks anyway
> ```

## Test

```bash
uv run pytest
```

## License

MIT (code). See PLAN.md §3 for the data policy on training corpora.
