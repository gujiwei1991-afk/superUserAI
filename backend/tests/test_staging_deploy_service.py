"""Unit tests for StagingDeployService (mocked SSH + wechat).

Stand-alone runnable: `python tests/test_staging_deploy_service.py`.
Prints `all test_staging_deploy_service checks passed` on success.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "shared"))

from app.services.staging_deploy_service import _parse_ssh_target  # noqa: E402


def test_parse_target_user_at_host() -> None:
    user, host, port = _parse_ssh_target("deploy@server.com", default_user="fallback")
    assert (user, host, port) == ("deploy", "server.com", None), (user, host, port)
    print("parse user@host ok")


def test_parse_target_user_at_host_with_port() -> None:
    user, host, port = _parse_ssh_target("deploy@server.com:2222", default_user="fallback")
    assert (user, host, port) == ("deploy", "server.com", 2222), (user, host, port)
    print("parse user@host:port ok")


def test_parse_target_only_host_uses_default_user() -> None:
    user, host, port = _parse_ssh_target("server.com", default_user="deploy")
    assert (user, host, port) == ("deploy", "server.com", None), (user, host, port)
    print("parse host-only uses default_user ok")


def test_parse_target_only_host_with_port() -> None:
    user, host, port = _parse_ssh_target("server.com:2222", default_user="deploy")
    assert (user, host, port) == ("deploy", "server.com", 2222), (user, host, port)
    print("parse host:port uses default_user ok")


def test_parse_target_invalid_port_raises() -> None:
    try:
        _parse_ssh_target("deploy@server.com:abc", default_user="x")
    except ValueError:
        print("parse invalid port raises ValueError ok")
        return
    raise AssertionError("expected ValueError")


def test_parse_target_empty_raises() -> None:
    try:
        _parse_ssh_target("", default_user="x")
    except ValueError:
        print("parse empty raises ValueError ok")
        return
    raise AssertionError("expected ValueError")


import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _make_service():
    from app.services.staging_deploy_service import StagingDeployService
    return StagingDeployService(
        wechat_client=AsyncMock(),
        ssh_key_path="/tmp/fake_key",
        ssh_user_default="deploy",
        deploy_timeout_sec=10,
        log_tail_lines=200,
    )


def _make_repo(**overrides):
    repo = MagicMock()
    repo.id = 1
    repo.github_owner = "owner"
    repo.github_repo = "repo"
    repo.staging_url = "https://staging.example.com"
    repo.staging_ssh_target = "deploy@server.com"
    repo.staging_deploy_path = "/srv/staging/repo"
    repo.staging_compose_file = "docker-compose.staging.yml"
    for k, v in overrides.items():
        setattr(repo, k, v)
    return repo


def _make_dev_task():
    dt = MagicMock()
    dt.id = 42
    dt.staging_deploy_status = "pending"
    dt.staging_deployed_at = None
    dt.staging_deploy_log = None
    return dt


def _make_project():
    p = MagicMock()
    p.id = 7
    p.title = "Test Project"
    p.status = "developing"
    return p


def _make_db():
    db = MagicMock()
    db.commit = AsyncMock()
    return db


def test_deploy_pr_skips_when_staging_url_missing() -> None:
    async def run():
        svc = _make_service()
        repo = _make_repo(staging_url=None)
        dev_task = _make_dev_task()
        project = _make_project()
        db = _make_db()
        await svc.deploy_pr(db, repo, project, dev_task, pr_number=3, head_sha="abc123")
        assert dev_task.staging_deploy_status == "skipped", dev_task.staging_deploy_status
        # 没发企微通知
        svc.wechat_client.send_text.assert_not_called()
        svc.wechat_client.send_card_link.assert_not_called()
    asyncio.run(run())
    print("deploy_pr skips when staging_url missing ok")


def test_deploy_pr_skips_when_ssh_target_missing() -> None:
    async def run():
        svc = _make_service()
        repo = _make_repo(staging_ssh_target=None)
        dev_task = _make_dev_task()
        project = _make_project()
        db = _make_db()
        await svc.deploy_pr(db, repo, project, dev_task, pr_number=3, head_sha="abc")
        assert dev_task.staging_deploy_status == "skipped"
    asyncio.run(run())
    print("deploy_pr skips when ssh_target missing ok")


def _fake_subprocess(returncode: int, stdout: bytes = b"ok\n"):
    """Returns an awaitable that resolves to a fake process behaving like asyncio's."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, None))
    proc.kill = MagicMock()
    proc.wait = AsyncMock()
    return proc


def test_deploy_pr_success_updates_state_and_notifies() -> None:
    async def run():
        svc = _make_service()
        repo = _make_repo()
        dev_task = _make_dev_task()
        project = _make_project()
        db = _make_db()

        fake_proc = _fake_subprocess(returncode=0, stdout=b"deploy succeeded\nUp 0 sec\n")

        with patch("app.services.staging_deploy_service.asyncio.create_subprocess_exec",
                   AsyncMock(return_value=fake_proc)) as mock_exec, \
             patch("app.services.staging_deploy_service.notify_creator_targeted",
                   AsyncMock()) as mock_notify:
            await svc.deploy_pr(db, repo, project, dev_task, pr_number=3, head_sha="abcdef")

        assert dev_task.staging_deploy_status == "success", dev_task.staging_deploy_status
        assert dev_task.staging_deployed_at is not None
        assert "deploy succeeded" in (dev_task.staging_deploy_log or "")
        assert project.status == "staged", project.status
        # 通知调了一次
        assert mock_notify.await_count == 1
        # 通知 body 含 staging_url + PR 号
        body = mock_notify.await_args.args[3]  # (db, wechat, project, body)
        assert "https://staging.example.com" in body
        assert "PR #3" in body
        # SSH 命令至少调过
        assert mock_exec.await_count == 1
        ssh_args = mock_exec.await_args.args
        assert "ssh" in ssh_args
        assert "deploy@server.com" in ssh_args
    asyncio.run(run())
    print("deploy_pr success path ok")


def test_deploy_pr_nonzero_exit_marks_failed_and_notifies() -> None:
    async def run():
        svc = _make_service()
        repo = _make_repo()
        dev_task = _make_dev_task()
        project = _make_project()
        db = _make_db()

        fake_proc = _fake_subprocess(
            returncode=1,
            stdout=b"docker compose error\nbuild failed\n",
        )

        with patch("app.services.staging_deploy_service.asyncio.create_subprocess_exec",
                   AsyncMock(return_value=fake_proc)), \
             patch("app.services.staging_deploy_service.notify_creator_targeted",
                   AsyncMock()) as mock_notify:
            await svc.deploy_pr(db, repo, project, dev_task, pr_number=4, head_sha="def")

        assert dev_task.staging_deploy_status == "failed"
        assert "build failed" in (dev_task.staging_deploy_log or "")
        assert mock_notify.await_count == 1
        body = mock_notify.await_args.args[3]
        assert "PR #4" in body
        assert "失败" in body
    asyncio.run(run())
    print("deploy_pr nonzero exit path ok")


def test_deploy_pr_timeout_kills_and_marks_failed() -> None:
    async def run():
        svc = _make_service()
        # timeout 设很短便于触发
        svc.deploy_timeout_sec = 0.1
        repo = _make_repo()
        dev_task = _make_dev_task()
        project = _make_project()
        db = _make_db()

        proc = MagicMock()
        proc.returncode = None

        async def hang(*a, **kw):
            await asyncio.sleep(5)  # 永远等不到
            return (b"", None)

        proc.communicate = hang
        proc.kill = MagicMock()
        proc.wait = AsyncMock()

        with patch("app.services.staging_deploy_service.asyncio.create_subprocess_exec",
                   AsyncMock(return_value=proc)), \
             patch("app.services.staging_deploy_service.notify_creator_targeted",
                   AsyncMock()) as mock_notify:
            await svc.deploy_pr(db, repo, project, dev_task, pr_number=5, head_sha="ghi")

        assert dev_task.staging_deploy_status == "failed"
        assert "timeout" in (dev_task.staging_deploy_log or "").lower()
        proc.kill.assert_called_once()
        assert mock_notify.await_count == 1
    asyncio.run(run())
    print("deploy_pr timeout path ok")


def test_deploy_pr_bad_ssh_target_marks_failed() -> None:
    async def run():
        svc = _make_service()
        repo = _make_repo(staging_ssh_target="deploy@server.com:not-a-port")
        dev_task = _make_dev_task()
        project = _make_project()
        db = _make_db()

        with patch("app.services.staging_deploy_service.notify_creator_targeted",
                   AsyncMock()) as mock_notify:
            await svc.deploy_pr(db, repo, project, dev_task, pr_number=6, head_sha="jkl")

        assert dev_task.staging_deploy_status == "failed"
        assert "ssh target parse error" in (dev_task.staging_deploy_log or "")
        # 失败也通知
        assert mock_notify.await_count == 1
    asyncio.run(run())
    print("deploy_pr bad ssh target ok")


def test_deploy_pr_same_repo_concurrent_serializes_and_coalesces() -> None:
    """同 repo 并发 N 次 deploy_pr，SSH 实际只调 2 次（首次 + 合并最新 sha）。"""
    async def run():
        svc = _make_service()
        repo = _make_repo()
        project = _make_project()
        db = _make_db()

        # 给两个不同的 dev_task（模拟两次 PR push）
        dt_a = _make_dev_task(); dt_a.id = 100
        dt_b = _make_dev_task(); dt_b.id = 101

        # SSH 调用计数 + 慢一点让并发能错开
        call_log: list[tuple[int, str]] = []

        async def fake_communicate(input_bytes):
            await asyncio.sleep(0.05)
            return (b"ok\n", None)

        def fake_create(*args, **kwargs):
            call_log.append(("called", str(len(call_log))))
            proc = MagicMock()
            proc.returncode = 0
            proc.communicate = fake_communicate
            proc.kill = MagicMock()
            proc.wait = AsyncMock()
            return proc

        async def fake_create_async(*args, **kwargs):
            return fake_create(*args, **kwargs)

        with patch("app.services.staging_deploy_service.asyncio.create_subprocess_exec",
                   side_effect=fake_create_async), \
             patch("app.services.staging_deploy_service.notify_creator_targeted",
                   AsyncMock()):
            # 三个 push 同一 repo 几乎同时来
            await asyncio.gather(
                svc.deploy_pr(db, repo, project, dt_a, pr_number=3, head_sha="sha-a"),
                svc.deploy_pr(db, repo, project, dt_b, pr_number=3, head_sha="sha-b"),
                svc.deploy_pr(db, repo, project, dt_b, pr_number=3, head_sha="sha-c"),
            )

        # 期望：第一次部 sha-a；后两次合并成一次部 sha-c。所以总共 2 次 SSH
        assert len(call_log) == 2, f"expected 2 ssh calls, got {len(call_log)}"
        # Coalesced replay should update dt_b (not dt_a, which is for the first deploy)
        assert dt_a.staging_deploy_status == "success", \
            f"dt_a should reflect first deploy: {dt_a.staging_deploy_status}"
        assert dt_b.staging_deploy_status == "success", \
            f"dt_b should reflect coalesced (latest) replay: {dt_b.staging_deploy_status}"
    asyncio.run(run())
    print("deploy_pr same-repo serialize + coalesce ok")


def test_deploy_pr_different_repos_parallel() -> None:
    """不同 repo 的并发不阻塞。"""
    async def run():
        svc = _make_service()
        project = _make_project()
        db = _make_db()
        repo1 = _make_repo(); repo1.id = 1
        repo2 = _make_repo(); repo2.id = 2
        dt1 = _make_dev_task(); dt1.id = 1
        dt2 = _make_dev_task(); dt2.id = 2

        started = []

        async def fake_communicate(_):
            started.append("started")
            await asyncio.sleep(0.1)
            return (b"ok\n", None)

        def fake_create(*args, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            proc.communicate = fake_communicate
            return proc

        async def fake_create_async(*args, **kwargs):
            return fake_create(*args, **kwargs)

        with patch("app.services.staging_deploy_service.asyncio.create_subprocess_exec",
                   side_effect=fake_create_async), \
             patch("app.services.staging_deploy_service.notify_creator_targeted",
                   AsyncMock()):
            t0 = asyncio.get_event_loop().time()
            await asyncio.gather(
                svc.deploy_pr(db, repo1, project, dt1, pr_number=1, head_sha="x"),
                svc.deploy_pr(db, repo2, project, dt2, pr_number=2, head_sha="y"),
            )
            elapsed = asyncio.get_event_loop().time() - t0

        # 应该差不多 0.1s（并行），不是 0.2s（串行）
        assert elapsed < 0.18, f"different repos should run in parallel, took {elapsed}"
        assert len(started) == 2
    asyncio.run(run())
    print("deploy_pr different-repos parallel ok")


def test_recover_stale_deploys_marks_failed() -> None:
    """模拟 backend 重启：dev_task 卡在 deploying 但开始时间超过 15min → 强改 failed.

    Saves+restores the chosen dev_task's state so the dev DB stays clean.
    """
    async def run():
        from app.services.staging_deploy_service import StagingDeployService
        from app.database import AsyncSessionLocal
        from sqlalchemy import text

        async with AsyncSessionLocal() as db:
            row = (await db.execute(text(
                "SELECT id, staging_deploy_status, staging_deploy_log, started_at "
                "FROM dev_tasks LIMIT 1"
            ))).first()
            if row is None:
                print("recover_stale_deploys: no dev_task in db, SKIP")
                return
            dev_task_id, orig_status, orig_log, orig_started_at = row
            # 设置成 deploying + 18 分钟前开始
            await db.execute(text("""
                UPDATE dev_tasks
                SET staging_deploy_status='deploying',
                    started_at = NOW() - INTERVAL '18 minutes',
                    staging_deployed_at = NULL
                WHERE id = :id
            """), {"id": dev_task_id})
            await db.commit()

        try:
            svc = _make_service()
            await svc.recover_stale_deploys(stale_after_sec=900)

            async with AsyncSessionLocal() as db:
                row = (await db.execute(text(
                    "SELECT staging_deploy_status, staging_deploy_log FROM dev_tasks WHERE id=:id"
                ), {"id": dev_task_id})).first()
                assert row[0] == "failed", row[0]
                assert "restart" in (row[1] or "").lower()
        finally:
            # Restore original row state so we don't pollute the dev DB
            async with AsyncSessionLocal() as db:
                await db.execute(text("""
                    UPDATE dev_tasks
                    SET staging_deploy_status = :status,
                        staging_deploy_log = :log,
                        started_at = :started_at
                    WHERE id = :id
                """), {
                    "id": dev_task_id,
                    "status": orig_status,
                    "log": orig_log,
                    "started_at": orig_started_at,
                })
                await db.commit()
        print("recover_stale_deploys ok")
    asyncio.run(run())


def main() -> None:
    test_parse_target_user_at_host()
    test_parse_target_user_at_host_with_port()
    test_parse_target_only_host_uses_default_user()
    test_parse_target_only_host_with_port()
    test_parse_target_invalid_port_raises()
    test_parse_target_empty_raises()
    test_deploy_pr_skips_when_staging_url_missing()
    test_deploy_pr_skips_when_ssh_target_missing()
    test_deploy_pr_success_updates_state_and_notifies()
    test_deploy_pr_nonzero_exit_marks_failed_and_notifies()
    test_deploy_pr_timeout_kills_and_marks_failed()
    test_deploy_pr_bad_ssh_target_marks_failed()
    test_deploy_pr_same_repo_concurrent_serializes_and_coalesces()
    test_deploy_pr_different_repos_parallel()
    test_recover_stale_deploys_marks_failed()
    print("\nall test_staging_deploy_service checks passed")


if __name__ == "__main__":
    main()
