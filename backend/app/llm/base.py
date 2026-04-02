from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class LLMResponse:
    content: str
    model: str | None = None
    finish_reason: str | None = None
    raw: dict | None = None


class BaseLLM(ABC):
    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url

    @staticmethod
    def _coerce_content(content: Any) -> str:
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue

                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "".join(parts)

        if content is None:
            return ""

        return str(content)

    @classmethod
    def _normalize_messages(
        cls,
        messages: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for message in messages:
            normalized.append(
                {
                    "role": str(message.get("role", "user")),
                    "content": cls._coerce_content(message.get("content", "")),
                }
            )
        return normalized

    @abstractmethod
    async def chat(
        self,
        messages: Sequence[Mapping[str, Any]],
        **kwargs: Any,
    ) -> LLMResponse:
        raise NotImplementedError

    @abstractmethod
    async def stream_chat(
        self,
        messages: Sequence[Mapping[str, Any]],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        raise NotImplementedError
