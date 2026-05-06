from __future__ import annotations

import logging

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


async def _process_message_async(user_id: str, command: Command) -> None:
    async with AsyncSessionLocal() as db:
        try:
            handler = MessageHandler(db, wechat)
            await handler.handle(user_id, command)
        except Exception:
            logger.exception(
                "Background message processing failed for user_id=%s command=%s",
                user_id,
                command.type,
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

    command = parse_command(message.content)
    logger.info(
        "Received WeChat message: msg_id=%s user_id=%s command=%s",
        message.msg_id,
        message.user_id,
        command.type,
    )
    background_tasks.add_task(_process_message_async, message.user_id, command)
    return {"status": "ok"}
