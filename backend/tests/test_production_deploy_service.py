"""Unit tests for ProductionDeployService (mocked SSH + wechat).

Stand-alone runnable: `python tests/test_production_deploy_service.py`.
Prints `all test_production_deploy_service checks passed` on success.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "shared"))

from app.services.production_deploy_service import _parse_ssh_target  # noqa: E402


def test_parse_target_user_at_host() -> None:
    user, host, port = _parse_ssh_target("deploy@prod.com", default_user="fallback")
    assert (user, host, port) == ("deploy", "prod.com", None)
    print("parse user@host ok")


def test_parse_target_user_at_host_with_port() -> None:
    user, host, port = _parse_ssh_target("deploy@prod.com:2222", default_user="fallback")
    assert (user, host, port) == ("deploy", "prod.com", 2222)
    print("parse user@host:port ok")


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
    from app.services.production_deploy_service import ProductionDeployService
    return ProductionDeployService(
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
    repo.prod_url = "https://app.example.com"
    repo.prod_ssh_target = "deploy@prod.com"
    repo.prod_deploy_path = "/srv/prod/repo"
    repo.prod_compose_file = "docker-compose.prod.yml"
    repo.prod_run_migrations = True
    for k, v in overrides.items():
        setattr(repo, k, v)
    return repo


def _make_dev_task():
    dt = MagicMock()
    dt.id = 42
    dt.pr_number = 11
    dt.prod_deploy_status = "pending"
    dt.prod_deployed_at = None
    dt.prod_deploy_log = None
    dt.prod_deployed_sha = None
    return dt


def _make_project():
    p = MagicMock()
    p.id = 7
    p.title = "Prod Test Project"
    p.status = "staged"
    return p


def _make_db():
    db = MagicMock()
    db.commit = AsyncMock()
    # _activate_creator_scoring uses db.execute().scalar_one_or_none() to find session,
    # then db.add + db.flush. Stubbed to "no existing session" so the new-session branch runs.
    no_session = MagicMock(scalar_one_or_none=lambda: None)
    db.execute = AsyncMock(return_value=no_session)
    db.add = MagicMock()
    db.flush = AsyncMock()
    return db


def _fake_subprocess(returncode: int, stdout: bytes = b"ok\n"):
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, None))
    proc.kill = MagicMock()
    proc.wait = AsyncMock()
    return proc


def test_deploy_merge_skips_when_prod_url_missing() -> None:
    async def run():
        svc = _make_service()
        repo = _make_repo(prod_url=None)
        dev_task = _make_dev_task()
        project = _make_project()
        db = _make_db()
        await svc.deploy_merge(db, repo, project, dev_task, merge_sha="abc", pr_number=3)
        assert dev_task.prod_deploy_status == "skipped"
        svc.wechat_client.send_text.assert_not_called()
    asyncio.run(run())
    print("deploy_merge skips when prod_url missing ok")


def test_deploy_merge_success_flips_to_acceptance_and_records_sha() -> None:
    async def run():
        svc = _make_service()
        repo = _make_repo()
        dev_task = _make_dev_task()
        project = _make_project()
        project.creator_id = 99
        db = _make_db()
        fake_proc = _fake_subprocess(returncode=0, stdout=b"deploy ok\nUp 0\n")

        with patch("app.services.production_deploy_service.asyncio.create_subprocess_exec",
                   AsyncMock(return_value=fake_proc)) as mock_exec, \
             patch("app.services.production_deploy_service.notify_creator_targeted",
                   AsyncMock()) as mock_notify:
            await svc.deploy_merge(db, repo, project, dev_task,
                                   merge_sha="cafebabe", pr_number=11)

        assert dev_task.prod_deploy_status == "success"
        assert dev_task.prod_deployed_at is not None
        assert dev_task.prod_deployed_sha == "cafebabe"
        # 新行为：进入 ACCEPTANCE（待验收），而非 DEPLOYED
        assert project.status == "acceptance", project.status
        assert mock_notify.await_count == 1
        body = mock_notify.await_args.args[3]
        assert "https://app.example.com" in body
        assert "PR #11" in body
        # SSH 命令至少调过一次
        assert mock_exec.await_count == 1
        ssh_args = mock_exec.await_args.args
        assert "ssh" in ssh_args
        assert "deploy@prod.com" in ssh_args
    asyncio.run(run())
    print("deploy_merge success path ok")


def test_deploy_merge_includes_alembic_when_run_migrations_true() -> None:
    async def run():
        svc = _make_service()
        repo = _make_repo(prod_run_migrations=True)
        dev_task = _make_dev_task()
        project = _make_project()
        db = _make_db()
        fake_proc = _fake_subprocess(returncode=0)

        with patch("app.services.production_deploy_service.asyncio.create_subprocess_exec",
                   AsyncMock(return_value=fake_proc)) as mock_exec, \
             patch("app.services.production_deploy_service.notify_creator_targeted",
                   AsyncMock()):
            await svc.deploy_merge(db, repo, project, dev_task,
                                   merge_sha="sha1", pr_number=11)

        # remote_script 通过 stdin 传，asyncio.create_subprocess_exec 的 communicate 接收 script bytes
        script_bytes = fake_proc.communicate.await_args.args[0]
        assert b"alembic upgrade head" in script_bytes
    asyncio.run(run())
    print("deploy_merge runs alembic when prod_run_migrations true ok")


def test_deploy_merge_skips_alembic_when_run_migrations_false() -> None:
    async def run():
        svc = _make_service()
        repo = _make_repo(prod_run_migrations=False)
        dev_task = _make_dev_task()
        project = _make_project()
        db = _make_db()
        fake_proc = _fake_subprocess(returncode=0)

        with patch("app.services.production_deploy_service.asyncio.create_subprocess_exec",
                   AsyncMock(return_value=fake_proc)), \
             patch("app.services.production_deploy_service.notify_creator_targeted",
                   AsyncMock()):
            await svc.deploy_merge(db, repo, project, dev_task,
                                   merge_sha="sha1", pr_number=11)

        script_bytes = fake_proc.communicate.await_args.args[0]
        assert b"alembic upgrade head" not in script_bytes
    asyncio.run(run())
    print("deploy_merge skips alembic when prod_run_migrations false ok")


def test_deploy_merge_nonzero_exit_marks_failed_and_notifies() -> None:
    async def run():
        svc = _make_service()
        repo = _make_repo()
        dev_task = _make_dev_task()
        project = _make_project()
        db = _make_db()
        fake_proc = _fake_subprocess(returncode=1, stdout=b"compose error\nbuild failed\n")

        with patch("app.services.production_deploy_service.asyncio.create_subprocess_exec",
                   AsyncMock(return_value=fake_proc)), \
             patch("app.services.production_deploy_service.notify_creator_targeted",
                   AsyncMock()) as mock_notify:
            await svc.deploy_merge(db, repo, project, dev_task,
                                   merge_sha="bad", pr_number=12)

        assert dev_task.prod_deploy_status == "failed"
        # project 状态不被翻到 deployed
        assert project.status == "staged"
        assert "build failed" in (dev_task.prod_deploy_log or "")
        assert mock_notify.await_count == 1
        body = mock_notify.await_args.args[3]
        assert "PR #12" in body and "失败" in body
    asyncio.run(run())
    print("deploy_merge nonzero exit path ok")


def test_deploy_merge_timeout_marks_failed() -> None:
    async def run():
        svc = _make_service()
        svc.deploy_timeout_sec = 0.1
        repo = _make_repo()
        dev_task = _make_dev_task()
        project = _make_project()
        db = _make_db()

        proc = MagicMock()
        proc.returncode = None

        async def hang(*a, **kw):
            await asyncio.sleep(5)
            return (b"", None)

        proc.communicate = hang
        proc.kill = MagicMock()
        proc.wait = AsyncMock()

        with patch("app.services.production_deploy_service.asyncio.create_subprocess_exec",
                   AsyncMock(return_value=proc)), \
             patch("app.services.production_deploy_service.notify_creator_targeted",
                   AsyncMock()) as mock_notify:
            await svc.deploy_merge(db, repo, project, dev_task,
                                   merge_sha="tmo", pr_number=13)

        assert dev_task.prod_deploy_status == "failed"
        assert "timeout" in (dev_task.prod_deploy_log or "").lower()
        proc.kill.assert_called_once()
        assert mock_notify.await_count == 1
    asyncio.run(run())
    print("deploy_merge timeout path ok")


def test_deploy_merge_bad_ssh_target() -> None:
    async def run():
        svc = _make_service()
        repo = _make_repo(prod_ssh_target="deploy@prod.com:not-a-port")
        dev_task = _make_dev_task()
        project = _make_project()
        db = _make_db()

        with patch("app.services.production_deploy_service.notify_creator_targeted",
                   AsyncMock()) as mock_notify:
            await svc.deploy_merge(db, repo, project, dev_task,
                                   merge_sha="x", pr_number=14)

        assert dev_task.prod_deploy_status == "failed"
        assert "ssh target parse error" in (dev_task.prod_deploy_log or "")
        assert mock_notify.await_count == 1
    asyncio.run(run())
    print("deploy_merge bad ssh target ok")


def main() -> None:
    test_parse_target_user_at_host()
    test_parse_target_user_at_host_with_port()
    test_parse_target_empty_raises()
    test_deploy_merge_skips_when_prod_url_missing()
    test_deploy_merge_success_flips_to_acceptance_and_records_sha()
    test_deploy_merge_includes_alembic_when_run_migrations_true()
    test_deploy_merge_skips_alembic_when_run_migrations_false()
    test_deploy_merge_nonzero_exit_marks_failed_and_notifies()
    test_deploy_merge_timeout_marks_failed()
    test_deploy_merge_bad_ssh_target()
    print("\nall test_production_deploy_service checks passed")


if __name__ == "__main__":
    main()
