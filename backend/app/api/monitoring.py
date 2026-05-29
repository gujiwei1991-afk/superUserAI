"""可观测性端点：/healthz（就绪探针）+ /metrics（Prometheus 文本）。

设计取舍：
  - 只检查实际被使用的依赖。当前代码库未使用 Redis（仅 config 占位），
    故 /healthz 只验证数据库连通，避免给出误导性的 Redis 健康信号。
  - /metrics 用手写的 Prometheus 文本曝光格式（text exposition format），
    不引入 prometheus_client 依赖；既能被 Prometheus 抓取，也方便人读。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import AsyncSessionLocal, get_db
from app.models import DevTask, Project
from shared.constants import ProjectStatus

logger = logging.getLogger(__name__)
router = APIRouter(tags=["monitoring"])

_VERSION = "0.1.0"
# 部署状态的已知取值，保证即使计数为 0 也曝光对应的时间序列。
_DEPLOY_STATES = ("pending", "deploying", "success", "failed", "skipped")


async def _check_database(
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
) -> tuple[bool, str]:
    """返回 (是否连通, 详情)。session_factory 可注入以便测试。"""
    try:
        async with session_factory() as db:
            await db.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:  # pragma: no cover - 连通失败分支由测试注入
        logger.warning("healthz: database check failed: %s", exc)
        return False, f"down: {exc.__class__.__name__}"


@router.get("/healthz")
async def healthz() -> Response:
    """就绪探针：数据库可连通则 200，否则 503。"""
    db_ok, db_detail = await _check_database()
    status = "ok" if db_ok else "degraded"
    payload = {"status": status, "checks": {"database": db_detail}}
    import json

    return Response(
        content=json.dumps(payload),
        media_type="application/json",
        status_code=200 if db_ok else 503,
    )


def _render_metrics(
    project_counts: dict[str, int],
    prod_counts: dict[str, int],
    staging_counts: dict[str, int],
    version: str = _VERSION,
) -> str:
    """把计数渲染成 Prometheus 文本曝光格式（纯函数，便于测试）。"""
    lines: list[str] = []

    lines.append("# HELP superuserai_build_info Build/version info.")
    lines.append("# TYPE superuserai_build_info gauge")
    lines.append(f'superuserai_build_info{{version="{version}"}} 1')

    lines.append("# HELP superuserai_projects Number of projects by status.")
    lines.append("# TYPE superuserai_projects gauge")
    for st in ProjectStatus:
        n = project_counts.get(st.value, 0)
        lines.append(f'superuserai_projects{{status="{st.value}"}} {n}')

    lines.append(
        "# HELP superuserai_prod_deploys Number of dev_tasks by prod deploy status."
    )
    lines.append("# TYPE superuserai_prod_deploys gauge")
    for st in _DEPLOY_STATES:
        n = prod_counts.get(st, 0)
        lines.append(f'superuserai_prod_deploys{{status="{st}"}} {n}')

    lines.append(
        "# HELP superuserai_staging_deploys Number of dev_tasks by staging deploy status."
    )
    lines.append("# TYPE superuserai_staging_deploys gauge")
    for st in _DEPLOY_STATES:
        n = staging_counts.get(st, 0)
        lines.append(f'superuserai_staging_deploys{{status="{st}"}} {n}')

    return "\n".join(lines) + "\n"


async def _group_count(db: AsyncSession, column) -> dict[str, int]:
    rows = await db.execute(select(column, func.count()).group_by(column))
    return {(k or "unknown"): int(v) for k, v in rows.all()}


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics(db: AsyncSession = Depends(get_db)) -> Response:
    project_counts = await _group_count(db, Project.status)
    prod_counts = await _group_count(db, DevTask.prod_deploy_status)
    staging_counts = await _group_count(db, DevTask.staging_deploy_status)
    body = _render_metrics(project_counts, prod_counts, staging_counts)
    # Prometheus 文本曝光格式的标准 content-type。
    return PlainTextResponse(content=body, media_type="text/plain; version=0.0.4")
