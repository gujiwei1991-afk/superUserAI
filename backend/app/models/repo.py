from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Repo(Base):
    __tablename__ = "repos"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    github_owner: Mapped[str]
    github_repo: Mapped[str]
    github_token_encrypted: Mapped[str] = mapped_column(default="")
    description: Mapped[str | None] = mapped_column(Text)
    local_path: Mapped[str | None] = mapped_column(Text)
    deploy_server: Mapped[str | None]
    deploy_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    projects: Mapped[list[Project]] = relationship("Project", back_populates="repo")
    dev_tasks: Mapped[list["DevTask"]] = relationship(
        "DevTask",
        back_populates="repo",
        cascade="all, delete-orphan",
    )

    @property
    def github_full_name(self) -> str:
        return f"{self.github_owner}/{self.github_repo}"

    @property
    def has_custom_github_token(self) -> bool:
        return bool(self.github_token_encrypted.strip())
