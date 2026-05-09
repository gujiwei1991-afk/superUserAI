from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.gateway.wechat_client import WeChatClient
from app.models import DevTask, Project, ProjectDevLog, Repo
from app.services.project_review import notify_creator_dev_failed
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


class ClaimRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=200)


_STALE_AFTER_MINUTES = 60
_ACTIVE_STATUSES = ("claimed", "in_progress", "pr_open", "merged", "deployed")


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


@router.post("/tasks/claim")
async def claim_task(
    payload: ClaimRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    # 1. Stale recovery: any claimed/in_progress dev_task older than 60 minutes
    #    is assumed dead and gets marked failed so its project becomes claimable.
    cutoff = datetime.utcnow() - timedelta(minutes=_STALE_AFTER_MINUTES)
    await db.execute(
        update(DevTask)
        .where(
            DevTask.status.in_(("claimed", "in_progress")),
            DevTask.started_at < cutoff,
        )
        .values(
            status="failed",
            finished_at=datetime.utcnow(),
        )
    )

    # 2. Find one approved project with no active dev_task.
    blocking_subquery = (
        select(DevTask.project_id)
        .where(DevTask.status.in_(_ACTIVE_STATUSES))
    )
    stmt = (
        select(Project, Repo)
        .join(Repo, Project.repo_id == Repo.id)
        .where(
            Project.status == ProjectStatus.APPROVED.value,
            Project.github_issue_number.is_not(None),
            ~Project.id.in_(blocking_subquery),
        )
        .order_by(Project.created_at.asc())
        .limit(1)
    )
    row = (await db.execute(stmt)).first()
    if row is None:
        await db.commit()
        return {"claimed": False}

    project, repo = row

    # 3. Insert claim. Partial unique index will reject duplicates if another
    #    worker beat us; treat as race-lost.
    new_task = DevTask(
        project_id=project.id,
        repo_id=project.repo_id,
        worker_id=payload.worker_id,
        status="claimed",
        started_at=datetime.utcnow(),
    )
    db.add(new_task)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        logger.info(
            "claim race lost project_id=%s worker=%s — backing off to next tick",
            project.id, payload.worker_id,
        )
        return {"claimed": False}

    await db.commit()
    logger.info(
        "claim success project_id=%s dev_task_id=%s worker=%s",
        project.id, new_task.id, payload.worker_id,
    )
    return {
        "claimed": True,
        "dev_task_id": new_task.id,
        "project_id": project.id,
        "github_owner": repo.github_owner,
        "github_repo": repo.github_repo,
        "github_issue_number": project.github_issue_number,
        "title": project.title,
    }


@router.post("/dev-tasks/{dev_task_id}/started")
async def mark_dev_task_started(
    dev_task_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    task = await db.get(DevTask, dev_task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="dev task not found")
    if task.status == "claimed":
        task.status = "in_progress"
        await db.commit()
    else:
        # idempotent: maybe already moved on by stale recovery or by a retry
        logger.info(
            "mark_started no-op dev_task_id=%s current_status=%s",
            dev_task_id, task.status,
        )
    return {"dev_task_id": dev_task_id, "status": task.status}


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

    # Find the active dev_task and update it instead of inserting a new row.
    stmt = (
        select(DevTask)
        .where(
            DevTask.project_id == project_id,
            DevTask.status.in_(("claimed", "in_progress")),
        )
        .order_by(DevTask.id.desc())
        .limit(1)
    )
    active = (await db.execute(stmt)).scalar_one_or_none()
    if active is not None:
        active.status = "pr_open"
        active.pr_number = payload.pr_number
        active.branch = payload.branch
        active.summary = payload.summary
        active.finished_at = datetime.utcnow()
    else:
        logger.warning(
            "complete_task: no active dev_task for project=%s; "
            "inserting fallback row to preserve audit trail",
            project_id,
        )
        db.add(
            DevTask(
                project_id=project.id,
                repo_id=project.repo_id,
                branch=payload.branch,
                pr_number=payload.pr_number,
                status="pr_open",
                summary=payload.summary,
                finished_at=datetime.utcnow(),
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

    stmt = (
        select(DevTask)
        .where(
            DevTask.project_id == project_id,
            DevTask.status.in_(("claimed", "in_progress")),
        )
        .order_by(DevTask.id.desc())
        .limit(1)
    )
    active = (await db.execute(stmt)).scalar_one_or_none()
    if active is not None:
        active.status = "failed"
        active.summary = payload.reason[:4000]
        active.finished_at = datetime.utcnow()
    else:
        logger.warning(
            "fail_task: no active dev_task for project=%s; inserting fallback row",
            project_id,
        )
        db.add(
            DevTask(
                project_id=project.id,
                repo_id=project.repo_id,
                branch=None,
                pr_number=None,
                status="failed",
                summary=payload.reason[:4000],
                finished_at=datetime.utcnow(),
            )
        )

    await db.commit()
    await db.refresh(project)

    await notify_creator_dev_failed(db, wechat, project, payload.reason)

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
