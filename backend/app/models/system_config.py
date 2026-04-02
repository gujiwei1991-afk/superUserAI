from __future__ import annotations
from datetime import datetime
from sqlalchemy import Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class SystemConfig(Base):
    __tablename__ = "system_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(unique=True, index=True)  # 配置键，如 "vwork_api_host"
    value: Mapped[str] = mapped_column(Text)                    # 配置值
    description: Mapped[str | None] = mapped_column(Text)       # 说明
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )
