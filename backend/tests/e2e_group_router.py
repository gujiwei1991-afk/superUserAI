"""End-to-end smoke for GroupMessageRouter — composes intent classification +
handler dispatch + auto-activation. Uses recording WeChat + stub LLM.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "shared"))

from app.database import AsyncSessionLocal  # noqa: E402
from app.services.group_message_router import GroupMessageRouter  # noqa: E402


class RecordingWeChat:
    def __init__(self) -> None:
        self.sent: list = []

    async def send_text(self, user_id, msg):
        self.sent.append(("text", user_id, msg))
        return {"status": "ok"}

    async def send_at_group(self, group_id, at_list, msg):
        self.sent.append(("at_group", group_id, at_list, msg))
        return {"status": "ok"}


class StubLLM:
    """Always answers 'no' for confirm-verify so we never accidentally promote."""

    async def chat(self, messages):
        class _R:
            content = "no"

        return _R()


async def test_unbound_group_returns_handled_false() -> None:
    """A group not in repos.wechat_group_id should return handled=False."""
    async with AsyncSessionLocal() as db:
        wechat = RecordingWeChat()
        router = GroupMessageRouter(db, wechat, llm=StubLLM())
        handled = await router.try_handle(
            wechat_user_id="user-x",
            group_id="R:NOT_BOUND",
            content="我想加个登录",
        )
        assert handled is False
    print("unbound group passthrough ok")


async def test_bound_group_full_flow() -> None:
    """Full flow only runs when env points at a real bound repo."""
    repo_id_env = os.environ.get("BIND_GROUP_TEST_REPO_ID")
    group_id_env = os.environ.get("BIND_GROUP_TEST_GROUP_ID")
    if not (repo_id_env and group_id_env):
        print("set BIND_GROUP_TEST_REPO_ID + BIND_GROUP_TEST_GROUP_ID to run e2e router test")
        return

    async with AsyncSessionLocal() as db:
        wechat = RecordingWeChat()
        router = GroupMessageRouter(db, wechat, llm=StubLLM())
        handled = await router.try_handle(
            wechat_user_id="router-test-user-001",
            group_id=group_id_env,
            content="我想加一个简单的待办列表，可以勾选完成",
        )
        assert handled is True
        # The recording wechat should have at least one send_at_group call
        assert any(s[0] == "at_group" for s in wechat.sent), wechat.sent
    print("bound group flow ok")


def main() -> None:
    asyncio.run(test_unbound_group_returns_handled_false())
    asyncio.run(test_bound_group_full_flow())
    print("all e2e_group_router checks passed")


if __name__ == "__main__":
    main()
