from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    active_project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"))
    state: Mapped[str] = mapped_column(default="idle")
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped[User] = relationship("User")
    active_project: Mapped[Project | None] = relationship("Project")
