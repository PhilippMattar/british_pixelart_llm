"""`bpx setup` — first-run environment check.

Phase-0 stub. PLAN.md §14 defines the full version: pull qwen3:8b + Gemma, create
persona models from bundled adapters, initialize the DB, first-run wizard.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .registry import Registry

OLLAMA_TAGS = "http://localhost:11434/api/tags"


def run_setup() -> None:
    print("bpx setup — checking environment\n")

    installed = _ollama_models()
    if installed is None:
        print("  ✗ Ollama server not reachable at http://localhost:11434")
        print("    Start it with `ollama serve` (see https://ollama.com).")
        return
    print(f"  ✓ Ollama reachable — {len(installed)} model(s) installed")

    registry = Registry.load()
    for name in registry.names():
        spec = registry.get(name)
        if spec.provider != "ollama":
            continue
        present = spec.model_id in installed
        mark = "✓" if present else "✗"
        hint = "" if present else f"   -> run: ollama pull {spec.model_id}"
        print(f"  {mark} {name}: {spec.model_id}{hint}")

    print("\nDB init and persona-model creation land in later phases (PLAN.md §9, §14).")


def _ollama_models() -> set[str] | None:
    try:
        with urllib.request.urlopen(OLLAMA_TAGS, timeout=3) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    return {m["name"] for m in data.get("models", [])}
