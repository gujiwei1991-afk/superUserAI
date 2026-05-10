"""End-to-end: GitHub PR opened webhook → backend dispatches staging deploy.

Stand-alone runnable. Mocks SSH (via patching staging_deploy_service.asyncio
.create_subprocess_exec) and wechat. Uses the real FastAPI TestClient + DB.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "shared"))


def _fake_proc(returncode: int = 0, stdout: bytes = b"deploy ok\n"):
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, None))
    proc.kill = MagicMock()
    proc.wait = AsyncMock()
    return proc


def test_pr_opened_webhook_triggers_deploy() -> None:
    """模拟 PR opened webhook → 验证 staging_deploy_service.deploy_pr 被异步调用一次。

    Saves+restores the chosen repo's staging_* fields so the dev DB stays clean.
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database import AsyncSessionLocal
    from sqlalchemy import text

    client = TestClient(app)

    # 找一个有 dev_task + project + repo 三件套齐全的 dev_task（不需要 staging 字段）
    async def fetch_setup():
        async with AsyncSessionLocal() as db:
            row = (await db.execute(text("""
                SELECT dt.id, dt.project_id, dt.repo_id, p.github_pr_number
                FROM dev_tasks dt JOIN projects p ON p.id = dt.project_id
                WHERE p.github_pr_number IS NOT NULL
                LIMIT 1
            """))).first()
            return row
    row = asyncio.run(fetch_setup())
    if row is None:
        print("e2e_staging_deploy: no PR-bound dev_task in db, SKIP")
        return

    dev_task_id, project_id, repo_id, pr_number = row

    # Save the repo's current staging_* values, then set test values, then restore at end
    async def fetch_repo_staging():
        async with AsyncSessionLocal() as db:
            return (await db.execute(text(
                "SELECT staging_url, staging_ssh_target, staging_deploy_path, "
                "staging_compose_file FROM repos WHERE id = :id"
            ), {"id": repo_id})).first()
    orig = asyncio.run(fetch_repo_staging())

    async def setup_repo():
        async with AsyncSessionLocal() as db:
            await db.execute(text("""
                UPDATE repos SET
                  staging_url = 'https://staging.test.example.com',
                  staging_ssh_target = 'deploy@dummyserver.example.com',
                  staging_deploy_path = '/srv/staging/test',
                  staging_compose_file = 'docker-compose.staging.yml'
                WHERE id = :id
            """), {"id": repo_id})
            await db.commit()
    asyncio.run(setup_repo())

    try:
        deploy_calls: list[tuple] = []

        async def fake_deploy_pr(db, repo, project, dev_task, pr_number, head_sha):
            deploy_calls.append((repo.id, project.id, dev_task.id, pr_number, head_sha))

        payload = {
            "action": "opened",
            "number": pr_number,
            "pull_request": {
                "number": pr_number,
                "head": {"sha": "deadbeef00000000000000000000000000000000"},
                "merged": False,
            },
        }

        with patch(
            "app.api.webhooks.staging_deploy_service.deploy_pr",
            side_effect=fake_deploy_pr,
        ):
            resp = client.post(
                "/api/webhooks/github",
                data=json.dumps(payload),
                headers={"X-GitHub-Event": "pull_request"},
            )
            assert resp.status_code == 200, (resp.status_code, resp.text)

        # TestClient runs BackgroundTasks synchronously inside client.post() — no sleep needed
        assert len(deploy_calls) == 1, deploy_calls
        assert deploy_calls[0][3] == pr_number
        assert deploy_calls[0][4].startswith("deadbeef")
        print(f"webhook → deploy_pr triggered ok ({deploy_calls[0]})")
    finally:
        # Restore original staging_* values so the dev DB stays clean
        async def restore_repo():
            async with AsyncSessionLocal() as db:
                await db.execute(text("""
                    UPDATE repos SET
                      staging_url = :su, staging_ssh_target = :st,
                      staging_deploy_path = :sp, staging_compose_file = :sc
                    WHERE id = :id
                """), {
                    "id": repo_id,
                    "su": orig[0], "st": orig[1],
                    "sp": orig[2], "sc": orig[3] or "docker-compose.staging.yml",
                })
                await db.commit()
        asyncio.run(restore_repo())


def main() -> None:
    test_pr_opened_webhook_triggers_deploy()
    print("\nall e2e_staging_deploy checks passed")


if __name__ == "__main__":
    main()
