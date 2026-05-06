"""Bootstrap script to initialize the SuperUserAI database.

Idempotent — safe to re-run. Steps:
  1. Create the `superuserai` database if it does not exist.
  2. Run alembic migrations to head.
  3. Ensure an admin user (wechat_user_id=1688855517625488) exists.
  4. Insert a placeholder repo row if the repos table is empty.

Usage (from the backend/ directory):
    python bootstrap.py
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models import Repo, User

ADMIN_WECHAT_USER_ID = "1688855517625488"
ADMIN_NICKNAME = "Admin"

PLACEHOLDER_REPO = {
    "name": "demo",
    "github_owner": "REPLACE_ME_OWNER",
    "github_repo": "REPLACE_ME_REPO",
    "github_token_encrypted": "",
    "deploy_server": None,
    "deploy_config": None,
}

BACKEND_DIR = Path(__file__).resolve().parent
logger = logging.getLogger("bootstrap")


async def ensure_database_exists(database_url: str) -> None:
    cleaned = database_url.replace("+asyncpg", "")
    parsed = urlparse(cleaned)
    dbname = (parsed.path or "/").lstrip("/")
    if not dbname:
        raise ValueError(f"database_url has no database name: {database_url}")

    conn = await asyncpg.connect(
        host=parsed.hostname or "localhost",
        port=parsed.port or 5432,
        user=parsed.username,
        password=parsed.password or None,
        database="postgres",
    )
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", dbname
        )
        if exists:
            logger.info("Database %s already exists.", dbname)
            return
        await conn.execute(f'CREATE DATABASE "{dbname}"')
        logger.info("Database %s created.", dbname)
    finally:
        await conn.close()


def run_alembic_upgrade() -> None:
    logger.info("Running alembic upgrade head...")
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        cwd=str(BACKEND_DIR),
    )
    if result.stdout.strip():
        logger.info(result.stdout.strip())
    if result.returncode != 0:
        logger.error("alembic stderr: %s", result.stderr)
        raise RuntimeError("alembic upgrade failed")
    logger.info("alembic upgrade head OK.")


async def seed_admin_and_repo(database_url: str) -> None:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with SessionLocal() as db:
            existing_admin = (
                await db.execute(
                    select(User).where(User.wechat_user_id == ADMIN_WECHAT_USER_ID)
                )
            ).scalar_one_or_none()

            if existing_admin is None:
                db.add(
                    User(
                        wechat_user_id=ADMIN_WECHAT_USER_ID,
                        nickname=ADMIN_NICKNAME,
                        role="admin",
                    )
                )
                logger.info(
                    "Created admin user wechat_user_id=%s", ADMIN_WECHAT_USER_ID
                )
            elif existing_admin.role != "admin":
                existing_admin.role = "admin"
                logger.info(
                    "Promoted existing user %s to admin", ADMIN_WECHAT_USER_ID
                )
            else:
                logger.info("Admin user already present.")

            any_repo = (await db.execute(select(Repo))).scalars().first()
            if any_repo is None:
                db.add(Repo(**PLACEHOLDER_REPO))
                logger.info(
                    "Inserted placeholder repo (update github_owner/github_repo via admin panel)."
                )
            else:
                logger.info("Repos table is not empty; skipped placeholder.")

            await db.commit()
    finally:
        await engine.dispose()


async def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    settings = get_settings()
    await ensure_database_exists(settings.database_url)
    run_alembic_upgrade()
    await seed_admin_and_repo(settings.database_url)
    logger.info("Bootstrap complete.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
