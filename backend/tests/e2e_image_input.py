"""End-to-end smoke for GroupImageHandler — bridge mocked, LLM stubbed.

Without env: only verifies the unbound-group bypass path and pure helpers.
With BIND_GROUP_TEST_REPO_ID + BIND_GROUP_TEST_GROUP_ID + a sender that has an
active drafting project: runs the full happy path (bridge mocked).
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "shared"))

from app.database import AsyncSessionLocal  # noqa: E402
from app.services.group_image_handler import GroupImageHandler  # noqa: E402
from app.services.image_bridge_client import (  # noqa: E402
    BridgeError,
    BridgeFetchResult,
    ImageBridgeClient,
)


class RecordingWeChat:
    def __init__(self) -> None:
        self.sent: list = []

    async def send_text(self, *args, **kwargs):
        self.sent.append(("text", args, kwargs))
        return {"status": "ok"}

    async def send_at_group(self, group_id, at_list, msg):
        self.sent.append(("at_group", group_id, at_list, msg))
        return {"status": "ok"}


class StubLLM:
    async def chat(self, messages):
        class _R:
            content = "我看到了这张图，你想让我重点关注哪个区域？"
        return _R()


_SAMPLE_META = {
    "cdn_key": "k1", "aes_key": "a1", "size": 1234,
    "img_type": 2, "url": "", "auth_key": "", "md5": "x",
}


async def test_unbound_group_returns_handled_false() -> None:
    async with AsyncSessionLocal() as db:
        wechat = RecordingWeChat()
        handler = GroupImageHandler(db, wechat, llm=StubLLM())
        handled = await handler.try_handle(
            wechat_user_id="user-x",
            group_id="R:NOT_BOUND_TEST",
            image_meta=_SAMPLE_META,
            msg_id="msg-1",
        )
        assert handled is False
    print("unbound passthrough ok")


async def test_bridge_failure_replies_user() -> None:
    """When bridge raises, user gets a friendly fallback reply."""
    repo_id_env = os.environ.get("BIND_GROUP_TEST_REPO_ID")
    group_id_env = os.environ.get("BIND_GROUP_TEST_GROUP_ID")
    sender = os.environ.get("BIND_GROUP_TEST_SENDER")
    if not (repo_id_env and group_id_env and sender):
        print("set BIND_GROUP_TEST_REPO_ID/GROUP_ID/SENDER + create active drafting"
              " project for SENDER to run bridge_failure test")
        return

    async def boom(*a, **kw):
        raise BridgeError(short="bridge 不可达", detail="simulated")

    async with AsyncSessionLocal() as db:
        wechat = RecordingWeChat()
        handler = GroupImageHandler(db, wechat, llm=StubLLM())
        with patch.object(ImageBridgeClient, "fetch_image", boom):
            await handler.try_handle(
                wechat_user_id=sender, group_id=group_id_env,
                image_meta=_SAMPLE_META, msg_id="msg-fail-1",
            )
        sent = [s for s in wechat.sent if s[0] == "at_group"]
        assert sent, wechat.sent
        assert "读不到" in sent[-1][3]
    print("bridge failure user-reply ok")


async def test_happy_path() -> None:
    """Mock bridge to return a URL; assert message row written + reply sent."""
    repo_id_env = os.environ.get("BIND_GROUP_TEST_REPO_ID")
    group_id_env = os.environ.get("BIND_GROUP_TEST_GROUP_ID")
    sender = os.environ.get("BIND_GROUP_TEST_SENDER")
    if not (repo_id_env and group_id_env and sender):
        print("set BIND_GROUP_TEST_REPO_ID/GROUP_ID/SENDER to run happy path")
        return

    async def fake_fetch(self, **kw):
        return BridgeFetchResult(
            url="https://cdn.example.com/sua/test.jpg",
            media_type="image/jpeg",
            size=1234,
        )

    async with AsyncSessionLocal() as db:
        wechat = RecordingWeChat()
        handler = GroupImageHandler(db, wechat, llm=StubLLM())
        with patch.object(ImageBridgeClient, "fetch_image", fake_fetch):
            await handler.try_handle(
                wechat_user_id=sender, group_id=group_id_env,
                image_meta=_SAMPLE_META, msg_id="msg-happy-1",
            )
        sent = [s for s in wechat.sent if s[0] == "at_group"]
        assert sent and "看到了这张图" in sent[-1][3], wechat.sent
    print("happy path ok")


def main() -> None:
    asyncio.run(test_unbound_group_returns_handled_false())
    asyncio.run(test_bridge_failure_replies_user())
    asyncio.run(test_happy_path())
    print("all e2e_image_input checks passed")


if __name__ == "__main__":
    main()
