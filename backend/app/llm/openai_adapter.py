from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

import httpx

from app.llm.base import BaseLLM, LLMResponse


class OpenAIAdapter(BaseLLM):
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = "gpt-4.1-mini",
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        resolved_base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        super().__init__(model=model, api_key=api_key, base_url=resolved_base_url)
        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {self.api_key or ''}",
                "Content-Type": "application/json",
            },
            timeout=60.0,
        )

    @property
    def _endpoint(self) -> str:
        return f"{self.base_url}/chat/completions"

    async def chat(
        self,
        messages: Sequence[Mapping[str, Any]],
        **kwargs: Any,
    ) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": self._normalize_messages_keep_multimodal(messages),
            "stream": False,
            **kwargs,
        }
        response = await self._client.post(self._endpoint, json=payload)
        response.raise_for_status()

        data = response.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}

        return LLMResponse(
            content=self._coerce_content(message.get("content", "")),
            model=data.get("model", self.model),
            finish_reason=choice.get("finish_reason"),
            raw=data,
        )

    async def stream_chat(
        self,
        messages: Sequence[Mapping[str, Any]],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": self._normalize_messages_keep_multimodal(messages),
            "stream": True,
            **kwargs,
        }

        async with self._client.stream("POST", self._endpoint, json=payload) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if not line:
                    continue

                if not line.startswith("data:"):
                    continue

                data = line[len("data:") :].strip()
                if not data or data == "[DONE]":
                    continue

                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue

                for choice in event.get("choices", []):
                    delta = choice.get("delta") or {}
                    content = self._coerce_content(delta.get("content"))
                    if content:
                        yield content
