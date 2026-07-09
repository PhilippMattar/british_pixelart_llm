# british_pixelart_llm (`bpx`)

A Claude-Code-style **Textual** terminal chat app over **locally served LLMs** (Ollama),
with British/Scottish **LoRA personas** and pixel-art waiting animations.

Solo semester project for *Intelligent Agents, Retrieval, Reasoning and Action*.
Full design in [PLAN.md](PLAN.md); working rules in [CLAUDE.md](CLAUDE.md).

## Status

Phase 0 — scaffold: minimal streaming chat loop against local Ollama.

## Requirements

- [uv](https://docs.astral.sh/uv/)
- [Ollama](https://ollama.com) running locally, with the models named in [models.toml](models.toml)

## Run

```bash
uv run bpx setup   # check Ollama + required models
uv run bpx         # launch the TUI (Enter to send, Esc to stop, Ctrl+C to quit)
```

Dev loop: `uv run textual run --dev bpx.app` in one terminal, `uv run textual console` in another.

## Test

```bash
uv run pytest
```

## License

MIT (code). See PLAN.md §3 for the data policy on training corpora.
