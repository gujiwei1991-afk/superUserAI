"""End-to-end tests for repo↔WeChat-group binding.

Without args: only verifies pure helpers (no DB).
With BIND_GROUP_TEST_REPO_ID + BIND_GROUP_TEST_GROUP_ID: hits the real DB
to verify the full flow.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "shared"))

from sqlalchemy import select  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models import Repo, User  # noqa: E402
from app.services.project_service import ProjectService  # noqa: E402
from app.services.repo_binding_service import (  # noqa: E402
    BindingConflictError,
    RepoBindingService,
)


async def test_get_repo_by_wechat_group_id_returns_none_for_unbound() -> None:
    async with AsyncSessionLocal() as db:
        svc = ProjectService(db)
        result = await svc.get_repo_by_wechat_group_id("R:DOES_NOT_EXIST")
        assert result is None, f"expected None, got {result!r}"
    print("get_repo_by_wechat_group_id none-case ok")


async def test_bind_unbind_round_trip() -> None:
    """Bind then unbind a real repo. Skips silently if env not set."""
    repo_id_env = os.environ.get("BIND_GROUP_TEST_REPO_ID")
    group_id_env = os.environ.get("BIND_GROUP_TEST_GROUP_ID")
    if not (repo_id_env and group_id_env):
        print("set BIND_GROUP_TEST_REPO_ID + BIND_GROUP_TEST_GROUP_ID to run db round trip")
        return

    repo_id = int(repo_id_env)
    group_id = group_id_env

    async with AsyncSessionLocal() as db:
        admin = (
            await db.execute(
                select(User).where(User.role == "admin").order_by(User.id).limit(1)
            )
        ).scalar_one_or_none()
        assert admin is not None, "need an admin user in the DB"

        svc = RepoBindingService(db)
        await svc.bind(repo_id=repo_id, wechat_group_id=group_id, bound_by=admin.id)
        await db.commit()

        repo = await db.get(Repo, repo_id)
        assert repo is not None
        assert repo.wechat_group_id == group_id
        assert repo.wechat_group_bound_at is not None
        assert repo.wechat_group_bound_by == admin.id

        # Re-bind to same pair -> idempotent (no error)
        await svc.bind(repo_id=repo_id, wechat_group_id=group_id, bound_by=admin.id)
        await db.commit()

        await svc.unbind(repo_id=repo_id)
        await db.commit()
        repo = await db.get(Repo, repo_id)
        assert repo is not None
        assert repo.wechat_group_id is None
        assert repo.wechat_group_bound_at is None
        assert repo.wechat_group_bound_by is None
    print("bind/unbind round trip ok")


async def test_bind_conflict_raises() -> None:
    """Two repos cannot share a group_id."""
    repo_id_env = os.environ.get("BIND_GROUP_TEST_REPO_ID")
    repo2_id_env = os.environ.get("BIND_GROUP_TEST_REPO2_ID")
    group_id_env = os.environ.get("BIND_GROUP_TEST_GROUP_ID")
    if not (repo_id_env and repo2_id_env and group_id_env):
        print("set BIND_GROUP_TEST_REPO2_ID to run conflict test")
        return

    async with AsyncSessionLocal() as db:
        admin = (
            await db.execute(
                select(User).where(User.role == "admin").order_by(User.id).limit(1)
            )
        ).scalar_one_or_none()
        assert admin is not None
        svc = RepoBindingService(db)
        await svc.bind(
            repo_id=int(repo_id_env), wechat_group_id=group_id_env, bound_by=admin.id
        )
        await db.commit()

        try:
            await svc.bind(
                repo_id=int(repo2_id_env),
                wechat_group_id=group_id_env,
                bound_by=admin.id,
            )
        except BindingConflictError:
            print("bind conflict raises ok")
        else:
            raise AssertionError("expected BindingConflictError")
        finally:
            # cleanup: unbind the first repo
            await svc.unbind(repo_id=int(repo_id_env))
            await db.commit()


def main() -> None:
    asyncio.run(test_get_repo_by_wechat_group_id_returns_none_for_unbound())
    asyncio.run(test_bind_unbind_round_trip())
    asyncio.run(test_bind_conflict_raises())
    print("all e2e_repo_binding checks passed")


if __name__ == "__main__":
    main()
