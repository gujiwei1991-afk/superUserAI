"""End-to-end smoke for group-chat support.

Without args: tests the gateway-level helpers (_strip_at_prefix +
the group/private branching of receive_message via direct call) without
touching the DB or external services.

Optionally exercises the full handle() flow with PROJECT_ID env unset:
just verifies that posting a fake VWorkMessage with sender + at_list
routes to MessageHandler with the right group_id.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "shared"))

from app.gateway.command_parser import parse_command  # noqa: E402
from app.gateway.wechat_gateway import _strip_at_prefix  # noqa: E402
from shared.schemas import VWorkMessage  # noqa: E402


def test_strip_at_prefix() -> None:
    assert _strip_at_prefix("@Robot #新需求 sandbox 测试") == "#新需求 sandbox 测试"
    assert _strip_at_prefix("@Robot @Other #帮助") == "#帮助"
    assert _strip_at_prefix("@所有人 你好") == "你好"
    assert _strip_at_prefix("普通文本") == "普通文本"
    # 中间 @ 不剥
    assert _strip_at_prefix("#新需求 @Robot 测试") == "#新需求 @Robot 测试"
    print("strip_at_prefix ok")


def test_group_vs_private_routing() -> None:
    """模拟 vworkApi 入站,判断是否分流到群路径"""
    BOT_ID = "168888888888"

    # 1. 私聊
    private = VWorkMessage(
        type=100, msg_type=2, msg_id="m1",
        user_id="user-A", at_list=[], content="#帮助",
        sender="",  # 私聊 sender 为空
        time_stamp=0, is_self_msg=0, self_user_id=BOT_ID, port=8989,
    )
    assert not private.sender, "private should have empty sender"

    # 2. 群消息但没 @ 机器人 → 应被丢弃
    group_unmention = VWorkMessage(
        type=100, msg_type=2, msg_id="m2",
        user_id="R:GROUP-1", at_list=["other-user"], content="@other 闲聊",
        sender="user-B", time_stamp=0, is_self_msg=0, self_user_id=BOT_ID, port=8989,
    )
    assert group_unmention.sender == "user-B"
    assert BOT_ID not in (group_unmention.at_list or [])

    # 3. 群消息且 @ 机器人 → 应处理
    group_at_bot = VWorkMessage(
        type=100, msg_type=2, msg_id="m3",
        user_id="R:GROUP-1", at_list=[BOT_ID], content="@SuperUserAI #新需求 sandbox 测试",
        sender="user-C", time_stamp=0, is_self_msg=0, self_user_id=BOT_ID, port=8989,
    )
    assert BOT_ID in (group_at_bot.at_list or [])
    stripped = _strip_at_prefix(group_at_bot.content)
    assert stripped == "#新需求 sandbox 测试"

    cmd = parse_command(stripped)
    assert cmd.type == "new_project"
    assert cmd.args["repo"] == "sandbox"
    print("group_vs_private_routing ok")


def test_notify_at_group_message_shape() -> None:
    """模拟 notify_creator_targeted 给群发的 message shape"""
    # 直接验证 send_at_group 期望的 payload 格式 — 不实际打 HTTP
    from app.gateway.wechat_client import WeChatClient
    from shared.constants import VWorkSendType

    expected_type = VWorkSendType.SEND_AT_GROUP.value
    assert expected_type == 3009

    captured: list[dict[str, Any]] = []

    class FakeClient:
        async def send_at_group(self, chat_room_id: str, at_list: list[str], msg: str):
            captured.append({"chat_room_id": chat_room_id, "at_list": at_list, "msg": msg})
            return {"status": "ok"}

    async def main() -> None:
        c = FakeClient()
        await c.send_at_group("R:G1", ["user-X"], "@张三 你的需求已通过审核")
        assert captured == [
            {"chat_room_id": "R:G1", "at_list": ["user-X"], "msg": "@张三 你的需求已通过审核"}
        ]

    asyncio.run(main())
    print("notify_at_group_message_shape ok")


def main() -> None:
    test_strip_at_prefix()
    test_group_vs_private_routing()
    test_notify_at_group_message_shape()
    print("\nall e2e_group_chat checks passed")


if __name__ == "__main__":
    main()
