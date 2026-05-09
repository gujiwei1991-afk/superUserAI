"""LLM adapter that runs the host's `claude` CLI in headless mode.

Reuses the host's Claude Code OAuth login — no API key required. Tools are
disabled (`--tools ""`) so the model only chats; it cannot edit files or run
commands. Multi-turn history is flattened into a single CLI invocation:

  - All `system` messages → joined and passed via `--append-system-prompt`
  - All prior `user`/`assistant` messages → injected as a "Conversation history"
    block at the end of the system prompt
  - The final `user` message → the `-p` prompt
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

from app.llm.base import BaseLLM, LLMResponse

logger = logging.getLogger(__name__)


class ClaudeCLIAdapter(BaseLLM):
    def __init__(
        self,
        *,
        executable: str = "claude",
        model: str = "claude-cli",
        timeout: int = 180,
    ) -> None:
        super().__init__(model=model or "claude-cli", api_key=None, base_url=None)
        self._executable = executable
        self._timeout = timeout

    async def chat(
        self,
        messages: Sequence[Mapping[str, Any]],
        **kwargs: Any,
    ) -> LLMResponse:
        # Multimodal content: flatten image_url parts into "[image: <URL>]" tokens
        # so the URL is preserved in plain text for the CLI prompt.
        flattened = self._flatten_to_text(
            self._normalize_messages_keep_multimodal(messages)
        )
        base_system, conversation = self._split_system(flattened)
        history, current_user = self._partition_last_user(conversation)
        composed_system = self._compose_system(base_system, history)

        cmd = [
            self._executable,
            "-p", current_user or "(空消息)",
            "--output-format", "text",
            "--tools", "",
        ]
        if composed_system:
            cmd += ["--append-system-prompt", composed_system]

        logger.info("Invoking claude CLI for PM chat (history=%d msgs)", len(history))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError("Claude CLI timed out") from None

        if proc.returncode != 0:
            tail = stderr_b.decode("utf-8", errors="replace").strip()[-1000:]
            raise RuntimeError(
                f"Claude CLI exited with {proc.returncode}: {tail or '(no stderr)'}"
            )

        return LLMResponse(
            content=stdout_b.decode("utf-8", errors="replace").strip(),
            model=self.model,
            finish_reason="stop",
            raw=None,
        )

    async def stream_chat(
        self,
        messages: Sequence[Mapping[str, Any]],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        result = await self.chat(messages, **kwargs)
        yield result.content

    @staticmethod
    def _split_system(
        messages: list[dict[str, str]],
    ) -> tuple[str, list[dict[str, str]]]:
        system_parts = [m["content"] for m in messages if m["role"] == "system"]
        rest = [m for m in messages if m["role"] != "system"]
        joined = "\n\n".join(p.strip() for p in system_parts if p.strip())
        return joined, rest

    @staticmethod
    def _partition_last_user(
        conversation: list[dict[str, str]],
    ) -> tuple[list[dict[str, str]], str]:
        for i in range(len(conversation) - 1, -1, -1):
            if conversation[i]["role"] == "user":
                return conversation[:i], conversation[i]["content"]
        return conversation, ""

    @staticmethod
    def _flatten_to_text(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
        """Turn multimodal content blocks into plain text with [image: URL] tokens."""
        out: list[dict[str, str]] = []
        for m in messages:
            content = m.get("content", "")
            if isinstance(content, list):
                parts: list[str] = []
                for p in content:
                    if not isinstance(p, dict):
                        continue
                    if p.get("type") == "text" and isinstance(p.get("text"), str):
                        parts.append(p["text"])
                    elif p.get("type") == "image_url":
                        url = (p.get("image_url") or {}).get("url")
                        if isinstance(url, str) and url:
                            parts.append(f"[image: {url}]")
                out.append({"role": m["role"], "content": "\n".join(parts)})
            else:
                out.append({"role": m["role"], "content": str(content)})
        return out

    @staticmethod
    def _compose_system(base: str, history: list[dict[str, str]]) -> str:
        parts: list[str] = []
        if base:
            parts.append(base)
        if history:
            lines = ["【对话历史】"]
            role_labels = {"user": "用户", "assistant": "助手"}
            for m in history:
                label = role_labels.get(m["role"], m["role"])
                lines.append(f"{label}: {m['content']}")
            lines.append("")
            lines.append("【任务】请基于上述上下文回应用户的最新消息，保持对话连贯。")
            parts.append("\n".join(lines))
        return "\n\n".join(parts)
