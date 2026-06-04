from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.pm_agent import has_ready_marker, strip_ready_marker
from app.config import get_settings
from app.gateway.command_parser import parse_command
from app.gateway.wechat_client import WeChatClient
from app.llm import create_llm
from app.models import Project, Repo, User
from app.services.group_intent import GroupIntentClassifier, Intent, IntentResult
from app.services.message_handler import MessageHandler
from app.services.project_service import ProjectService
from app.services.session_manager import SessionManager

logger = logging.getLogger(__name__)


class GroupMessageRouter:
    def __init__(
        self,
        db: AsyncSession,
        wechat: WeChatClient,
        llm=None,
    ) -> None:
        self.db = db
        self.wechat = wechat
        self.settings = get_settings()
        # v1: share PMAgent's LLM client. A dedicated lightweight provider can
        # be wired later via INTENT_LLM_MODEL without changing call sites.
        self.intent_llm = llm or create_llm()
        self.session_manager = SessionManager(db)
        self.project_service = ProjectService(db)
        self.handler = MessageHandler(db, wechat)
        self.classifier = GroupIntentClassifier(llm=self.intent_llm)

    async def try_handle(
        self,
        wechat_user_id: str,
        group_id: str,
        content: str,
    ) -> bool:
        """Returns True iff this group is bound and the message has been routed."""
        repo = await self.project_service.get_repo_by_wechat_group_id(group_id)
        if repo is None:
            return False

        try:
            await self._handle_bound(repo, wechat_user_id, group_id, content)
            await self.db.commit()
        except Exception:
            logger.exception(
                "bound_group_route failed group=%s repo=%s sender=%s",
                group_id,
                repo.id,
                wechat_user_id,
            )
            await self.db.rollback()
        return True

    async def _handle_bound(
        self,
        repo: Repo,
        wechat_user_id: str,
        group_id: str,
        content: str,
    ) -> None:
        # 1. Resolve user (auto-activate if first-timer).
        user, just_created = await self.session_manager.get_or_create_user_for_bound_group(
            wechat_user_id,
            auto_activate=self.settings.group_bound_auto_activate,
        )
        if just_created:
            logger.info(
                "auto_activate user=%s via bound_group=%s repo=%s",
                wechat_user_id,
                group_id,
                repo.id,
            )

        # 2. Whitelist gate (still applies if auto_activate=False or admin override).
        if user.role != "admin" and not user.is_active:
            logger.info(
                "Whitelist gate: dropping message from inactive user wechat_user_id=%s",
                wechat_user_id,
            )
            return

        session = await self.session_manager.get_session(user)
        project: Project | None = None
        if session.active_project_id is not None:
            project = await self.project_service.get_project(session.active_project_id)

        # 3. Classify.
        history_lines: list[str] = []
        if project is not None:
            messages = await self.project_service.get_messages(project.id)
            history_lines = [f"{m.role}: {m.content}" for m in messages[-5:]]
        result = await self.classifier.classify(
            user, session, project, content, history_lines=history_lines
        )

        logger.info(
            "bound_group_route group=%s repo=%s sender=%s intent=%s",
            group_id,
            repo.id,
            wechat_user_id,
            result.intent.value,
        )

        # 4. Dispatch.
        reply = await self._dispatch(
            result, user, session, wechat_user_id, group_id, repo, content
        )

        # 5. Send reply (mirror MessageHandler.handle's send pattern).
        if not reply:
            return

        # Strip [READY_TO_CONFIRM] marker if present, append confirm hint.
        if has_ready_marker(reply):
            cleaned = strip_ready_marker(reply)
            hint = self.handler.pm_agent.build_confirm_hint()
            reply = (cleaned + hint) if cleaned else hint.lstrip()

        try:
            # @ 提及交给 at_list 渲染,msg 内不再手动拼 @昵称(否则会重复 @)。
            await self.wechat.send_at_group(
                group_id, [wechat_user_id], reply
            )
        except Exception:
            logger.exception(
                "send_at_group failed group=%s sender=%s",
                group_id,
                wechat_user_id,
            )

    async def _dispatch(
        self,
        result: IntentResult,
        user: User,
        session,
        wechat_user_id: str,
        group_id: str,
        repo: Repo,
        original_content: str,
    ) -> str:
        match result.intent:
            case Intent.LEGACY_COMMAND:
                # Fall back to existing parse_command + MessageHandler flow.
                # send=False: handle() 只返回文本,不自己发送 —— 由 _handle_bound
                # 统一发送一次,避免 LEGACY_COMMAND 被双发(handle 内 + _handle_bound)。
                cmd = parse_command(result.content_for_handler)
                return (
                    await self.handler.handle(
                        wechat_user_id, cmd, group_id=group_id, send=False
                    )
                    or ""
                )
            case Intent.OTHER:
                return ""
            case Intent.NEW_PROJECT:
                return await self.handler._handle_new_project_internal(
                    user,
                    session,
                    wechat_user_id,
                    repo,
                    original_content,
                    group_id=group_id,
                )
            case Intent.CHAT:
                return await self.handler._handle_chat_internal(
                    user, session, wechat_user_id, original_content
                )
            case Intent.CONFIRM:
                return await self.handler._handle_confirm(
                    user, session, wechat_user_id
                )
            case Intent.MODIFY:
                return await self.handler._handle_modify_internal(
                    user, session, wechat_user_id, original_content
                )
            case Intent.STATUS:
                return await self.handler._handle_status_internal(user, session)
            case Intent.REVIEW:
                if (
                    result.review_project_id is None
                    or result.review_decision is None
                ):
                    return (
                        "审核命令解析失败，请使用「通过项目 #ID」或「拒绝项目 #ID 理由是 …」。"
                    )
                return await self.handler._handle_review_internal(
                    user,
                    result.review_project_id,
                    result.review_decision,
                    result.review_reason,
                )
            case _:
                logger.warning(
                    "unknown intent %s — falling back to chat", result.intent
                )
                return await self.handler._handle_chat_internal(
                    user, session, wechat_user_id, original_content
                )
