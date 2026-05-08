from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"))
    title: Mapped[str]
    status: Mapped[str] = mapped_column(default="drafting")
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    approver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    github_issue_number: Mapped[int | None]
    github_pr_number: Mapped[int | None]
    prd_content: Mapped[str | None] = mapped_column(Text)
    tech_doc: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float | None]
    feedback: Mapped[str | None] = mapped_column(Text)
    wechat_group_id: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
    )

    repo: Mapped[Repo] = relationship("Repo", back_populates="projects")
    creator: Mapped[User] = relationship(
        "User", foreign_keys=[creator_id], back_populates="created_projects"
    )
    approver: Mapped[User | None] = relationship(
        "User", foreign_keys=[approver_id], back_populates="approved_projects"
    )
    messages: Mapped[list[Message]] = relationship("Message", back_populates="project")
    dev_tasks: Mapped[list["DevTask"]] = relationship(
        "DevTask",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="DevTask.started_at.desc()",
    )
    dev_logs: Mapped[list["ProjectDevLog"]] = relationship(
        "ProjectDevLog",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectDevLog.created_at",
    )
