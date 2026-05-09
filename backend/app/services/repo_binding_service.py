from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.wechat_client import WeChatClient
from app.models import Repo

logger = logging.getLogger(__name__)


class BindingConflictError(Exception):
    """Raised when wechat_group_id is already taken by another repo."""


class RepoNotFoundError(Exception):
    """Raised when the target repo doesn't exist."""


class RepoBindingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def bind(
        self,
        repo_id: int,
        wechat_group_id: str,
        bound_by: int,
        note: str | None = None,
    ) -> Repo:
        del note  # reserved for future, not stored yet
        normalized = wechat_group_id.strip()
        if not normalized:
            raise ValueError("wechat_group_id must be non-empty")

        repo = await self.db.get(Repo, repo_id)
        if repo is None:
            raise RepoNotFoundError(f"repo {repo_id} not found")

        # Idempotent: re-bind same pair -> no-op
        if repo.wechat_group_id == normalized:
            return repo

        # Conflict: group already bound to another repo
        existing = (
            await self.db.execute(
                select(Repo).where(
                    Repo.wechat_group_id == normalized,
                    Repo.id != repo_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise BindingConflictError(
                f"group {normalized} already bound to repo {existing.id}"
            )

        repo.wechat_group_id = normalized
        repo.wechat_group_bound_at = datetime.utcnow()
        repo.wechat_group_bound_by = bound_by
        await self.db.flush()
        logger.info(
            "repo_binding bind repo=%s group=%s by=%s",
            repo_id, normalized, bound_by,
        )
        return repo

    async def unbind(self, repo_id: int) -> Repo:
        repo = await self.db.get(Repo, repo_id)
        if repo is None:
            raise RepoNotFoundError(f"repo {repo_id} not found")

        if repo.wechat_group_id is None:
            return repo  # idempotent

        old_group = repo.wechat_group_id
        repo.wechat_group_id = None
        repo.wechat_group_bound_at = None
        repo.wechat_group_bound_by = None
        await self.db.flush()
        logger.info("repo_binding unbind repo=%s old_group=%s", repo_id, old_group)
        return repo


async def send_welcome(wechat: WeChatClient, group_id: str, repo_name: str) -> None:
    """Send a welcome message to the bound group. Logs but doesn't raise on failure."""
    try:
        await wechat.send_text(
            group_id,
            (
                f"本群已绑定 [{repo_name}] 仓库。\n"
                "@我并直接说出你的需求即可，例如：'我想加个登录功能'。\n"
                "我会引导你补充细节，最后请你确认开发方案。"
            ),
        )
    except Exception:
        logger.exception("send_welcome failed group=%s repo=%s", group_id, repo_name)


async def send_unbind_notice(wechat: WeChatClient, group_id: str, repo_name: str) -> None:
    try:
        await wechat.send_text(
            group_id,
            f"本群已与 [{repo_name}] 仓库解除绑定，自然语言提需求功能已关闭。",
        )
    except Exception:
        logger.exception(
            "send_unbind_notice failed group=%s repo=%s", group_id, repo_name
        )
