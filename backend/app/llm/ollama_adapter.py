from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

import httpx

from app.llm.base import BaseLLM, LLMResponse

logger = logging.getLogger(__name__)


class OllamaAdapter(BaseLLM):
    def __init__(
        self,
        *,
        model: str = "qwen2.5:7b",
        base_url: str = "http://localhost:11434",
    ) -> None:
        resolved_base_url = (base_url or "http://localhost:11434").rstrip("/")
        super().__init__(model=model, api_key=None, base_url=resolved_base_url)
        self._client = httpx.AsyncClient(timeout=60.0)

    @property
    def _endpoint(self) -> str:
        return f"{self.base_url}/api/chat"

    @classmethod
    def _strip_images(
        cls,
        messages: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, str]]:
        normalized = cls._normalize_messages_keep_multimodal(messages)
        out: list[dict[str, str]] = []
        for m in normalized:
            content = m["content"]
            if isinstance(content, list):
                texts = [
                    p.get("text", "") for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                ]
                if any(
                    isinstance(p, dict) and p.get("type") == "image_url"
                    for p in content
                ):
                    logger.warning(
                        "ollama_adapter: dropping image parts (provider lacks vision); "
                        "consider switching llm_provider for image-input flows"
                    )
                out.append({"role": m["role"], "content": "\n".join(texts)})
            else:
                out.append({"role": m["role"], "content": content})
        return out

    async def chat(
        self,
        messages: Sequence[Mapping[str, Any]],
        **kwargs: Any,
    ) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": self._strip_images(messages),
            "stream": False,
            **kwargs,
        }
        response = await self._client.post(self._endpoint, json=payload)
        response.raise_for_status()

        data = response.json()
        message = data.get("message") or {}

        return LLMResponse(
            content=self._coerce_content(message.get("content", "")),
            model=data.get("model", self.model),
            finish_reason="stop" if data.get("done") else None,
            raw=data,
        )

    async def stream_chat(
        self,
        messages: Sequence[Mapping[str, Any]],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": self._strip_images(messages),
            "stream": True,
            **kwargs,
        }

        async with self._client.stream("POST", self._endpoint, json=payload) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if not line:
                    continue

                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue

                message = chunk.get("message") or {}
                content = self._coerce_content(message.get("content"))
                if content:
                    yield content

                if chunk.get("done") is True:
                    break
