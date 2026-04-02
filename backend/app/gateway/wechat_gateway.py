from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.gateway.command_parser import parse_command
from app.gateway.wechat_client import WeChatClient
from app.services import MessageHandler
from shared.constants import VWorkMsgType
from shared.schemas import VWorkMessage

logger = logging.getLogger(__name__)

router = APIRouter()
wechat = WeChatClient()


@router.post("/msg")
async def receive_message(
    message: VWorkMessage,
    db: AsyncSession = Depends(get_db),
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
    handler = MessageHandler(db, wechat)
    await handler.handle(message.user_id, command)
    return {"status": "ok"}
