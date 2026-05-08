from __future__ import annotations

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    wechat_user_id: Mapped[str] = mapped_column(unique=True, index=True)
    nickname: Mapped[str | None]
    role: Mapped[str] = mapped_column(default="user")
    is_active: Mapped[bool] = mapped_column(default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    created_projects: Mapped[list[Project]] = relationship(
        "Project", foreign_keys="Project.creator_id", back_populates="creator"
    )
    approved_projects: Mapped[list[Project]] = relationship(
        "Project", foreign_keys="Project.approver_id", back_populates="approver"
    )
