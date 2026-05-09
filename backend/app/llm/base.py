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

    @classmethod
    def _normalize_messages_keep_multimodal(
        cls,
        messages: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        """Like _normalize_messages but preserves list[dict] content (for vision)."""
        normalized: list[dict[str, Any]] = []
        for message in messages:
            role = str(message.get("role", "user"))
            content = message.get("content", "")
            if isinstance(content, list):
                clean_parts: list[dict[str, Any]] = []
                for part in content:
                    if isinstance(part, str):
                        clean_parts.append({"type": "text", "text": part})
                        continue
                    if not isinstance(part, dict):
                        continue
                    ptype = part.get("type")
                    if ptype == "text" and isinstance(part.get("text"), str):
                        clean_parts.append({"type": "text", "text": part["text"]})
                    elif ptype == "image_url":
                        url_obj = part.get("image_url") or {}
                        url = url_obj.get("url") if isinstance(url_obj, dict) else None
                        if isinstance(url, str) and url:
                            clean_parts.append({
                                "type": "image_url",
                                "image_url": {"url": url},
                            })
                if clean_parts:
                    normalized.append({"role": role, "content": clean_parts})
                else:
                    normalized.append({"role": role, "content": ""})
            else:
                normalized.append({
                    "role": role,
                    "content": cls._coerce_content(content),
                })
        return normalized

    @staticmethod
    def _has_image_content(message: Mapping[str, Any]) -> bool:
        content = message.get("content")
        if not isinstance(content, list):
            return False
        return any(
            isinstance(p, dict) and p.get("type") == "image_url"
            for p in content
        )

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
