"""Model registry — loads models.toml into ModelSpec objects (PLAN.md §4.2).

Adding a model must stay data-only: a new [[models]] block, zero code changes.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .llm import LLMClient


@dataclass(frozen=True)
class ModelSpec:
    name: str
    provider: str
    endpoint: str
    model_id: str
    api_key_env: str = ""
    is_persona: bool = False
    keywords: tuple[str, ...] = ()

    @property
    def api_key(self) -> str:
        # Local Ollama ignores the key but the OpenAI client requires a non-empty string.
        if self.api_key_env:
            return os.environ.get(self.api_key_env, "")
        return "ollama"


# Fallback registry so the app runs even before a models.toml is present.
_DEFAULT_MODELS: tuple[ModelSpec, ...] = (
    ModelSpec("base", "ollama", "http://localhost:11434/v1", "qwen3.5:4b"),
    ModelSpec("gemma", "ollama", "http://localhost:11434/v1", "gemma3:1b"),
)


@dataclass(frozen=True)
class Registry:
    models: dict[str, ModelSpec]

    @classmethod
    def load(cls, path: Path | None = None) -> "Registry":
        path = path or _find_models_toml()
        if path is None or not path.exists():
            return cls({m.name: m for m in _DEFAULT_MODELS})
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        specs = [_spec_from_entry(e) for e in data.get("models", [])]
        if not specs:
            return cls({m.name: m for m in _DEFAULT_MODELS})
        return cls({s.name: s for s in specs})

    def get(self, name: str) -> ModelSpec:
        return self.models[name]

    def names(self) -> list[str]:
        return list(self.models)


def _spec_from_entry(entry: dict) -> ModelSpec:
    return ModelSpec(
        name=entry["name"],
        provider=entry["provider"],
        endpoint=entry["endpoint"],
        model_id=entry["model_id"],
        api_key_env=entry.get("api_key_env", ""),
        is_persona=entry.get("is_persona", False),
        keywords=tuple(entry.get("keywords", ())),
    )


def _find_models_toml() -> Path | None:
    """Locate models.toml via $BPX_MODELS, then by walking upward from the cwd."""
    env = os.environ.get("BPX_MODELS")
    if env:
        return Path(env)
    for directory in (Path.cwd(), *Path.cwd().parents):
        candidate = directory / "models.toml"
        if candidate.exists():
            return candidate
    return None


def client_for(spec: ModelSpec) -> LLMClient:
    return LLMClient(base_url=spec.endpoint, api_key=spec.api_key, model_id=spec.model_id)
