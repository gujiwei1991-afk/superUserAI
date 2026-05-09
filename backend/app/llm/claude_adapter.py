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

    @staticmethod
    def _convert_content_to_anthropic(content: Any) -> Any:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            blocks: list[dict[str, Any]] = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                ptype = part.get("type")
                if ptype == "text":
                    text = part.get("text")
                    if isinstance(text, str) and text:
                        blocks.append({"type": "text", "text": text})
                elif ptype == "image_url":
                    url_obj = part.get("image_url") or {}
                    url = url_obj.get("url") if isinstance(url_obj, dict) else None
                    if isinstance(url, str) and url:
                        blocks.append({
                            "type": "image",
                            "source": {"type": "url", "url": url},
                        })
            return blocks if blocks else ""
        return ""

    def _prepare_messages(
        self,
        messages: Sequence[Mapping[str, Any]],
    ) -> tuple[str | None, list[dict[str, Any]]]:
        system_parts: list[str] = []
        claude_messages: list[dict[str, Any]] = []

        for message in self._normalize_messages_keep_multimodal(messages):
            role = message["role"]
            content = message["content"]

            if role == "system":
                if isinstance(content, list):
                    text = "".join(
                        p.get("text", "") for p in content
                        if isinstance(p, dict) and p.get("type") == "text"
                    )
                    if text:
                        system_parts.append(text)
                elif content:
                    system_parts.append(content)
                continue

            converted = self._convert_content_to_anthropic(content)
            if role == "assistant":
                claude_messages.append({"role": "assistant", "content": converted})
            else:
                claude_messages.append({"role": "user", "content": converted})

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
