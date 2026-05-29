"""Unit tests for monitoring endpoints + admin alerting.

无需真实 DB：用 mock session/工厂注入，覆盖
  - _render_metrics 纯函数（曝光格式、计数、全量时间序列）
  - _check_database 连通/失败两条分支
  - notify_admins 投递与容错
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "shared"))

from app.api.monitoring import _check_database, _render_metrics  # noqa: E402
from app.services.project_review import notify_admins  # noqa: E402
from shared.constants import ProjectStatus  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


# ---------- _render_metrics ----------

def test_render_metrics_contains_all_series() -> None:
    out = _render_metrics({}, {}, {})
    # build_info
    assert 'superuserai_build_info{version="0.1.0"} 1' in out
    # 每个 ProjectStatus 都有一条（即使计数为 0）
    for st in ProjectStatus:
        assert f'superuserai_projects{{status="{st.value}"}} 0' in out
    # 部署状态全量曝光
    for st in ("pending", "deploying", "success", "failed", "skipped"):
        assert f'superuserai_prod_deploys{{status="{st}"}} 0' in out
        assert f'superuserai_staging_deploys{{status="{st}"}} 0' in out
    # 含 HELP/TYPE 头
    assert "# TYPE superuserai_projects gauge" in out
    print("render_metrics contains all series ok")


def test_render_metrics_reflects_counts() -> None:
    out = _render_metrics(
        {ProjectStatus.ACCEPTANCE.value: 3, ProjectStatus.COMPLETED.value: 5},
        {"success": 7, "failed": 2},
        {"deploying": 1},
    )
    assert f'superuserai_projects{{status="{ProjectStatus.ACCEPTANCE.value}"}} 3' in out
    assert f'superuserai_projects{{status="{ProjectStatus.COMPLETED.value}"}} 5' in out
    assert 'superuserai_prod_deploys{status="success"} 7' in out
    assert 'superuserai_prod_deploys{status="failed"} 2' in out
    assert 'superuserai_staging_deploys{status="deploying"} 1' in out
    print("render_metrics reflects counts ok")


# ---------- _check_database ----------

class _FakeSession:
    def __init__(self, fail: bool) -> None:
        self._fail = fail

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, *_a, **_k):
        if self._fail:
            raise RuntimeError("connection refused")
        return MagicMock()


def _factory(fail: bool):
    return lambda: _FakeSession(fail)


def test_check_database_ok() -> None:
    ok, detail = _run(_check_database(session_factory=_factory(fail=False)))
    assert ok is True
    assert detail == "ok"
    print("check_database ok branch ok")


def test_check_database_down() -> None:
    ok, detail = _run(_check_database(session_factory=_factory(fail=True)))
    assert ok is False
    assert detail.startswith("down:")
    print("check_database down branch ok")


# ---------- notify_admins ----------

def _make_db_with_admins(admins):
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = admins
    db.execute = AsyncMock(return_value=result)
    return db


def test_notify_admins_dms_each_and_returns_count() -> None:
    async def run():
        admins = [MagicMock(wechat_user_id="a1"), MagicMock(wechat_user_id="a2")]
        db = _make_db_with_admins(admins)
        wechat = MagicMock()
        wechat.send_text = AsyncMock()
        sent = await notify_admins(db, wechat, "deploy failed")
        assert sent == 2
        assert wechat.send_text.await_count == 2
    _run(run())
    print("notify_admins dms each + counts ok")


def test_notify_admins_survives_send_failure() -> None:
    async def run():
        admins = [MagicMock(wechat_user_id="a1"), MagicMock(wechat_user_id="a2")]
        db = _make_db_with_admins(admins)
        wechat = MagicMock()
        # 第一个抛错，第二个成功 → 不应中断，返回 1
        wechat.send_text = AsyncMock(side_effect=[RuntimeError("net"), None])
        sent = await notify_admins(db, wechat, "deploy failed")
        assert sent == 1
    _run(run())
    print("notify_admins survives send failure ok")


def test_notify_admins_empty_returns_zero() -> None:
    async def run():
        db = _make_db_with_admins([])
        wechat = MagicMock()
        wechat.send_text = AsyncMock()
        sent = await notify_admins(db, wechat, "x")
        assert sent == 0
        wechat.send_text.assert_not_awaited()
    _run(run())
    print("notify_admins empty returns zero ok")


def main() -> None:
    test_render_metrics_contains_all_series()
    test_render_metrics_reflects_counts()
    test_check_database_ok()
    test_check_database_down()
    test_notify_admins_dms_each_and_returns_count()
    test_notify_admins_survives_send_failure()
    test_notify_admins_empty_returns_zero()
    print("\nall test_monitoring checks passed")


if __name__ == "__main__":
    main()
