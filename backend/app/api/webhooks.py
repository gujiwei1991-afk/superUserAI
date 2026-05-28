from __future__ import annotations

import hmac
import json
import logging
from hashlib import sha256
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.gateway.wechat_client import WeChatClient
from app.models import DevTask, Project, Repo
from app.services.production_deploy_service import ProductionDeployService
from app.services.staging_deploy_service import StagingDeployService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")
wechat = WeChatClient()


def _build_staging_service() -> StagingDeployService:
    s = get_settings()
    return StagingDeployService(
        wechat_client=wechat,
        ssh_key_path=s.staging_ssh_key_path,
        ssh_user_default=s.staging_ssh_user_default,
        deploy_timeout_sec=s.staging_deploy_timeout_sec,
        log_tail_lines=s.staging_log_tail_lines,
    )


staging_deploy_service = _build_staging_service()


def _build_production_service() -> ProductionDeployService:
    s = get_settings()
    return ProductionDeployService(
        wechat_client=wechat,
        # Fall back to staging key if prod key isn't separately configured.
        ssh_key_path=s.prod_ssh_key_path or s.staging_ssh_key_path,
        ssh_user_default=s.prod_ssh_user_default,
        deploy_timeout_sec=s.prod_deploy_timeout_sec,
        log_tail_lines=s.prod_log_tail_lines,
    )


production_deploy_service = _build_production_service()


def verify_github_signature(secret: str, body: bytes, signature: str | None) -> bool:
    if not secret or not signature:
        return False

    expected_signature = f"sha256={hmac.new(secret.encode('utf-8'), body, sha256).hexdigest()}"
    return hmac.compare_digest(expected_signature, signature)


@router.post("/webhooks/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
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
        action = payload.get("action")
        if action in ("opened", "synchronize", "reopened"):
            await _dispatch_staging_deploy(payload, db, background_tasks)
        else:
            await _handle_pull_request_event(payload, db, background_tasks)
    elif event == "workflow_run":
        await _handle_workflow_run_event(payload, db)
    elif event == "ping":
        logger.info("Received GitHub ping event: zen=%s", payload.get("zen", ""))
    else:
        logger.info("Ignoring unsupported GitHub event: %s", event)

    await db.commit()
    return {"status": "ok"}


async def _handle_pull_request_event(
    payload: dict[str, Any],
    db: AsyncSession,
    background_tasks: BackgroundTasks,
) -> None:
    pull_request = payload.get("pull_request") or {}
    if payload.get("action") != "closed" or pull_request.get("merged") is not True:
        return

    pr_number = payload.get("number") or pull_request.get("number")
    if not isinstance(pr_number, int):
        logger.info("Ignoring pull_request event with invalid PR number: %s", pr_number)
        return

    merge_sha = pull_request.get("merge_commit_sha") or (pull_request.get("head") or {}).get("sha")
    if not isinstance(merge_sha, str) or not merge_sha:
        logger.info("Ignoring merged PR #%s with no merge_commit_sha", pr_number)
        return

    project = (await db.execute(
        select(Project).where(Project.github_pr_number == pr_number)
    )).scalar_one_or_none()
    if project is None:
        logger.info("No project found for merged PR #%s", pr_number)
        return

    repo = (await db.execute(
        select(Repo).where(Repo.id == project.repo_id)
    )).scalar_one_or_none()
    dev_task = (await db.execute(
        select(DevTask)
        .where(DevTask.project_id == project.id)
        .order_by(DevTask.id.desc())
        .limit(1)
    )).scalar_one_or_none()

    if repo is None or dev_task is None:
        logger.info("prod dispatch: missing repo/dev_task for project %s", project.id)
        return

    background_tasks.add_task(
        production_deploy_service.deploy_merge,
        db, repo, project, dev_task, merge_sha, pr_number,
    )


async def _handle_workflow_run_event(payload: dict[str, Any], db: AsyncSession) -> None:
    """Kept for visibility only.

    Production deployment is now driven by the `pull_request closed+merged`
    event via ProductionDeployService — we no longer flip project status
    here, since that would race with (and duplicate) the prod deploy flow.
    """
    workflow_run = payload.get("workflow_run") or {}
    if payload.get("action") != "completed":
        return
    logger.info(
        "workflow_run completed: branch=%s conclusion=%s (informational only)",
        workflow_run.get("head_branch", ""),
        workflow_run.get("conclusion"),
    )


async def _dispatch_staging_deploy(
    payload: dict[str, Any],
    db: AsyncSession,
    background_tasks: BackgroundTasks,
) -> None:
    pr = payload.get("pull_request") or {}
    pr_number = pr.get("number")
    head_sha = (pr.get("head") or {}).get("sha")
    if not isinstance(pr_number, int) or not head_sha:
        logger.info("staging dispatch: invalid pr payload, skipping")
        return

    # 用 pr_number 找 project，再拿 repo 和最新 dev_task
    proj_row = (await db.execute(
        select(Project).where(Project.github_pr_number == pr_number)
    )).scalar_one_or_none()
    if proj_row is None:
        logger.info("staging dispatch: no project for PR #%s", pr_number)
        return

    repo_row = (await db.execute(
        select(Repo).where(Repo.id == proj_row.repo_id)
    )).scalar_one_or_none()
    dt_row = (await db.execute(
        select(DevTask)
        .where(DevTask.project_id == proj_row.id)
        .order_by(DevTask.id.desc())
        .limit(1)
    )).scalar_one_or_none()

    if repo_row is None or dt_row is None:
        logger.info("staging dispatch: missing repo/dev_task for project %s", proj_row.id)
        return

    if dt_row.staging_deploy_status == "deploying":
        logger.info(
            "staging dispatch: dev_task %s already deploying, dispatching anyway "
            "(service will coalesce)",
            dt_row.id,
        )

    background_tasks.add_task(
        staging_deploy_service.deploy_pr,
        db, repo_row, proj_row, dt_row, pr_number, head_sha,
    )
