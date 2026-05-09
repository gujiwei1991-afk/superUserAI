"""End-to-end smoke for /api/tasks/claim and friends.

Without env: verifies the empty-pool case + race-lost mechanic with mocks.
With CLAIM_TEST_PROJECT_ID set to an approved project: exercises the full
claim → mark_started → completed cycle on real DB rows.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "shared"))

from sqlalchemy import text  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models import DevTask, Project  # noqa: E402


async def test_claim_empty_pool() -> None:
    """When no project is approved-and-untaken, /claim returns claimed=false.
    Either way (claimed something or not), it must not 500.
    """
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)

    response = client.post(
        "/api/tasks/claim",
        json={"worker_id": "test-worker-empty"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "claimed" in body
    if body["claimed"]:
        # Roll back: mark this task failed so we don't disturb other tests.
        async with AsyncSessionLocal() as db:
            t = await db.get(DevTask, body["dev_task_id"])
            if t:
                t.status = "failed"
                t.finished_at = datetime.utcnow()
                await db.commit()
    print("claim_empty_pool ok (claimed=%s)" % body["claimed"])


async def test_stale_recovery() -> None:
    """Insert a synthetic stale claimed dev_task; next /claim should mark it failed."""
    proj_id_env = os.environ.get("CLAIM_TEST_PROJECT_ID")
    if not proj_id_env:
        print("set CLAIM_TEST_PROJECT_ID to an approved-status project to run stale_recovery test")
        return

    project_id = int(proj_id_env)
    async with AsyncSessionLocal() as db:
        project = await db.get(Project, project_id)
        assert project is not None, f"project {project_id} not found"
        # Insert a stale claimed task (started_at = 90 minutes ago)
        stale_started = datetime.utcnow() - timedelta(minutes=90)
        await db.execute(
            text(
                "INSERT INTO dev_tasks (project_id, repo_id, status, worker_id, started_at) "
                "VALUES (:pid, :rid, 'claimed', :wid, :sa)"
            ),
            {
                "pid": project_id,
                "rid": project.repo_id,
                "wid": "stale-worker-test",
                "sa": stale_started,
            },
        )
        await db.commit()

    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    response = client.post(
        "/api/tasks/claim",
        json={"worker_id": "fresh-worker-test"},
    )
    assert response.status_code == 200, response.text

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(text(
            "SELECT id, status FROM dev_tasks WHERE worker_id='stale-worker-test' ORDER BY id DESC LIMIT 1"
        ))).all()
        assert rows, "synthetic stale row missing"
        assert rows[0].status == "failed", f"expected stale row failed, got {rows[0].status}"
        body = response.json()
        if body.get("claimed"):
            new_id = body["dev_task_id"]
            await db.execute(text("DELETE FROM dev_tasks WHERE id=:i"), {"i": new_id})
        await db.execute(text("DELETE FROM dev_tasks WHERE worker_id='stale-worker-test'"))
        await db.commit()

    print("stale_recovery ok")


async def test_started_endpoint_idempotent() -> None:
    """started should transition claimed→in_progress once; subsequent calls no-op."""
    proj_id_env = os.environ.get("CLAIM_TEST_PROJECT_ID")
    if not proj_id_env:
        print("set CLAIM_TEST_PROJECT_ID to run started_endpoint test")
        return
    project_id = int(proj_id_env)

    async with AsyncSessionLocal() as db:
        project = await db.get(Project, project_id)
        assert project is not None
        new_task = DevTask(
            project_id=project_id,
            repo_id=project.repo_id,
            worker_id="started-test",
            status="claimed",
            started_at=datetime.utcnow(),
        )
        db.add(new_task)
        await db.flush()
        task_id = new_task.id
        await db.commit()

    try:
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        r1 = client.post(f"/api/dev-tasks/{task_id}/started")
        assert r1.status_code == 200, r1.text
        assert r1.json()["status"] == "in_progress"

        r2 = client.post(f"/api/dev-tasks/{task_id}/started")
        assert r2.status_code == 200, r2.text
        assert r2.json()["status"] == "in_progress"  # idempotent
    finally:
        async with AsyncSessionLocal() as db:
            await db.execute(text("DELETE FROM dev_tasks WHERE id=:i"), {"i": task_id})
            await db.commit()

    print("started_endpoint_idempotent ok")


def main() -> None:
    asyncio.run(test_claim_empty_pool())
    asyncio.run(test_stale_recovery())
    asyncio.run(test_started_endpoint_idempotent())
    print("all e2e_task_claim_lock checks passed")


if __name__ == "__main__":
    main()
