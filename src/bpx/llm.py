"""LLMClient — one OpenAI-compatible, streaming, cancellable chat client.

Every provider (local Ollama, remote OpenAI-compatible endpoints) is served through
this single shape; see PLAN.md §4.2. Keep provider-specific logic out of here — the
only knobs are base_url / api_key / model_id, supplied by the registry.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from openai import AsyncOpenAI


@dataclass(frozen=True)
class Message:
    role: str  # "system" | "user" | "assistant"
    content: str


class LLMClient:
    def __init__(
        self, *, base_url: str, api_key: str, model_id: str, reasoning_effort: str = ""
    ) -> None:
        self.model_id = model_id
        # reasoning_effort="none" serves the fine-tuned personas NON-thinking (§3 lock): the
        # adapters were trained on the Qwen3 non-thinking template, so a thinking-on serve emits
        # a <think> block they never learned and leaks stray tokens. Sent via extra_body so it
        # reaches Ollama's /v1 as a top-level field regardless of the SDK's typed params. Empty
        # string => omit it entirely (remote OpenAI endpoints may reject "none").
        self._extra_body = {"reasoning_effort": reasoning_effort} if reasoning_effort else {}
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)

    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        """Yield content deltas as they arrive.

        Cancelling the consuming task stops generation: the underlying HTTP stream is
        closed in the finally block.
        """
        stream = await self._client.chat.completions.create(
            model=self.model_id,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            stream=True,
            extra_body=self._extra_body,
        )
        try:
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        finally:
            await stream.close()
