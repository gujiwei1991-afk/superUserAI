from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class DevTask(Base):
    __tablename__ = "dev_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )
    repo_id: Mapped[int] = mapped_column(
        ForeignKey("repos.id", ondelete="CASCADE"),
        index=True,
    )
    branch: Mapped[str | None]
    pr_number: Mapped[int | None]
    status: Mapped[str] = mapped_column(default="pending")
    worker_id: Mapped[str | None]
    summary: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime | None]
    staging_deploy_status: Mapped[str] = mapped_column(default="pending")
    staging_deployed_at: Mapped[datetime | None]
    staging_deploy_log: Mapped[str | None] = mapped_column(Text)
    prod_deploy_status: Mapped[str] = mapped_column(default="pending")
    prod_deployed_at: Mapped[datetime | None]
    prod_deploy_log: Mapped[str | None] = mapped_column(Text)
    prod_deployed_sha: Mapped[str | None]

    project: Mapped["Project"] = relationship("Project", back_populates="dev_tasks")
    repo: Mapped["Repo"] = relationship("Repo", back_populates="dev_tasks")
