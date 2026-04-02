from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Project, Repo
from shared.constants import ProjectStatus

router = APIRouter(prefix="/api")


class CompleteTaskRequest(BaseModel):
    pr_number: int = Field(gt=0)


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
    await db.commit()
    await db.refresh(project)

    return {
        "status": "ok",
        "project_id": project.id,
        "github_pr_number": project.github_pr_number,
    }
