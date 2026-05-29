from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.wechat_client import WeChatClient
from app.models import Project, ProjectDevLog, Repo, User
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


async def request_fix_iteration(
    db: AsyncSession,
    *,
    project: Project,
    repo: Repo,
    fix_description: str,
) -> int:
    """Dispatch a code-fix iteration to dev-agent.

    Creates a new GitHub Issue describing the fix request (with the original
    PRD as context), points `project.github_issue_number` at it, flips
    `project.status -> APPROVED` so dev-agent's claim poller picks it up.
    Returns the new issue number.

    The caller is responsible for committing and for messaging the user.
    """
    # 数当前是第几轮 fix（前面已开过几个 dev_log 标记）
    fix_round_stmt = select(func.count(ProjectDevLog.id)).where(
        ProjectDevLog.project_id == project.id,
        ProjectDevLog.message.like("fix iteration #%"),
    )
    prior = (await db.execute(fix_round_stmt)).scalar_one() or 0
    iteration = int(prior) + 1

    prd = (project.prd_content or "").strip()
    prd_block = f"## 原 PRD\n\n{prd}\n\n" if prd else ""
    issue_body = (
        f"## 修复需求（第 {iteration} 轮）\n\n"
        f"{fix_description.strip()}\n\n"
        f"{prd_block}"
        f"---\nSuperUserAI Project ID: {project.id}\n"
        f"Fix Iteration: {iteration}"
    )

    github = GitHubService.for_repo(repo)
    try:
        issue_data = await github.create_issue(
            owner=repo.github_owner,
            repo=repo.github_repo,
            title=f"[SuperUserAI][修复 #{iteration}] {project.title}",
            body=issue_body,
            labels=["superuserai", "auto-dev", "fix"],
        )
    finally:
        await github.close()

    issue_number = int(issue_data["number"])
    project.github_issue_number = issue_number
    project.status = ProjectStatus.APPROVED.value
    db.add(ProjectDevLog(
        project_id=project.id,
        message=f"fix iteration #{iteration}: issue #{issue_number} — {fix_description.strip()[:200]}",
    ))
    await db.flush()
    return issue_number


async def notify_creator_targeted(
    db: AsyncSession,
    wechat: WeChatClient,
    project: Project,
    body: str,
) -> None:
    """如果 project 来自群,发到群里并 @ creator;否则私聊 creator。失败仅记录日志。"""
    creator = await db.get(User, project.creator_id)
    if creator is None or not creator.wechat_user_id:
        return

    creator_label = creator.nickname or creator.wechat_user_id
    try:
        if project.wechat_group_id:
            # 群消息: msg 里手动拼上 @昵称 让接收者看到提示,at_list 触发企微高亮通知
            text = f"@{creator_label} {body}"
            await wechat.send_at_group(
                project.wechat_group_id,
                [creator.wechat_user_id],
                text,
            )
        else:
            await wechat.send_text(creator.wechat_user_id, body)
    except Exception:
        logger.exception(
            "notify creator failed project=%s group=%s",
            project.id,
            project.wechat_group_id,
        )


async def notify_admins(
    db: AsyncSession,
    wechat: WeChatClient,
    body: str,
) -> int:
    """私聊所有管理员（role=='admin' 且绑定了 wechat_user_id）。

    用于运维告警（如部署失败）。尽力而为：单个发送失败只记录日志，
    不影响其余管理员；返回成功投递的人数。
    """
    stmt = select(User).where(
        User.role == "admin",
        User.wechat_user_id.is_not(None),
    )
    admins = list((await db.execute(stmt)).scalars().all())
    sent = 0
    for admin in admins:
        try:
            await wechat.send_text(admin.wechat_user_id, body)
            sent += 1
        except Exception:
            logger.exception("notify_admins failed admin=%s", admin.wechat_user_id)
    return sent


async def notify_creator_approved(
    db: AsyncSession,
    wechat: WeChatClient,
    project: Project,
) -> None:
    body = (
        f"✅ 你的需求《{project.title}》已通过审核，"
        "AI 正在排队开发，完成后会再通知你验收。"
    )
    await notify_creator_targeted(db, wechat, project, body)


async def notify_creator_rejected(
    db: AsyncSession,
    wechat: WeChatClient,
    project: Project,
    reason: str,
) -> None:
    body = f"⚠️ 你的需求《{project.title}》未通过审核。"
    if reason and reason.strip():
        body += f"\n\n理由：{reason.strip()[:600]}"
    body += "\n\n如需调整请重新发起 #新需求 或联系管理员。"
    await notify_creator_targeted(db, wechat, project, body)


async def notify_creator_dev_failed(
    db: AsyncSession,
    wechat: WeChatClient,
    project: Project,
    reason: str,
) -> None:
    body = f"⚠️ 需求《{project.title}》自动开发失败。"
    if reason and reason.strip():
        body += f"\n\n失败原因:\n{reason.strip()[:600]}"
    body += "\n\n已暂时挂起，请联系管理员排查后再决定是否重试。"
    await notify_creator_targeted(db, wechat, project, body)
