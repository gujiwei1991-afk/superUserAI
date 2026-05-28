"""Unit tests for MessageHandler._handle_score validation.

Covers the new state whitelist + score-range rules added for the
acceptance/scoring closed loop.
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
from shared.constants import ProjectStatus  # noqa: E402


def _make_handler(active_project_status: str):
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    wechat = AsyncMock()
    h = MessageHandler(db=db, wechat=wechat)

    user = MagicMock()
    user.id = 1
    session = MagicMock()
    session.id = 11
    session.active_project_id = 7
    session.state = "idle"

    project = MagicMock()
    project.id = 7
    project.title = "X"
    project.status = active_project_status
    repo = MagicMock(id=2)

    async def stub_active(s):
        return project, repo, None

    h._get_active_project_context = stub_active
    h.project_service = MagicMock()
    h.project_service.add_message = AsyncMock()
    h.project_service.update_status = AsyncMock()
    h.session_manager = MagicMock()
    h.session_manager.update_session_state = AsyncMock()
    return h, user, session, project


def _make_score_cmd(score, comment):
    return Command(type="score", args={"score": score, "comment": comment})


def _run(coro):
    return asyncio.run(coro)


def test_score_rejects_below_one() -> None:
    h, u, s, _ = _make_handler(ProjectStatus.ACCEPTANCE.value)
    reply = _run(h._handle_score(u, s, "wuser", _make_score_cmd(0, "ok")))
    assert "1-10" in reply, reply
    print("score rejects 0 ok")


def test_score_rejects_above_ten() -> None:
    h, u, s, _ = _make_handler(ProjectStatus.ACCEPTANCE.value)
    reply = _run(h._handle_score(u, s, "wuser", _make_score_cmd(11, "ok")))
    assert "1-10" in reply, reply
    print("score rejects 11 ok")


def test_score_rejects_non_integer() -> None:
    h, u, s, _ = _make_handler(ProjectStatus.ACCEPTANCE.value)
    reply = _run(h._handle_score(u, s, "wuser", _make_score_cmd("abc", "ok")))
    assert "1-10" in reply, reply
    print("score rejects non-int ok")


def test_score_requires_comment() -> None:
    h, u, s, _ = _make_handler(ProjectStatus.ACCEPTANCE.value)
    reply = _run(h._handle_score(u, s, "wuser", _make_score_cmd(8, "")))
    assert "文字反馈" in reply, reply
    print("score requires comment ok")


def test_score_blocks_staged_state() -> None:
    h, u, s, _ = _make_handler(ProjectStatus.STAGED.value)
    reply = _run(h._handle_score(u, s, "wuser", _make_score_cmd(8, "looks good")))
    assert "main" in reply or "合并" in reply, reply
    print("score blocks STAGED ok")


def test_score_blocks_completed_state() -> None:
    h, u, s, _ = _make_handler(ProjectStatus.COMPLETED.value)
    reply = _run(h._handle_score(u, s, "wuser", _make_score_cmd(8, "again")))
    assert "重复" in reply or "已完成" in reply, reply
    print("score blocks COMPLETED ok")


def test_score_accepts_acceptance_state() -> None:
    h, u, s, project = _make_handler(ProjectStatus.ACCEPTANCE.value)
    reply = _run(h._handle_score(u, s, "wuser", _make_score_cmd(9, "good")))
    assert "已记录" in reply, reply
    # 副作用：写入了 score、feedback；翻成 COMPLETED 在 update_status mock 里
    assert project.score == 9.0
    assert project.feedback == "good"
    h.project_service.update_status.assert_awaited_once()
    print("score accepts ACCEPTANCE state ok")


def test_score_accepts_deployed_state() -> None:
    h, u, s, project = _make_handler(ProjectStatus.DEPLOYED.value)
    reply = _run(h._handle_score(u, s, "wuser", _make_score_cmd(7, "shipped")))
    assert "已记录" in reply, reply
    assert project.score == 7.0
    print("score accepts DEPLOYED state ok")


def main() -> None:
    test_score_rejects_below_one()
    test_score_rejects_above_ten()
    test_score_rejects_non_integer()
    test_score_requires_comment()
    test_score_blocks_staged_state()
    test_score_blocks_completed_state()
    test_score_accepts_acceptance_state()
    test_score_accepts_deployed_state()
    print("\nall test_score_validation checks passed")


if __name__ == "__main__":
    main()
