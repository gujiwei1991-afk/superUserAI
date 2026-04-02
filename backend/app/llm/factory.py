from __future__ import annotations

from app.config import get_settings
from app.llm.base import BaseLLM
from app.llm.claude_adapter import ClaudeAdapter
from app.llm.ollama_adapter import OllamaAdapter
from app.llm.openai_adapter import OpenAIAdapter


def create_llm(
    *,
    provider: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> BaseLLM:
    settings = get_settings()

    resolved_provider = (provider or settings.llm_provider or "openai").strip().lower()
    resolved_api_key = api_key if api_key is not None else settings.llm_api_key or None
    resolved_base_url = base_url if base_url is not None else settings.llm_base_url or None
    configured_model = model if model is not None else settings.llm_model or None

    match resolved_provider:
        case "openai":
            return OpenAIAdapter(
                api_key=resolved_api_key,
                base_url=resolved_base_url or "https://api.openai.com/v1",
                model=configured_model or "gpt-4.1-mini",
            )
        case "claude" | "anthropic":
            return ClaudeAdapter(
                api_key=resolved_api_key,
                base_url=resolved_base_url or "https://api.anthropic.com",
                model=configured_model or "claude-sonnet-4-20250514",
            )
        case "ollama":
            return OllamaAdapter(
                base_url=resolved_base_url or "http://localhost:11434",
                model=configured_model or "qwen2.5:7b",
            )
        case _:
            raise ValueError(f"Unsupported LLM provider: {resolved_provider}")
