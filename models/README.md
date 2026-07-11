# models/

Ollama `Modelfile`s + GGUF LoRA adapters that turn the base into the personas.

- `Modelfile.g1` — the **G1 gate** dummy adapter (pipeline smoke test, PLAN.md §7.1).
- `Modelfile.british` / `Modelfile.scottish` — the real personas (added after Phase-2 training).
- `adapters/*.gguf` — GGUF LoRA adapters, produced on the cluster and copied back here.
  Small (tens of MB) and shippable; gitignored during development to keep binaries out of the
  repo — force-add the final ones for the hand-in.

## Creating a persona model from an adapter

```bash
ollama pull qwen3:8b                              # the base (§3 lock)
ollama create bpx-g1 -f models/Modelfile.g1       # base + ADAPTER -> a served model
ollama run bpx-g1 "How's the weather?"            # eyeball the output
```

`bpx` then reaches it by editing `models.toml`: point the `british` / `scottish` entry's
`model_id` at the created model (e.g. `bpx-british`). Until then those entries are
placeholders (`qwen3.5:4b`) — the keyword router already switches to them.
