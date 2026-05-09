from __future__ import annotations

import logging
import re

from fastapi import APIRouter, BackgroundTasks

from app.database import AsyncSessionLocal
from app.gateway.command_parser import Command, parse_command
from app.gateway.wechat_client import WeChatClient
from app.services import MessageHandler
from shared.constants import VWorkMsgType
from shared.schemas import VWorkMessage

logger = logging.getLogger(__name__)

router = APIRouter()
wechat = WeChatClient()

# 群消息 content 通常是 "@机器人昵称 (空格) 实际内容",可能多个 @ 连缀。
# 把开头的连续 "@xxx (空白)" 一并剥掉,留下真正的指令文本。
_AT_PREFIX_RE = re.compile(r"^(?:@\S+\s+)+")


def _strip_at_prefix(text: str) -> str:
    return _AT_PREFIX_RE.sub("", text or "")


async def _process_message_async(
    user_id: str,
    command: Command,
    group_id: str | None = None,
) -> None:
    async with AsyncSessionLocal() as db:
        try:
            handler = MessageHandler(db, wechat)
            await handler.handle(user_id, command, group_id=group_id)
        except Exception:
            logger.exception(
                "Background message processing failed for user_id=%s group_id=%s command=%s",
                user_id,
                group_id,
                command.type,
            )


async def _process_bound_group_message_async(
    user_id: str,
    group_id: str,
    content: str,
) -> None:
    """Bound-group fast path: try natural-language router first, fall back to legacy
    parse_command if the group has been unbound between request acceptance and dispatch.
    """
    from app.services.group_message_router import GroupMessageRouter

    async with AsyncSessionLocal() as db:
        try:
            router_obj = GroupMessageRouter(db, wechat)
            handled = await router_obj.try_handle(user_id, group_id, content)
            if handled:
                return
            # Group is no longer bound — fall back to legacy parse_command path.
            cmd = parse_command(content)
            handler = MessageHandler(db, wechat)
            await handler.handle(user_id, cmd, group_id=group_id)
        except Exception:
            logger.exception(
                "Bound-group processing failed user_id=%s group_id=%s",
                user_id,
                group_id,
            )


@router.post("/msg")
async def receive_message(
    message: VWorkMessage,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    if message.is_self_msg == 1:
        logger.debug("Ignoring self message: msg_id=%s", message.msg_id)
        return {"status": "ok"}

    if message.msg_type != VWorkMsgType.TEXT.value:
        logger.info(
            "Ignoring non-text message: msg_id=%s msg_type=%s",
            message.msg_id,
            message.msg_type,
        )
        return {"status": "ok"}

    if not isinstance(message.content, str):
        logger.warning("Ignoring text payload with non-string content: msg_id=%s", message.msg_id)
        return {"status": "ok"}

    # 群消息: vworkApi 用 sender 区分 — 私聊 sender 为空,群消息 sender 是发送者 ID,
    # user_id 此时是 chat_room_id。仅当机器人被 @ 才处理,免得无差别响应群内闲聊。
    is_group = bool(message.sender)
    if is_group:
        at_list = message.at_list or []
        if message.self_user_id not in at_list and "notify@all" not in at_list:
            logger.debug(
                "Ignoring group message without @bot: msg_id=%s group_id=%s sender=%s",
                message.msg_id,
                message.user_id,
                message.sender,
            )
            return {"status": "ok"}
        sender_id = message.sender
        group_id: str | None = message.user_id
        content_text = _strip_at_prefix(message.content)
    else:
        sender_id = message.user_id
        group_id = None
        content_text = message.content

    # Bound-group fast path: when the message comes from a group, defer to the
    # bound-group router which decides natural-language vs. legacy parse_command
    # based on the live binding state. Private messages still take the legacy path.
    if group_id is not None:
        logger.info(
            "Received WeChat group message: msg_id=%s user=%s group=%s (deferring bound-check)",
            message.msg_id,
            sender_id,
            group_id,
        )
        background_tasks.add_task(
            _process_bound_group_message_async, sender_id, group_id, content_text
        )
        return {"status": "ok"}

    command = parse_command(content_text)
    logger.info(
        "Received WeChat message: msg_id=%s user=%s group=%s command=%s",
        message.msg_id,
        sender_id,
        group_id,
        command.type,
    )
    background_tasks.add_task(_process_message_async, sender_id, command, group_id)
    return {"status": "ok"}
