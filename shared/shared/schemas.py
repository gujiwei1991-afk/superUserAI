from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from shared.constants import ProjectStatus


class VWorkMessage(BaseModel):
    type: int
    msg_type: int
    msg_id: str
    user_id: str
    waiter_id: str = ""
    at_list: list[str] = Field(default_factory=list)
    content: str | dict[str, Any]
    sender: str = ""
    time_stamp: int
    is_self_msg: int
    is_pc_msg: int = 0
    self_user_id: str
    port: int


class ProjectCreate(BaseModel):
    repo_id: int
    title: str
    description: str


class ProjectResponse(BaseModel):
    id: int
    repo_id: int
    title: str
    status: ProjectStatus
    creator_id: str
    github_issue_number: int | None = None
    github_pr_number: int | None = None
    score: int | None = None
    created_at: datetime
    updated_at: datetime


class ChatMessage(BaseModel):
    role: str
    content: str


class ScoreInput(BaseModel):
    score: int = Field(ge=1, le=10)
    comment: str = Field(max_length=2000)
