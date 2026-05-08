from __future__ import annotations

import hmac
import json
import logging
import re
from hashlib import sha256
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.gateway.wechat_client import WeChatClient
from app.models import Project
from app.services.project_review import notify_creator_targeted
from shared.constants import ProjectStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")
wechat = WeChatClient()


def verify_github_signature(secret: str, body: bytes, signature: str | None) -> bool:
    if not secret or not signature:
        return False

    expected_signature = f"sha256={hmac.new(secret.encode('utf-8'), body, sha256).hexdigest()}"
    return hmac.compare_digest(expected_signature, signature)


@router.post("/webhooks/github")
async def github_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    settings = get_settings()
    if settings.github_webhook_secret:
        if not verify_github_signature(settings.github_webhook_secret, body, signature):
            raise HTTPException(status_code=401, detail="Invalid GitHub webhook signature")

    event = request.headers.get("X-GitHub-Event", "")
    payload: dict[str, Any] = json.loads(body.decode("utf-8") or "{}")

    if event == "pull_request":
        await _handle_pull_request_event(payload, db)
    elif event == "workflow_run":
        await _handle_workflow_run_event(payload, db)
    elif event == "ping":
        logger.info("Received GitHub ping event: zen=%s", payload.get("zen", ""))
    else:
        logger.info("Ignoring unsupported GitHub event: %s", event)

    await db.commit()
    return {"status": "ok"}


async def _handle_pull_request_event(payload: dict[str, Any], db: AsyncSession) -> None:
    pull_request = payload.get("pull_request") or {}
    if payload.get("action") != "closed" or pull_request.get("merged") is not True:
        return

    pr_number = payload.get("number") or pull_request.get("number")
    if not isinstance(pr_number, int):
        logger.info("Ignoring pull_request event with invalid PR number: %s", pr_number)
        return

    result = await db.execute(select(Project).where(Project.github_pr_number == pr_number))
    project = result.scalar_one_or_none()
    if project is None:
        logger.info("No project found for merged PR #%s", pr_number)
        return

    project.status = ProjectStatus.DEPLOYED.value
    await _notify_project_creator(
        db,
        project,
        (
            f"✅ 需求《{project.title}》对应的 GitHub PR #{pr_number} 已合并，代码已部署。\n\n"
            "请去验证一下功能是否符合预期：\n"
            "• 验收通过：发送  #评分 <1-10> <反馈内容>  完成闭环\n"
            "• 还有问题：发送  #修改 <修改建议>  让 AI 继续调整\n"
        ),
    )


async def _handle_workflow_run_event(payload: dict[str, Any], db: AsyncSession) -> None:
    workflow_run = payload.get("workflow_run") or {}
    if payload.get("action") != "completed" or workflow_run.get("conclusion") != "success":
        return

    head_branch = workflow_run.get("head_branch", "")
    match = re.fullmatch(r"feat/issue-(\d+)", head_branch)
    if match is None:
        logger.info("Ignoring workflow_run event with unmatched branch: %s", head_branch)
        return

    issue_number = int(match.group(1))
    result = await db.execute(select(Project).where(Project.github_issue_number == issue_number))
    project = result.scalar_one_or_none()
    if project is None:
        logger.info("No project found for workflow issue #%s", issue_number)
        return

    if project.status != ProjectStatus.DEVELOPING.value:
        logger.info(
            "Ignoring workflow_run event for project id=%s with status=%s",
            project.id,
            project.status,
        )
        return

    project.status = ProjectStatus.DEPLOYED.value
    await _notify_project_creator(
        db,
        project,
        (
            f"🚀 需求《{project.title}》已部署成功。\n\n"
            "请验证一下功能：\n"
            "• 验收通过：发送  #评分 <1-10> <反馈内容>  完成闭环\n"
            "• 还有问题：发送  #修改 <修改建议>  让 AI 继续调整\n"
        ),
    )


async def _notify_project_creator(
    db: AsyncSession,
    project: Project,
    message: str,
) -> None:
    # 走共享 helper:有 group_id 就发群里 @ creator,否则私聊 creator;失败已在 helper 内吞掉。
    await notify_creator_targeted(db, wechat, project, message)
