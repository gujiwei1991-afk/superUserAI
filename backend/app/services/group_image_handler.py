from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.pm_agent import has_ready_marker, strip_ready_marker
from app.config import get_settings
from app.gateway.wechat_client import WeChatClient
from app.services.image_bridge_client import BridgeError, ImageBridgeClient
from app.services.message_handler import MessageHandler
from app.services.project_service import ProjectService
from app.services.session_manager import SessionManager
from shared.constants import ProjectStatus

logger = logging.getLogger(__name__)


class GroupImageHandler:
    def __init__(
        self,
        db: AsyncSession,
        wechat: WeChatClient,
        bridge_client: ImageBridgeClient | None = None,
        llm=None,
    ) -> None:
        self.db = db
        self.wechat = wechat
        self.settings = get_settings()
        self.bridge = bridge_client or ImageBridgeClient()
        self.session_manager = SessionManager(db)
        self.project_service = ProjectService(db)
        self.handler = MessageHandler(db, wechat)
        if llm is not None:
            # Allow tests to inject a stub LLM
            self.handler.pm_agent.llm = llm

    async def try_handle(
        self,
        wechat_user_id: str,
        group_id: str,
        image_meta: dict[str, Any],
        msg_id: str,
    ) -> bool:
        """Returns True iff the group is bound and the image was attempted."""
        repo = await self.project_service.get_repo_by_wechat_group_id(group_id)
        if repo is None:
            return False

        try:
            await self._handle_bound(repo, wechat_user_id, group_id, image_meta, msg_id)
            await self.db.commit()
        except Exception:
            logger.exception(
                "group_image handler failed group=%s repo=%s sender=%s msg_id=%s",
                group_id, repo.id, wechat_user_id, msg_id,
            )
            await self.db.rollback()
        return True

    async def _handle_bound(
        self,
        repo,
        wechat_user_id: str,
        group_id: str,
        image_meta: dict[str, Any],
        msg_id: str,
    ) -> None:
        # 1. Resolve user (auto-activate same as text path).
        user, just_created = await self.session_manager.get_or_create_user_for_bound_group(
            wechat_user_id,
            auto_activate=self.settings.group_bound_auto_activate,
        )
        if just_created:
            logger.info(
                "auto_activate user=%s via bound_group=%s repo=%s (image)",
                wechat_user_id, group_id, repo.id,
            )
        if user.role != "admin" and not user.is_active:
            return  # whitelist gate, silent

        # 2. Must have an active drafting project.
        session = await self.session_manager.get_session(user)
        if session.active_project_id is None:
            return
        project = await self.project_service.get_project(session.active_project_id)
        if project is None or project.status != ProjectStatus.DRAFTING.value:
            return

        # 3. Validate image_meta shape.
        try:
            cdn_key = str(image_meta["cdn_key"])
            aes_key = str(image_meta["aes_key"])
            size = int(image_meta["size"])
            img_type = int(image_meta.get("img_type", 2))
        except (KeyError, TypeError, ValueError):
            logger.warning("group_image bad meta group=%s msg_id=%s meta=%s",
                           group_id, msg_id, image_meta)
            return

        # 4. Fetch via bridge.
        try:
            result = await self.bridge.fetch_image(
                cdn_key=cdn_key, aes_key=aes_key, size=size,
                img_type=img_type, msg_id=msg_id,
            )
        except BridgeError as exc:
            logger.warning(
                "group_image bridge fail group=%s msg_id=%s short=%s detail=%s",
                group_id, msg_id, exc.short, exc.detail,
            )
            await self._reply_at(
                group_id, wechat_user_id,
                f"@{wechat_user_id} 刚才那张图我读不到（{exc.short}），"
                "能用文字补充一下吗？",
            )
            return

        # 5. Persist image as a message row.
        await self.project_service.add_message(
            project.id, wechat_user_id, "user", "[图片]",
            media_url=result.url, media_type=result.media_type,
        )

        # 6. Run PMAgent over full history (now includes the image).
        history = await self.project_service.get_messages(project.id)
        ai_reply = await self.handler.pm_agent.chat(project, repo, history, "")
        await self.project_service.add_message(
            project.id, wechat_user_id, "assistant", ai_reply,
        )

        # 7. Send reply with [READY_TO_CONFIRM] strip.
        if has_ready_marker(ai_reply):
            cleaned = strip_ready_marker(ai_reply)
            hint = self.handler.pm_agent.build_confirm_hint()
            ai_reply = (cleaned + hint) if cleaned else hint.lstrip()

        await self._reply_at(group_id, wechat_user_id, f"@{wechat_user_id} {ai_reply}")

    async def _reply_at(self, group_id: str, sender_id: str, msg: str) -> None:
        try:
            await self.wechat.send_at_group(group_id, [sender_id], msg)
        except Exception:
            logger.exception(
                "group_image send_at_group failed group=%s sender=%s",
                group_id, sender_id,
            )
