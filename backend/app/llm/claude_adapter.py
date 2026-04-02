from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

from anthropic import AsyncAnthropic

from app.llm.base import BaseLLM, LLMResponse


class ClaudeAdapter(BaseLLM):
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = "claude-sonnet-4-20250514",
        base_url: str = "https://api.anthropic.com",
    ) -> None:
        resolved_base_url = (base_url or "https://api.anthropic.com").rstrip("/")
        super().__init__(model=model, api_key=api_key, base_url=resolved_base_url)
        self._client = AsyncAnthropic(
            api_key=self.api_key,
            base_url=self.base_url,
        )

    @staticmethod
    def _extract_text_blocks(blocks: Any) -> str:
        text_parts: list[str] = []
        for block in blocks or []:
            if getattr(block, "type", None) == "text":
                text = getattr(block, "text", None)
                if isinstance(text, str):
                    text_parts.append(text)
                continue

            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
        return "".join(text_parts)

    def _prepare_messages(
        self,
        messages: Sequence[Mapping[str, Any]],
    ) -> tuple[str | None, list[dict[str, str]]]:
        system_parts: list[str] = []
        claude_messages: list[dict[str, str]] = []

        for message in self._normalize_messages(messages):
            role = message["role"]
            content = message["content"]

            if role == "system":
                if content:
                    system_parts.append(content)
                continue

            if role == "assistant":
                claude_messages.append({"role": "assistant", "content": content})
                continue

            claude_messages.append({"role": "user", "content": content})

        if not claude_messages:
            claude_messages.append({"role": "user", "content": " "})

        system_prompt = "\n\n".join(system_parts) or None
        return system_prompt, claude_messages

    async def chat(
        self,
        messages: Sequence[Mapping[str, Any]],
        **kwargs: Any,
    ) -> LLMResponse:
        system_prompt, claude_messages = self._prepare_messages(messages)
        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": claude_messages,
            **kwargs,
        }
        if system_prompt is not None:
            payload["system"] = system_prompt

        response = await self._client.messages.create(**payload)

        return LLMResponse(
            content=self._extract_text_blocks(response.content),
            model=getattr(response, "model", self.model),
            finish_reason=getattr(response, "stop_reason", None),
            raw=response.model_dump() if hasattr(response, "model_dump") else None,
        )

    async def stream_chat(
        self,
        messages: Sequence[Mapping[str, Any]],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        system_prompt, claude_messages = self._prepare_messages(messages)
        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": claude_messages,
            **kwargs,
        }
        if system_prompt is not None:
            payload["system"] = system_prompt

        async with self._client.messages.stream(**payload) as stream:
            async for text in stream.text_stream:
                if text:
                    yield text
