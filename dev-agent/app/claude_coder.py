"""Run Claude Code locally against a cloned repo.

Invokes the host's `claude` CLI in headless mode (`-p`) with cwd set to the
cloned repo. Claude edits files in place; the worker handles git add/commit/push
afterwards. Reuses the host's OAuth login — no token needs to be configured.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from app.config import get_settings

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str], Awaitable[None]]

ALLOWED_TOOLS = "Bash,Read,Write,Edit,Glob,Grep,WebFetch,WebSearch,TodoWrite"


@dataclass(slots=True)
class ClaudeRunResult:
    summary: str
    cost_usd: float | None
    duration_ms: int | None
    num_turns: int | None


class ClaudeCoderError(RuntimeError):
    pass


class ClaudeCoder:
    def __init__(self) -> None:
        settings = get_settings()
        self._executable = settings.claude_executable
        self._timeout = settings.claude_timeout_seconds

    async def develop(
        self,
        prompt: str,
        repo_path: str | Path,
        on_milestone: ProgressCallback | None = None,
    ) -> ClaudeRunResult:
        repo_dir = Path(repo_path).resolve()
        if not repo_dir.is_dir():
            raise ClaudeCoderError(f"repo_path is not a directory: {repo_dir}")

        cmd = [
            self._executable,
            "-p", prompt,
            "--output-format", "stream-json",
            "--include-partial-messages",
            "--verbose",
            "--permission-mode", "acceptEdits",
            "--allowedTools", ALLOWED_TOOLS,
            "--add-dir", str(repo_dir),
        ]

        logger.info("Launching claude in %s", repo_dir)
        await self._notify(on_milestone, "🤖 Claude Code 开始分析仓库并制定方案...")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(repo_dir),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stdout is not None and proc.stderr is not None

        events_seen = {"plan_announced": False, "code_announced": False}
        result_summary = ""
        cost_usd: float | None = None
        duration_ms: int | None = None
        num_turns: int | None = None
        stderr_buffer: list[str] = []

        async def drain_stderr() -> None:
            assert proc.stderr is not None
            async for line in proc.stderr:
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    stderr_buffer.append(text)
                    logger.info("[claude stderr] %s", text)

        stderr_task = asyncio.create_task(drain_stderr())

        try:
            while True:
                try:
                    line = await asyncio.wait_for(proc.stdout.readline(), timeout=self._timeout)
                except asyncio.TimeoutError:
                    proc.kill()
                    raise ClaudeCoderError("Claude CLI timed out") from None

                if not line:
                    break

                try:
                    event = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type")

                if event_type == "assistant":
                    content = event.get("message", {}).get("content", [])
                    for block in content if isinstance(content, list) else []:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "tool_use":
                            tool = block.get("name", "")
                            if tool in ("Edit", "Write") and not events_seen["code_announced"]:
                                events_seen["code_announced"] = True
                                await self._notify(
                                    on_milestone,
                                    "✏️ 开始编写代码...",
                                )
                            elif tool in ("Read", "Glob", "Grep") and not events_seen["plan_announced"]:
                                events_seen["plan_announced"] = True
                                await self._notify(
                                    on_milestone,
                                    "🔍 正在阅读仓库代码、制定实施方案...",
                                )
                elif event_type == "result":
                    result_summary = str(event.get("result") or "")
                    cost_usd = event.get("total_cost_usd")
                    duration_ms = event.get("duration_ms")
                    num_turns = event.get("num_turns")
                    if event.get("subtype") not in (None, "success"):
                        raise ClaudeCoderError(
                            f"Claude CLI finished with subtype={event.get('subtype')}: "
                            f"{result_summary[:200]}"
                        )

            await proc.wait()
        finally:
            stderr_task.cancel()
            try:
                await stderr_task
            except (asyncio.CancelledError, Exception):
                pass

        if proc.returncode != 0:
            tail = "\n".join(stderr_buffer[-20:]) or "(no stderr)"
            raise ClaudeCoderError(
                f"claude exited with code {proc.returncode}\n--- stderr ---\n{tail}"
            )

        return ClaudeRunResult(
            summary=result_summary,
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            num_turns=num_turns,
        )

    @staticmethod
    async def _notify(callback: ProgressCallback | None, message: str) -> None:
        if callback is None:
            return
        try:
            await callback(message)
        except Exception:
            logger.exception("milestone callback failed: %s", message)
