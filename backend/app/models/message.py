from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    wechat_user_id: Mapped[str] = mapped_column(index=True)
    role: Mapped[str]
    content: Mapped[str] = mapped_column(Text)
    msg_type: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    project: Mapped[Project] = relationship("Project", back_populates="messages")
