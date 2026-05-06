"""Smoke-test the #评分 closing step."""
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


async def run(content: str) -> str:
    cmd = parse_command(content)
    async with AsyncSessionLocal() as db:
        handler = MessageHandler(db, RecordingWeChat())  # type: ignore[arg-type]
        reply = await handler.handle(WECHAT_USER, cmd)
    print(f">>> {content}\n<<< {reply}\n")
    return reply


async def main():
    await run("#状态")
    await run("#评分 9 整体功能符合预期，UI 简洁好用")
    await run("#状态")


if __name__ == "__main__":
    asyncio.run(main())
