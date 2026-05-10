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
from unittest.mock import AsyncMock, MagicMock


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


def main() -> None:
    test_parse_target_user_at_host()
    test_parse_target_user_at_host_with_port()
    test_parse_target_only_host_uses_default_user()
    test_parse_target_only_host_with_port()
    test_parse_target_invalid_port_raises()
    test_parse_target_empty_raises()
    test_deploy_pr_skips_when_staging_url_missing()
    test_deploy_pr_skips_when_ssh_target_missing()
    print("\nall test_staging_deploy_service checks passed")


if __name__ == "__main__":
    main()
