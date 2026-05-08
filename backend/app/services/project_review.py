from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.wechat_client import WeChatClient
from app.models import Project, Repo, User
from app.services.github_service import GitHubService
from shared.constants import ProjectStatus

logger = logging.getLogger(__name__)


async def create_issue_for_project(
    db: AsyncSession,
    *,
    project: Project,
    repo: Repo,
    approver_id: int,
) -> int:
    github = GitHubService.for_repo(repo)
    footer = f"---\nSuperUserAI Project ID: {project.id}"
    issue_body = (
        f"{project.prd_content.strip()}\n\n{footer}"
        if project.prd_content and project.prd_content.strip()
        else footer
    )

    try:
        issue_data = await github.create_issue(
            owner=repo.github_owner,
            repo=repo.github_repo,
            title=f"[SuperUserAI] {project.title}",
            body=issue_body,
            labels=["superuserai", "auto-dev"],
        )
    finally:
        await github.close()

    issue_number = int(issue_data["number"])
    project.github_issue_number = issue_number
    project.approver_id = approver_id
    project.status = ProjectStatus.APPROVED.value
    await db.flush()
    return issue_number


async def notify_creator_approved(
    db: AsyncSession,
    wechat: WeChatClient,
    project: Project,
) -> None:
    creator = await db.get(User, project.creator_id)
    if creator is None or not creator.wechat_user_id:
        return
    try:
        await wechat.send_text(
            creator.wechat_user_id,
            (
                f"✅ 你的需求《{project.title}》已通过审核，"
                "AI 正在排队开发，完成后会再通知你验收。"
            ),
        )
    except Exception:
        logger.exception("notify creator approved failed project=%s", project.id)


async def notify_creator_rejected(
    db: AsyncSession,
    wechat: WeChatClient,
    project: Project,
    reason: str,
) -> None:
    creator = await db.get(User, project.creator_id)
    if creator is None or not creator.wechat_user_id:
        return
    body = f"⚠️ 你的需求《{project.title}》未通过审核。"
    if reason and reason.strip():
        body += f"\n\n理由：{reason.strip()[:600]}"
    body += "\n\n如需调整请重新发起 #新需求 或联系管理员。"
    try:
        await wechat.send_text(creator.wechat_user_id, body)
    except Exception:
        logger.exception("notify creator rejected failed project=%s", project.id)


async def notify_creator_dev_failed(
    db: AsyncSession,
    wechat: WeChatClient,
    project: Project,
    reason: str,
) -> None:
    creator = await db.get(User, project.creator_id)
    if creator is None or not creator.wechat_user_id:
        return
    body = f"⚠️ 需求《{project.title}》自动开发失败。"
    if reason and reason.strip():
        body += f"\n\n失败原因:\n{reason.strip()[:600]}"
    body += "\n\n已暂时挂起,请联系管理员排查后再决定是否重试。"
    try:
        await wechat.send_text(creator.wechat_user_id, body)
    except Exception:
        logger.exception("notify creator dev_failed project=%s", project.id)
