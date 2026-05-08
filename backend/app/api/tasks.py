from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.gateway.wechat_client import WeChatClient
from app.models import DevTask, Project, ProjectDevLog, Repo, User
from shared.constants import ProjectStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")
wechat = WeChatClient()


class CompleteTaskRequest(BaseModel):
    pr_number: int = Field(gt=0)
    branch: str | None = None
    summary: str | None = None


class FailTaskRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=4000)


class LogProgressRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


@router.get("/tasks/pending")
async def get_pending_tasks(
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    stmt = (
        select(
            Project.id.label("project_id"),
            Repo.github_owner,
            Repo.github_repo,
            Project.github_issue_number,
            Project.title,
        )
        .join(Repo, Project.repo_id == Repo.id)
        .where(
            Project.status == ProjectStatus.APPROVED.value,
            Project.github_issue_number.is_not(None),
        )
        .order_by(Project.created_at.asc())
    )
    result = await db.execute(stmt)
    return [dict(row) for row in result.mappings()]


@router.post("/tasks/{project_id}/completed")
async def complete_task(
    project_id: int,
    payload: CompleteTaskRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    project.github_pr_number = payload.pr_number
    project.status = ProjectStatus.DEVELOPING.value

    db.add(
        DevTask(
            project_id=project.id,
            repo_id=project.repo_id,
            branch=payload.branch,
            pr_number=payload.pr_number,
            status="pr_open",
            summary=payload.summary,
            finished_at=datetime.now(timezone.utc),
        )
    )

    await db.commit()
    await db.refresh(project)

    return {
        "status": "ok",
        "project_id": project.id,
        "github_pr_number": project.github_pr_number,
    }


@router.post("/tasks/{project_id}/failed")
async def fail_task(
    project_id: int,
    payload: FailTaskRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    project.status = ProjectStatus.REJECTED.value

    db.add(
        DevTask(
            project_id=project.id,
            repo_id=project.repo_id,
            branch=None,
            pr_number=None,
            status="failed",
            summary=payload.reason[:4000],
            finished_at=datetime.now(timezone.utc),
        )
    )

    await db.commit()
    await db.refresh(project)

    creator = await db.get(User, project.creator_id)
    if creator is not None and creator.wechat_user_id:
        try:
            await wechat.send_text(
                creator.wechat_user_id,
                (
                    f"⚠️ 需求《{project.title}》自动开发失败：\n\n"
                    f"{payload.reason[:600]}\n\n"
                    "已暂时挂起，请联系管理员排查后再决定是否重试。"
                ),
            )
        except Exception:
            logger.exception("notify creator failed for project_id=%s", project_id)

    return {"status": "ok", "project_id": project.id}


@router.post("/projects/{project_id}/logs")
async def log_progress(
    project_id: int,
    payload: LogProgressRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    db.add(ProjectDevLog(project_id=project_id, message=payload.message))
    await db.commit()
    return {"status": "ok"}
