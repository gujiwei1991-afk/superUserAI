"""End-to-end smoke test for the PM chat flow.

Runs without going through HTTP / vworkApi. Replaces WeChatClient with a
recorder so the handler doesn't try to POST to the unreachable Windows host.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "shared"))

from app.database import AsyncSessionLocal  # noqa: E402
from app.gateway.command_parser import parse_command  # noqa: E402
from app.services.message_handler import MessageHandler  # noqa: E402


class RecordingWeChat:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_text(self, user_id: str, msg: str):
        self.sent.append((user_id, msg))
        return {"status": "ok"}

    async def send_card_link(self, *args, **kwargs):
        return {"status": "ok"}


WECHAT_USER = "test-user-001"


async def run_command(content: str) -> str:
    cmd = parse_command(content)
    print(f"\n>>> 用户输入: {content!r}  → command.type={cmd.type}")
    async with AsyncSessionLocal() as db:
        wechat = RecordingWeChat()
        handler = MessageHandler(db, wechat)  # type: ignore[arg-type]
        reply = await handler.handle(WECHAT_USER, cmd)
    print(f"<<< Bot 回复:\n{reply}")
    return reply


async def main() -> None:
    await run_command("#新需求 sandbox 一个 React + Vite 单页应用：极简待办事项管理。要求：1) 真正的 package.json 与 vite 配置，npm install && npm test 必须通过；2) 必须包含至少一个 vitest 单元测试覆盖核心组件；3) 新增/勾选完成/删除三个核心功能。")
    await run_command("不需要登录、不需要持久化，所有人共用一个内存列表即可。")
    await run_command("#确认")


if __name__ == "__main__":
    asyncio.run(main())
