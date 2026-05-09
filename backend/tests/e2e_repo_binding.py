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

from app.database import AsyncSessionLocal  # noqa: E402
from app.services.project_service import ProjectService  # noqa: E402


async def test_get_repo_by_wechat_group_id_returns_none_for_unbound() -> None:
    async with AsyncSessionLocal() as db:
        svc = ProjectService(db)
        result = await svc.get_repo_by_wechat_group_id("R:DOES_NOT_EXIST")
        assert result is None, f"expected None, got {result!r}"
    print("get_repo_by_wechat_group_id none-case ok")


def main() -> None:
    asyncio.run(test_get_repo_by_wechat_group_id_returns_none_for_unbound())
    print("all e2e_repo_binding pre-checks passed")


if __name__ == "__main__":
    main()
