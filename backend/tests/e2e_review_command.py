"""End-to-end smoke for the #审核 admin command.

Without args: only verifies parse_command behavior.
With PROJECT_ID=<id> env var: runs an actual #审核 通过 against an admin user
in the DB. Use a reviewing-status project; a real GitHub issue will be created.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "shared"))

from sqlalchemy import select  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.gateway.command_parser import parse_command  # noqa: E402
from app.models import User  # noqa: E402
from app.services.message_handler import MessageHandler  # noqa: E402


class RecordingWeChat:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_text(self, user_id: str, msg: str):
        self.sent.append((user_id, msg))
        return {"status": "ok"}

    async def send_card_link(self, *args, **kwargs):
        return {"status": "ok"}


def _check_parser() -> None:
    cmd = parse_command("#审核 12 通过")
    assert cmd.type == "review", cmd
    assert cmd.args["project_id"] == 12
    assert cmd.args["decision"] == "通过"
    assert cmd.args["reason"] == ""

    cmd_reason = parse_command("#审核 5 拒绝 PRD 不够完整")
    assert cmd_reason.type == "review"
    assert cmd_reason.args["reason"] == "PRD 不够完整"

    bad_id = parse_command("#审核 abc 通过")
    assert bad_id.type == "chat", bad_id

    bad_decision = parse_command("#审核 1 maybe")
    assert bad_decision.type == "chat", bad_decision

    too_few = parse_command("#审核 1")
    assert too_few.type == "chat", too_few

    print("parse ok")


async def _run_db_test(project_id: int) -> None:
    async with AsyncSessionLocal() as db:
        admin = (
            await db.execute(
                select(User).where(User.role == "admin").order_by(User.id).limit(1)
            )
        ).scalar_one_or_none()
        if admin is None:
            print("no admin user in DB; skipping db test")
            return

        wechat = RecordingWeChat()
        handler = MessageHandler(db, wechat)  # type: ignore[arg-type]
        cmd = parse_command(f"#审核 {project_id} 通过")
        # Skip handler.handle to avoid the whitelist/session-state plumbing,
        # call the inner method with the real admin user directly.
        reply = await handler._handle_review_command(admin, cmd)
        await db.commit()
        print(f"reply: {reply}")
        print(f"wechat.sent: {wechat.sent}")


async def main() -> None:
    _check_parser()
    pid_env = os.environ.get("PROJECT_ID")
    if pid_env and pid_env.isdigit():
        await _run_db_test(int(pid_env))
    else:
        print("set PROJECT_ID=<reviewing project id> to run db test")


if __name__ == "__main__":
    asyncio.run(main())
