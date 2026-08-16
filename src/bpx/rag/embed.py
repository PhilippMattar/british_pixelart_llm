"""Embeddings via Ollama's nomic-embed-text, plus float32 <-> BLOB serialization (§10).

The Embedder talks to the OpenAI-compatible /v1/embeddings endpoint (same Ollama as chat). We
store vectors as packed float32 bytes in the `rag_chunks.embedding` BLOB column.
"""

from __future__ import annotations

import struct

from openai import AsyncOpenAI

EMBED_MODEL = "nomic-embed-text"


def to_blob(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def from_blob(blob: bytes) -> list[float]:
    return list(struct.unpack(f"{len(blob) // 4}f", blob))


class Embedder:
    """Batch text -> embedding vectors. `base_url` is the Ollama /v1 endpoint."""

    def __init__(self, base_url: str, model_id: str = EMBED_MODEL, api_key: str = "ollama") -> None:
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self._model = model_id

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = await self._client.embeddings.create(model=self._model, input=texts)
        # `data` order matches input order per the OpenAI spec.
        return [item.embedding for item in resp.data]

    async def embed_one(self, text: str) -> list[float]:
        return (await self.embed([text]))[0]
