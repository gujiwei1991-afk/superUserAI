"""Unit tests for the fix-iteration feedback loop.

Covers:
  - request_fix_iteration helper (new GitHub issue + status flip + dev_log)
  - _handle_modify branching by project state (PRD-edit vs code-fix vs reject)
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "shared"))

from app.gateway.command_parser import Command  # noqa: E402
from app.services.message_handler import MessageHandler  # noqa: E402
from app.services.project_review import request_fix_iteration  # noqa: E402
from shared.constants import ProjectStatus  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


# ---------- request_fix_iteration ----------

def _make_fix_db(prior_count: int = 0):
    db = MagicMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    # for `SELECT COUNT(*) ...` → scalar_one() returns prior_count
    count_result = MagicMock(scalar_one=MagicMock(return_value=prior_count))
    db.execute = AsyncMock(return_value=count_result)
    return db


def _make_project_and_repo(status):
    project = MagicMock()
    project.id = 42
    project.title = "Demo"
    project.prd_content = "PRD body"
    project.status = status
    project.github_issue_number = 7
    repo = MagicMock()
    repo.id = 1
    repo.github_owner = "owner"
    repo.github_repo = "repo"
    repo.has_custom_github_token = False
    repo.github_token_encrypted = ""
    return project, repo


def test_request_fix_iteration_creates_issue_and_flips_status() -> None:
    async def run():
        db = _make_fix_db(prior_count=0)
        project, repo = _make_project_and_repo(ProjectStatus.ACCEPTANCE.value)

        fake_github = MagicMock()
        fake_github.create_issue = AsyncMock(return_value={"number": 123})
        fake_github.close = AsyncMock()
        with patch("app.services.project_review.GitHubService.for_repo",
                   return_value=fake_github):
            issue_no = await request_fix_iteration(
                db, project=project, repo=repo, fix_description="按钮没反应",
            )

        assert issue_no == 123
        assert project.github_issue_number == 123
        assert project.status == ProjectStatus.APPROVED.value
        # create_issue 调用了一次，标题含 "[修复 #1]"，body 含 PRD + fix_description
        fake_github.create_issue.assert_awaited_once()
        kwargs = fake_github.create_issue.await_args.kwargs
        assert "[修复 #1]" in kwargs["title"]
        assert "按钮没反应" in kwargs["body"]
        assert "PRD body" in kwargs["body"]
        # dev_log 记一行
        assert db.add.called
        log = db.add.call_args.args[0]
        assert "fix iteration #1" in log.message
        assert "issue #123" in log.message
    _run(run())
    print("request_fix_iteration creates issue + flips status ok")


def test_request_fix_iteration_increments_round_counter() -> None:
    async def run():
        db = _make_fix_db(prior_count=2)  # 已有两轮 fix
        project, repo = _make_project_and_repo(ProjectStatus.ACCEPTANCE.value)
        fake_github = MagicMock()
        fake_github.create_issue = AsyncMock(return_value={"number": 200})
        fake_github.close = AsyncMock()
        with patch("app.services.project_review.GitHubService.for_repo",
                   return_value=fake_github):
            await request_fix_iteration(
                db, project=project, repo=repo, fix_description="再来一轮",
            )
        kwargs = fake_github.create_issue.await_args.kwargs
        assert "[修复 #3]" in kwargs["title"], kwargs["title"]
    _run(run())
    print("request_fix_iteration increments round counter ok")


# ---------- _handle_modify branching ----------

def _make_handler(status: str, prd: str = "PRD"):
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    wechat = AsyncMock()
    h = MessageHandler(db=db, wechat=wechat)

    user = MagicMock(id=1)
    session = MagicMock(id=10, active_project_id=42, state="idle")
    project = MagicMock()
    project.id = 42
    project.title = "Demo"
    project.prd_content = prd
    project.status = status
    project.github_issue_number = 7
    repo = MagicMock(id=2, github_owner="o", github_repo="r",
                     has_custom_github_token=False, github_token_encrypted="")

    async def stub_active(_s):
        return project, repo, None
    h._get_active_project_context = stub_active
    h.project_service = MagicMock()
    h.project_service.get_messages = AsyncMock(return_value=[])
    h.project_service.add_message = AsyncMock()
    h.project_service.save_prd = AsyncMock()
    h.project_service.update_status = AsyncMock()
    h.session_manager = MagicMock()
    h.session_manager.update_session_state = AsyncMock()
    h.pm_agent = MagicMock()
    h.pm_agent.modify_prd = AsyncMock(return_value="new PRD")
    h._notify_admins_for_review = AsyncMock()
    return h, user, session, project, repo


def test_modify_in_reviewing_calls_pm_agent_not_fix() -> None:
    async def run():
        h, u, s, project, _ = _make_handler(ProjectStatus.REVIEWING.value)
        with patch("app.services.message_handler.MessageHandler._dispatch_fix_iteration",
                   new=AsyncMock()) as fix_mock:
            reply = await h._handle_modify_internal(u, s, "wuser", "改一下表头")
        assert "更新方案" in reply
        h.pm_agent.modify_prd.assert_awaited_once()
        fix_mock.assert_not_called()
    _run(run())
    print("modify in REVIEWING → PRD edit ok")


def test_modify_in_acceptance_dispatches_fix_not_pm() -> None:
    async def run():
        h, u, s, project, repo = _make_handler(ProjectStatus.ACCEPTANCE.value)
        with patch("app.services.project_review.request_fix_iteration",
                   new=AsyncMock(return_value=999)) as fix_mock:
            reply = await h._handle_modify_internal(u, s, "wuser", "登录按钮坏了")
        assert "issue #999" in reply
        fix_mock.assert_awaited_once()
        # PM Agent 不应被调
        h.pm_agent.modify_prd.assert_not_awaited()
    _run(run())
    print("modify in ACCEPTANCE → fix dispatch ok")


def test_modify_in_deployed_dispatches_fix() -> None:
    async def run():
        h, u, s, _p, _r = _make_handler(ProjectStatus.DEPLOYED.value)
        with patch("app.services.project_review.request_fix_iteration",
                   new=AsyncMock(return_value=888)):
            reply = await h._handle_modify_internal(u, s, "wuser", "tooltip 文案不对")
        assert "issue #888" in reply
    _run(run())
    print("modify in DEPLOYED → fix dispatch ok")


def test_modify_in_completed_rejects() -> None:
    async def run():
        h, u, s, _p, _r = _make_handler(ProjectStatus.COMPLETED.value)
        with patch("app.services.project_review.request_fix_iteration",
                   new=AsyncMock(return_value=1)) as fix_mock:
            reply = await h._handle_modify_internal(u, s, "wuser", "再补点")
        assert "已经完成" in reply or "#新需求" in reply
        fix_mock.assert_not_called()
    _run(run())
    print("modify in COMPLETED → rejected ok")


def test_modify_empty_feedback_rejects() -> None:
    async def run():
        h, u, s, _p, _r = _make_handler(ProjectStatus.ACCEPTANCE.value)
        reply = await h._handle_modify_internal(u, s, "wuser", "   ")
        assert "怎么改" in reply or "具体" in reply
    _run(run())
    print("modify empty feedback rejects ok")


def test_modify_dispatch_failure_friendly_error() -> None:
    async def run():
        h, u, s, _p, _r = _make_handler(ProjectStatus.ACCEPTANCE.value)
        with patch("app.services.project_review.request_fix_iteration",
                   new=AsyncMock(side_effect=RuntimeError("github 5xx"))):
            reply = await h._handle_modify_internal(u, s, "wuser", "fix this")
        assert "失败" in reply
    _run(run())
    print("modify dispatch failure → friendly error ok")


def main() -> None:
    test_request_fix_iteration_creates_issue_and_flips_status()
    test_request_fix_iteration_increments_round_counter()
    test_modify_in_reviewing_calls_pm_agent_not_fix()
    test_modify_in_acceptance_dispatches_fix_not_pm()
    test_modify_in_deployed_dispatches_fix()
    test_modify_in_completed_rejects()
    test_modify_empty_feedback_rejects()
    test_modify_dispatch_failure_friendly_error()
    print("\nall test_fix_iteration checks passed")


if __name__ == "__main__":
    main()
