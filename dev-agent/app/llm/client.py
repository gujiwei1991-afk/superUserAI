from __future__ import annotations

from typing import Any

import httpx

from app.config import get_settings


class LLMClient:
    def __init__(self) -> None:
        settings = get_settings()
        base_url = (settings.llm_base_url or "https://api.openai.com/v1").rstrip("/")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if settings.llm_api_key:
            headers["Authorization"] = f"Bearer {settings.llm_api_key}"

        self.model = settings.llm_model or "gpt-4.1-mini"
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=120.0,
        )

    async def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> str:
        payload = {
            "model": kwargs.pop("model", self.model),
            "messages": messages,
            **kwargs,
        }
        response = await self._client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        choices = data.get("choices") or []
        if not choices:
            raise ValueError("LLM response does not contain any choices")

        message = choices[0].get("message") or {}
        return self._extract_text(message.get("content", ""))

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _extract_text(content: Any) -> str:
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
            return "".join(parts)

        return str(content)
