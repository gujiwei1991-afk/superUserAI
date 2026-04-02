from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.system_config import SystemConfig
from app.config import get_settings


class ConfigService:
    """统一配置读取。优先级：DB > .env > 默认值"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, key: str, default: str = "") -> str:
        """获取配置值。先查数据库，没有则查 .env（Settings），最后用默认值。"""
        # 1. 查数据库
        stmt = select(SystemConfig.value).where(SystemConfig.key == key)
        result = await self.db.execute(stmt)
        db_value = result.scalar_one_or_none()
        if db_value is not None and db_value.strip():
            return db_value

        # 2. 查 .env (Settings)
        settings = get_settings()
        env_value = getattr(settings, key, None)
        if env_value is not None and str(env_value).strip():
            return str(env_value)

        # 3. 默认值
        return default

    async def get_int(self, key: str, default: int = 0) -> int:
        value = await self.get(key, str(default))
        try:
            return int(value)
        except ValueError:
            return default

    async def set(self, key: str, value: str, description: str | None = None):
        """设置配置值（upsert）"""
        stmt = select(SystemConfig).where(SystemConfig.key == key)
        result = await self.db.execute(stmt)
        config = result.scalar_one_or_none()
        if config is None:
            config = SystemConfig(key=key, value=value, description=description)
            self.db.add(config)
        else:
            config.value = value
            if description is not None:
                config.description = description
        await self.db.flush()

    async def get_all(self) -> dict[str, str]:
        """获取所有数据库中的配置"""
        stmt = select(SystemConfig).order_by(SystemConfig.key)
        result = await self.db.execute(stmt)
        return {c.key: c.value for c in result.scalars().all()}

    async def get_all_with_meta(self) -> list[SystemConfig]:
        """获取所有配置（含 description 和 updated_at）"""
        stmt = select(SystemConfig).order_by(SystemConfig.key)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def delete(self, key: str):
        """删除配置项"""
        stmt = select(SystemConfig).where(SystemConfig.key == key)
        result = await self.db.execute(stmt)
        config = result.scalar_one_or_none()
        if config:
            await self.db.delete(config)
            await self.db.flush()
