# Staging 自动部署 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 backend 在收到 GitHub PR opened/synchronize/reopened webhook 后，集中 SSH 到用户自管服务器跑 docker compose，把当前 PR 部署到一个固定 staging URL，并通过企业微信通知客户去看效果；失败时给开发者发文字摘要。

**Architecture:** Webhook → backend BackgroundTask → `StagingDeployService.deploy_pr()` → SSH 命令（系统 `ssh`）→ 远端 `git fetch + checkout + docker compose up -d --build` → 成功/失败更新 dev_task + 通知 creator（走 `notify_creator_targeted` 群/私聊路由）。Per-repo `asyncio.Lock` 串行 + pending head_sha 合并；启动时清理卡死 deploying 任务。

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic, asyncio.create_subprocess_exec（不引第三方 SSH 库），httpx（已用，wechat_client）

**Spec:** `docs/superpowers/specs/2026-05-10-staging-auto-deploy-design.md`

---

## File Map

**Create:**
- `backend/alembic/versions/<rev>_add_staging_deploy_fields.py` — 加 7 列
- `backend/app/services/staging_deploy_service.py` — 主服务
- `backend/tests/test_staging_deploy_service.py` — 单元测试（stand-alone，mock SSH + wechat）
- `backend/tests/e2e_staging_deploy.py` — 端到端（模拟 webhook → 验证 service 被调用）
- `docs/staging-server-setup.md` — 服务器一次性配置 README

**Modify:**
- `shared/shared/constants.py` — `ProjectStatus` 加 `STAGED`
- `backend/app/models/repo.py` — 加 4 个 staging_* 字段
- `backend/app/models/dev_task.py` — 加 3 个 staging_* 字段
- `backend/app/config.py` — 加 4 个 staging_* 设置
- `backend/.env.example` — sync 4 个新设置（变量名占位）
- `backend/app/api/webhooks.py` — handle PR opened/synchronize/reopened
- `backend/app/api/admin.py` — 加 `/admin/dev-tasks/{id}/redeploy-staging` 端点
- `backend/app/main.py` — 启动时调 `_recover_stale_deploys()`
- `backend/templates/repos.html` — repo 编辑表单加 staging fieldset
- `backend/templates/project_detail.html` — 加 staging deploy 卡片

---

## Pre-flight

- [ ] **Step 0: Confirm we're on the staging branch + clean tree + alembic head**

```bash
cd /Users/gujiwei/python/superUserAI && git status -sb
```
Expected: `## feat/staging-auto-deploy` 第一行；后续无 staged/unstaged 改动（除了未跟踪的 `.DS_Store` / `vworkapi-bridge.zip` 等，是上面已存在的 untracked，不影响）。

```bash
cd /Users/gujiwei/python/superUserAI/backend && /Users/gujiwei/python/superUserAI/.venv/bin/alembic current 2>&1 | tail -1
```
Expected: `i3c4d5e6f7a8 (head)`

如果分支不是 `feat/staging-auto-deploy`，先 `git checkout feat/staging-auto-deploy`（spec 已经 commit 在该分支）。如果 alembic head 不一致，停下来对账。

---

## Task 1: 给 ProjectStatus 加 STAGED

**Files:**
- Modify: `shared/shared/constants.py`

- [ ] **Step 1: 加 enum 值**

在 `shared/shared/constants.py` 的 `ProjectStatus` 类中，在 `ACCEPTANCE = "acceptance"` **之前**插入一行：

```python
class ProjectStatus(str, Enum):
    DRAFTING = "drafting"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    DEVELOPING = "developing"
    DEPLOYED = "deployed"
    STAGED = "staged"        # ← 新增
    ACCEPTANCE = "acceptance"
    COMPLETED = "completed"
    REJECTED = "rejected"
```

- [ ] **Step 2: 烟雾测试**

```bash
/Users/gujiwei/python/superUserAI/.venv/bin/python -c "
from shared.constants import ProjectStatus
assert ProjectStatus.STAGED.value == 'staged'
print('STAGED added ok')
"
```
Expected: `STAGED added ok`

- [ ] **Step 3: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add shared/shared/constants.py && git commit -m "feat(constants): add ProjectStatus.STAGED for staging deploy state"
```

---

## Task 2: Alembic 迁移加 7 列

**Files:**
- Create: `backend/alembic/versions/j4d5e6f7a8b9_add_staging_deploy_fields.py`

- [ ] **Step 1: 生成空迁移**

```bash
cd /Users/gujiwei/python/superUserAI/backend && /Users/gujiwei/python/superUserAI/.venv/bin/alembic revision -m "add_staging_deploy_fields"
```
Expected: 输出形如 `Generating /Users/gujiwei/python/superUserAI/backend/alembic/versions/<id>_add_staging_deploy_fields.py`。记下生成的 revision id（替换下文 `<NEW_REV_ID>`）。

- [ ] **Step 2: 把生成的迁移文件改名 + 写内容**

把生成的文件重命名为 `j4d5e6f7a8b9_add_staging_deploy_fields.py`（保持跟旧 head 一致的 12-char id 风格）—— 如果 alembic 已经按 `<NEW_REV_ID>_add_staging_deploy_fields.py` 生成，直接用它的 revision id 即可，不必改名；只是把内容写成下面这段：

```python
"""add staging deploy fields

Revision ID: j4d5e6f7a8b9
Revises: i3c4d5e6f7a8
Create Date: 2026-05-10 ...

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "j4d5e6f7a8b9"
down_revision = "i3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("repos", sa.Column("staging_url", sa.Text(), nullable=True))
    op.add_column("repos", sa.Column("staging_ssh_target", sa.String(length=255), nullable=True))
    op.add_column("repos", sa.Column("staging_deploy_path", sa.Text(), nullable=True))
    op.add_column(
        "repos",
        sa.Column(
            "staging_compose_file",
            sa.String(length=255),
            nullable=False,
            server_default="docker-compose.staging.yml",
        ),
    )
    op.add_column(
        "dev_tasks",
        sa.Column(
            "staging_deploy_status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column("dev_tasks", sa.Column("staging_deployed_at", sa.DateTime(), nullable=True))
    op.add_column("dev_tasks", sa.Column("staging_deploy_log", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("dev_tasks", "staging_deploy_log")
    op.drop_column("dev_tasks", "staging_deployed_at")
    op.drop_column("dev_tasks", "staging_deploy_status")
    op.drop_column("repos", "staging_compose_file")
    op.drop_column("repos", "staging_deploy_path")
    op.drop_column("repos", "staging_ssh_target")
    op.drop_column("repos", "staging_url")
```

注意：如果 alembic 自动生成的 revision id 不是 `j4d5e6f7a8b9`，把上面 `revision = "..."` 替换成实际生成的那个；并把文件名也保持跟 revision id 对应。

- [ ] **Step 3: 跑迁移**

```bash
cd /Users/gujiwei/python/superUserAI/backend && /Users/gujiwei/python/superUserAI/.venv/bin/alembic upgrade head 2>&1 | tail -3
```
Expected: 末尾包含 `Running upgrade i3c4d5e6f7a8 -> <NEW_REV_ID>, add_staging_deploy_fields` 且无 traceback。

- [ ] **Step 4: 验证 schema**

```bash
/Users/gujiwei/python/superUserAI/.venv/bin/python -c "
import asyncio
from app.database import AsyncSessionLocal
from sqlalchemy import text

async def go():
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(text(\"\"\"
            SELECT column_name FROM information_schema.columns
            WHERE table_name='repos' AND column_name LIKE 'staging_%'
            ORDER BY column_name
        \"\"\"))).all()
        print('repos cols:', [r[0] for r in rows])
        rows = (await db.execute(text(\"\"\"
            SELECT column_name FROM information_schema.columns
            WHERE table_name='dev_tasks' AND column_name LIKE 'staging_%'
            ORDER BY column_name
        \"\"\"))).all()
        print('dev_tasks cols:', [r[0] for r in rows])
asyncio.run(go())
"
```
Expected:
```
repos cols: ['staging_compose_file', 'staging_deploy_path', 'staging_ssh_target', 'staging_url']
dev_tasks cols: ['staging_deploy_log', 'staging_deploy_status', 'staging_deployed_at']
```

- [ ] **Step 5: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add backend/alembic/versions/*_add_staging_deploy_fields.py && git commit -m "feat(db): add staging deploy fields to repos + dev_tasks"
```

---

## Task 3: Repo + DevTask 模型加 staging 字段

**Files:**
- Modify: `backend/app/models/repo.py`
- Modify: `backend/app/models/dev_task.py`

- [ ] **Step 1: Repo 模型加 4 字段**

编辑 `backend/app/models/repo.py`，在 `wechat_group_bound_by` 那行**之后**、`projects` relationship **之前** 插入：

```python
    staging_url: Mapped[str | None] = mapped_column(Text)
    staging_ssh_target: Mapped[str | None]
    staging_deploy_path: Mapped[str | None] = mapped_column(Text)
    staging_compose_file: Mapped[str] = mapped_column(default="docker-compose.staging.yml")
```

`Mapped[str | None]` 默认是 `String`，符合 `String(255)` 期望（具体长度 alembic 已定）。`Text` 给 URL 和 path（长度不定）。

- [ ] **Step 2: DevTask 模型加 3 字段**

编辑 `backend/app/models/dev_task.py`，在 `finished_at: Mapped[datetime | None]` 那行**之后**、relationships **之前** 插入：

```python
    staging_deploy_status: Mapped[str] = mapped_column(default="pending")
    staging_deployed_at: Mapped[datetime | None]
    staging_deploy_log: Mapped[str | None] = mapped_column(Text)
```

- [ ] **Step 3: 烟雾测试 — 字段可读、默认值符合**

```bash
/Users/gujiwei/python/superUserAI/.venv/bin/python -c "
import asyncio
from app.database import AsyncSessionLocal
from app.models import Repo, DevTask
from sqlalchemy import select

async def go():
    async with AsyncSessionLocal() as db:
        # 检查 mapper 不报错 + 字段都在
        repo_cols = {c.name for c in Repo.__table__.columns}
        for f in ('staging_url', 'staging_ssh_target', 'staging_deploy_path', 'staging_compose_file'):
            assert f in repo_cols, f'Repo missing: {f}'
        dt_cols = {c.name for c in DevTask.__table__.columns}
        for f in ('staging_deploy_status', 'staging_deployed_at', 'staging_deploy_log'):
            assert f in dt_cols, f'DevTask missing: {f}'
        print('models ok')
asyncio.run(go())
"
```
Expected: `models ok`

- [ ] **Step 4: 跑现有 e2e 验证没破东西**

```bash
cd /Users/gujiwei/python/superUserAI/backend && /Users/gujiwei/python/superUserAI/.venv/bin/python tests/e2e_task_claim_lock.py 2>&1 | tail -3
```
Expected: 末尾 `all e2e_task_claim_lock checks passed`（或类似），无 traceback。

- [ ] **Step 5: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add backend/app/models/repo.py backend/app/models/dev_task.py && git commit -m "feat(models): add staging deploy fields to Repo + DevTask"
```

---

## Task 4: 新增 staging 配置项

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`

- [ ] **Step 1: config.py 加 4 设置**

编辑 `backend/app/config.py` 的 `Settings` 类，加入：

```python
    staging_ssh_key_path: str = ""
    staging_ssh_user_default: str = "deploy"
    staging_deploy_timeout_sec: int = 600
    staging_log_tail_lines: int = 200
```

放在 `Settings` 类内适当位置（可放在其他 staging-相关设置附近；如果当前没有相关 grouping，放在类末尾即可）。

- [ ] **Step 2: .env.example sync**

编辑 `backend/.env.example`，文件末尾加入：

```
# Staging auto-deploy
STAGING_SSH_KEY_PATH=
STAGING_SSH_USER_DEFAULT=deploy
STAGING_DEPLOY_TIMEOUT_SEC=600
STAGING_LOG_TAIL_LINES=200
```

- [ ] **Step 3: 烟雾测试 — settings 加载**

```bash
cd /Users/gujiwei/python/superUserAI/backend && /Users/gujiwei/python/superUserAI/.venv/bin/python -c "
from app.config import get_settings
s = get_settings()
assert hasattr(s, 'staging_ssh_key_path')
assert s.staging_ssh_user_default == 'deploy'
assert s.staging_deploy_timeout_sec == 600
assert s.staging_log_tail_lines == 200
print('config ok')
"
```
Expected: `config ok`

- [ ] **Step 4: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add backend/app/config.py backend/.env.example && git commit -m "feat(config): staging deploy settings (ssh key path, timeout, log tail)"
```

---

## Task 5: SSH target parser（TDD）

**Files:**
- Create: `backend/tests/test_staging_deploy_service.py`
- Create: `backend/app/services/staging_deploy_service.py`（先建空 module + parser）

- [ ] **Step 1: 写 parser 的测试（先 fail）**

创建 `backend/tests/test_staging_deploy_service.py`：

```python
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


def main() -> None:
    test_parse_target_user_at_host()
    test_parse_target_user_at_host_with_port()
    test_parse_target_only_host_uses_default_user()
    test_parse_target_only_host_with_port()
    test_parse_target_invalid_port_raises()
    test_parse_target_empty_raises()
    print("\nall test_staging_deploy_service checks passed")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 跑测试，确认 fail（module 不存在）**

```bash
cd /Users/gujiwei/python/superUserAI/backend && /Users/gujiwei/python/superUserAI/.venv/bin/python tests/test_staging_deploy_service.py 2>&1 | tail -3
```
Expected: 含 `ModuleNotFoundError: No module named 'app.services.staging_deploy_service'`。

- [ ] **Step 3: 写 module 骨架 + parser**

创建 `backend/app/services/staging_deploy_service.py`：

```python
"""Staging auto-deploy service.

Handles SSH-driven docker compose deploys to user's self-managed staging
server, triggered by GitHub PR webhooks.

Spec: docs/superpowers/specs/2026-05-10-staging-auto-deploy-design.md
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _parse_ssh_target(
    target: str,
    *,
    default_user: str,
) -> tuple[str, str, Optional[int]]:
    """Parse `[user@]host[:port]` into (user, host, port).

    Raises ValueError on malformed input (empty, non-numeric port, etc.).
    """
    if not target or not target.strip():
        raise ValueError("ssh target is empty")
    target = target.strip()

    if "@" in target:
        user, _, hostport = target.partition("@")
        if not user:
            raise ValueError(f"empty user in ssh target: {target!r}")
    else:
        user = default_user
        hostport = target

    if ":" in hostport:
        host, _, port_str = hostport.partition(":")
        if not host:
            raise ValueError(f"empty host in ssh target: {target!r}")
        try:
            port = int(port_str)
        except ValueError:
            raise ValueError(f"invalid port in ssh target: {target!r}") from None
    else:
        host = hostport
        port = None

    if not host:
        raise ValueError(f"empty host in ssh target: {target!r}")

    return user, host, port
```

- [ ] **Step 4: 跑测试，确认 pass**

```bash
cd /Users/gujiwei/python/superUserAI/backend && /Users/gujiwei/python/superUserAI/.venv/bin/python tests/test_staging_deploy_service.py 2>&1 | tail -3
```
Expected: 末尾 `all test_staging_deploy_service checks passed`。

- [ ] **Step 5: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add backend/app/services/staging_deploy_service.py backend/tests/test_staging_deploy_service.py && git commit -m "feat(staging_deploy): scaffold service + ssh target parser (TDD)"
```

---

## Task 6: StagingDeployService 类骨架 + skipped 路径

**Files:**
- Modify: `backend/app/services/staging_deploy_service.py`
- Modify: `backend/tests/test_staging_deploy_service.py`

- [ ] **Step 1: 加 skipped 路径的测试**

在 `backend/tests/test_staging_deploy_service.py` 的 `_parse_ssh_target` 测试**后面**、`def main()` **前面** 插入：

```python
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
```

并把它们加到 `main()`：

```python
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
```

- [ ] **Step 2: 跑，确认 fail**

```bash
cd /Users/gujiwei/python/superUserAI/backend && /Users/gujiwei/python/superUserAI/.venv/bin/python tests/test_staging_deploy_service.py 2>&1 | tail -3
```
Expected: 含 `cannot import name 'StagingDeployService'` 或 `AttributeError`。

- [ ] **Step 3: 在 service 里加 class 骨架 + skipped 路径**

编辑 `backend/app/services/staging_deploy_service.py`，**在 `_parse_ssh_target` 函数下面** 加：

```python
import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.gateway.wechat_client import WeChatClient
    from app.models import DevTask, Project, Repo


_STAGING_REQUIRED_FIELDS = (
    "staging_url",
    "staging_ssh_target",
    "staging_deploy_path",
    "staging_compose_file",
)


class StagingDeployService:
    def __init__(
        self,
        wechat_client: "WeChatClient",
        ssh_key_path: str,
        ssh_user_default: str = "deploy",
        deploy_timeout_sec: int = 600,
        log_tail_lines: int = 200,
    ) -> None:
        self.wechat_client = wechat_client
        self.ssh_key_path = ssh_key_path
        self.ssh_user_default = ssh_user_default
        self.deploy_timeout_sec = deploy_timeout_sec
        self.log_tail_lines = log_tail_lines
        # per-repo lock 串行
        self._locks: dict[int, asyncio.Lock] = {}
        # per-repo "下一次要部署的 head_sha"，用于合并并发请求
        self._pending: dict[int, tuple[int, str]] = {}  # repo_id -> (pr_number, head_sha)

    def _missing_staging_fields(self, repo: "Repo") -> list[str]:
        return [f for f in _STAGING_REQUIRED_FIELDS if not getattr(repo, f, None)]

    async def deploy_pr(
        self,
        db: "AsyncSession",
        repo: "Repo",
        project: "Project",
        dev_task: "DevTask",
        pr_number: int,
        head_sha: str,
    ) -> None:
        missing = self._missing_staging_fields(repo)
        if missing:
            logger.info(
                "staging deploy skipped repo_id=%s missing=%s",
                repo.id, missing,
            )
            dev_task.staging_deploy_status = "skipped"
            dev_task.staging_deploy_log = (
                f"skipped: missing staging fields: {', '.join(missing)}"
            )
            await db.commit()
            return
        # 后续步骤会在 Task 7+ 实现
        raise NotImplementedError("happy path not implemented yet")
```

- [ ] **Step 4: 跑测试，确认 pass**

```bash
cd /Users/gujiwei/python/superUserAI/backend && /Users/gujiwei/python/superUserAI/.venv/bin/python tests/test_staging_deploy_service.py 2>&1 | tail -3
```
Expected: 末尾 `all test_staging_deploy_service checks passed`。

- [ ] **Step 5: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add backend/app/services/staging_deploy_service.py backend/tests/test_staging_deploy_service.py && git commit -m "feat(staging_deploy): service skeleton + skipped path when config incomplete"
```

---

## Task 7: deploy_pr 成功路径（SSH + DB 更新 + 企微通知）

**Files:**
- Modify: `backend/app/services/staging_deploy_service.py`
- Modify: `backend/tests/test_staging_deploy_service.py`

- [ ] **Step 1: 加成功路径的测试**

在 `backend/tests/test_staging_deploy_service.py` 现有 `test_deploy_pr_skips_*` 后面插入：

```python
from unittest.mock import patch


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
```

并把它加到 `main()`。

- [ ] **Step 2: 跑测试，确认 fail（NotImplementedError）**

```bash
cd /Users/gujiwei/python/superUserAI/backend && /Users/gujiwei/python/superUserAI/.venv/bin/python tests/test_staging_deploy_service.py 2>&1 | tail -5
```
Expected: 含 `NotImplementedError: happy path not implemented yet`。

- [ ] **Step 3: 实现成功路径**

编辑 `backend/app/services/staging_deploy_service.py`，把 `deploy_pr` 末尾的 `raise NotImplementedError(...)` 替换成完整成功路径。整个 `deploy_pr` 现在长这样：

```python
    async def deploy_pr(
        self,
        db: "AsyncSession",
        repo: "Repo",
        project: "Project",
        dev_task: "DevTask",
        pr_number: int,
        head_sha: str,
    ) -> None:
        missing = self._missing_staging_fields(repo)
        if missing:
            logger.info(
                "staging deploy skipped repo_id=%s missing=%s",
                repo.id, missing,
            )
            dev_task.staging_deploy_status = "skipped"
            dev_task.staging_deploy_log = (
                f"skipped: missing staging fields: {', '.join(missing)}"
            )
            await db.commit()
            return

        try:
            user, host, port = _parse_ssh_target(
                repo.staging_ssh_target,
                default_user=self.ssh_user_default,
            )
        except ValueError as e:
            logger.warning("staging deploy bad ssh target repo_id=%s: %s", repo.id, e)
            dev_task.staging_deploy_status = "failed"
            dev_task.staging_deploy_log = f"ssh target parse error: {e}"
            await db.commit()
            await self._notify_failure(db, project, dev_task, pr_number)
            return

        # 标记 deploying，同步 commit
        dev_task.staging_deploy_status = "deploying"
        dev_task.staging_deploy_log = None
        await db.commit()

        ssh_args = [
            "ssh",
            "-i", self.ssh_key_path,
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=15",
        ]
        if port is not None:
            ssh_args += ["-p", str(port)]
        ssh_args += [f"{user}@{host}", "bash", "-s"]

        # 远端脚本（注意 shlex.quote 防注入）
        import shlex
        remote_script = (
            "set -euo pipefail\n"
            f"cd {shlex.quote(repo.staging_deploy_path)}\n"
            f"git fetch origin pull/{int(pr_number)}/head:pr-{int(pr_number)}\n"
            f"git checkout -f pr-{int(pr_number)}\n"
            f"git reset --hard {shlex.quote(head_sha)}\n"
            f"docker compose -f {shlex.quote(repo.staging_compose_file)} up -d --build\n"
            f"docker compose -f {shlex.quote(repo.staging_compose_file)} ps\n"
        )

        proc = await asyncio.create_subprocess_exec(
            *ssh_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        try:
            stdout, _ = await asyncio.wait_for(
                proc.communicate(remote_script.encode()),
                timeout=self.deploy_timeout_sec,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            dev_task.staging_deploy_status = "failed"
            dev_task.staging_deploy_log = f"deploy timeout after {self.deploy_timeout_sec}s"
            await db.commit()
            await self._notify_failure(db, project, dev_task, pr_number)
            return

        log_text = (stdout or b"").decode("utf-8", errors="replace")
        # 截取最后 N 行
        lines = log_text.splitlines()
        if len(lines) > self.log_tail_lines:
            lines = lines[-self.log_tail_lines:]
        dev_task.staging_deploy_log = "\n".join(lines)

        if proc.returncode != 0:
            dev_task.staging_deploy_status = "failed"
            await db.commit()
            await self._notify_failure(db, project, dev_task, pr_number)
            return

        # 成功
        from datetime import datetime
        dev_task.staging_deploy_status = "success"
        dev_task.staging_deployed_at = datetime.utcnow()
        from shared.constants import ProjectStatus
        project.status = ProjectStatus.STAGED.value
        await db.commit()
        await self._notify_success(db, project, repo, pr_number)

    async def _notify_success(
        self,
        db: "AsyncSession",
        project: "Project",
        repo: "Repo",
        pr_number: int,
    ) -> None:
        from app.services.project_review import notify_creator_targeted
        body = (
            f"🎉 需求《{project.title}》已部署到测试环境\n\n"
            f"PR #{pr_number}\n"
            f"👉 {repo.staging_url}\n\n"
            "满意请回复  #评分 <1-10> <意见>\n"
            "需要修改请回复  #修改 <说明>"
        )
        try:
            await notify_creator_targeted(db, self.wechat_client, project, body)
        except Exception:
            logger.exception("staging notify success failed project=%s", project.id)

    async def _notify_failure(
        self,
        db: "AsyncSession",
        project: "Project",
        dev_task: "DevTask",
        pr_number: int,
    ) -> None:
        from app.services.project_review import notify_creator_targeted
        log = (dev_task.staging_deploy_log or "").strip()
        # 取最后 200 字符当摘要
        summary = log[-200:] if log else "(no log)"
        body = (
            f"❌ PR #{pr_number} 部署到测试环境失败\n\n"
            f"错误摘要：\n{summary}\n\n"
            f"详情见管理后台 project_id={project.id}"
        )
        try:
            await notify_creator_targeted(db, self.wechat_client, project, body)
        except Exception:
            logger.exception("staging notify failure failed project=%s", project.id)
```

- [ ] **Step 4: 跑测试，确认 pass**

```bash
cd /Users/gujiwei/python/superUserAI/backend && /Users/gujiwei/python/superUserAI/.venv/bin/python tests/test_staging_deploy_service.py 2>&1 | tail -3
```
Expected: 末尾 `all test_staging_deploy_service checks passed`。

- [ ] **Step 5: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add backend/app/services/staging_deploy_service.py backend/tests/test_staging_deploy_service.py && git commit -m "feat(staging_deploy): success path — SSH + db update + creator notify"
```

---

## Task 8: deploy_pr 失败路径测试覆盖

**Files:**
- Modify: `backend/tests/test_staging_deploy_service.py`

> 失败路径在 Task 7 已经实现（`returncode != 0` + `TimeoutError` + parse error 三条），这一 Task 只补测试覆盖。

- [ ] **Step 1: 加 3 个失败路径的测试**

在 `backend/tests/test_staging_deploy_service.py` 现有 success 测试后面插入：

```python
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
```

把这 3 个加到 `main()`。

- [ ] **Step 2: 跑测试，确认 pass（实现已就位）**

```bash
cd /Users/gujiwei/python/superUserAI/backend && /Users/gujiwei/python/superUserAI/.venv/bin/python tests/test_staging_deploy_service.py 2>&1 | tail -3
```
Expected: 末尾 `all test_staging_deploy_service checks passed`。

如果有失败，回去 Task 7 的实现里对照修。

- [ ] **Step 3: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add backend/tests/test_staging_deploy_service.py && git commit -m "test(staging_deploy): cover failure paths (nonzero exit, timeout, bad ssh target)"
```

---

## Task 9: 同 repo 串行 + pending 合并

**Files:**
- Modify: `backend/app/services/staging_deploy_service.py`
- Modify: `backend/tests/test_staging_deploy_service.py`

- [ ] **Step 1: 加并发测试（先 fail）**

在 `backend/tests/test_staging_deploy_service.py` 加：

```python
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
            # 记一下这次调用是发给哪个 head_sha 的
            # remote_script 在 stdin，不在 args；用 call counter 作 proxy
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
```

把这 2 个加到 `main()`。

- [ ] **Step 2: 跑测试，确认 fail**

```bash
cd /Users/gujiwei/python/superUserAI/backend && /Users/gujiwei/python/superUserAI/.venv/bin/python tests/test_staging_deploy_service.py 2>&1 | tail -10
```
Expected: 同 repo 那个测试 assert 失败（call_log 长度是 3 不是 2，因为还没合并），或不同 repo 那个超时。

- [ ] **Step 3: 实现 lock + pending 合并**

编辑 `backend/app/services/staging_deploy_service.py`，把现在的 `deploy_pr` 改名成 `_deploy_pr_inner`（保留全部内容不变），然后加新的 `deploy_pr` 当作"门面"，处理 lock + 合并：

```python
    async def deploy_pr(
        self,
        db: "AsyncSession",
        repo: "Repo",
        project: "Project",
        dev_task: "DevTask",
        pr_number: int,
        head_sha: str,
    ) -> None:
        # skipped 路径不进锁（廉价、立刻返回）
        missing = self._missing_staging_fields(repo)
        if missing:
            logger.info(
                "staging deploy skipped repo_id=%s missing=%s",
                repo.id, missing,
            )
            dev_task.staging_deploy_status = "skipped"
            dev_task.staging_deploy_log = (
                f"skipped: missing staging fields: {', '.join(missing)}"
            )
            await db.commit()
            return

        lock = self._locks.setdefault(repo.id, asyncio.Lock())
        if lock.locked():
            # 有部署在跑：把"最新 head_sha"记下来，让当前部署完后接力一次
            self._pending[repo.id] = (pr_number, head_sha)
            logger.info(
                "staging deploy queued (coalesce) repo_id=%s pr=%s sha=%s",
                repo.id, pr_number, head_sha,
            )
            return

        async with lock:
            await self._deploy_pr_inner(db, repo, project, dev_task, pr_number, head_sha)

            # 部署完看看有没有 pending 的，有就接力一次（用最新的 sha）
            pending = self._pending.pop(repo.id, None)
            if pending is not None:
                p_pr, p_sha = pending
                logger.info(
                    "staging deploy coalesced replay repo_id=%s pr=%s sha=%s",
                    repo.id, p_pr, p_sha,
                )
                await self._deploy_pr_inner(db, repo, project, dev_task, p_pr, p_sha)
```

并把原来的 `async def deploy_pr` 改名为 `_deploy_pr_inner`（**注意把 skipped 那一段从 inner 里删掉**，因为现在归到外层 deploy_pr 里了）。

修改后 `_deploy_pr_inner` 签名：

```python
    async def _deploy_pr_inner(
        self,
        db: "AsyncSession",
        repo: "Repo",
        project: "Project",
        dev_task: "DevTask",
        pr_number: int,
        head_sha: str,
    ) -> None:
        # 不再有 skipped 检查；调用方已经过滤
        try:
            user, host, port = _parse_ssh_target(...)
        except ValueError ...
        # ... （Task 7 里 deploy_pr 的剩余全部内容，从 try parse_ssh 一直到末尾通知）
```

- [ ] **Step 4: 跑测试，确认 pass**

```bash
cd /Users/gujiwei/python/superUserAI/backend && /Users/gujiwei/python/superUserAI/.venv/bin/python tests/test_staging_deploy_service.py 2>&1 | tail -3
```
Expected: `all test_staging_deploy_service checks passed`

- [ ] **Step 5: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add backend/app/services/staging_deploy_service.py backend/tests/test_staging_deploy_service.py && git commit -m "feat(staging_deploy): per-repo lock + pending-sha coalesce on concurrent push"
```

---

## Task 10: 启动时清理卡死 deploying 任务

**Files:**
- Modify: `backend/app/services/staging_deploy_service.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_staging_deploy_service.py`

- [ ] **Step 1: 加恢复测试**

在 `backend/tests/test_staging_deploy_service.py` 加：

```python
def test_recover_stale_deploys_marks_failed() -> None:
    """模拟 backend 重启：dev_task 卡在 deploying 但开始时间超过 15min → 强改 failed。"""
    async def run():
        from app.services.staging_deploy_service import StagingDeployService
        # 这个测试不调 SSH/wechat，只验 SQL 行为；用真 DB
        from app.database import AsyncSessionLocal
        from sqlalchemy import text

        # 准备一条假 dev_task，状态 deploying + started_at 16 分钟前
        # 用一条已有 project+repo+devtask 的任意 repo（如果库里没有，跳过）
        async with AsyncSessionLocal() as db:
            row = (await db.execute(text(
                "SELECT id FROM dev_tasks LIMIT 1"
            ))).first()
            if row is None:
                print("recover_stale_deploys: no dev_task in db, SKIP")
                return
            dev_task_id = row[0]
            # 设置成 deploying + 18 分钟前开始
            await db.execute(text("""
                UPDATE dev_tasks
                SET staging_deploy_status='deploying',
                    started_at = NOW() - INTERVAL '18 minutes',
                    staging_deployed_at = NULL
                WHERE id = :id
            """), {"id": dev_task_id})
            await db.commit()

        svc = _make_service()
        await svc.recover_stale_deploys(stale_after_sec=900)  # 15 min

        async with AsyncSessionLocal() as db:
            row = (await db.execute(text(
                "SELECT staging_deploy_status, staging_deploy_log FROM dev_tasks WHERE id=:id"
            ), {"id": dev_task_id})).first()
            assert row[0] == "failed", row[0]
            assert "restart" in (row[1] or "").lower()
        print("recover_stale_deploys ok")
    asyncio.run(run())
```

加到 `main()`（注意：这个测试需要数据库连接 + 已有 dev_task 行；如果跑不起来会 SKIP 自己跳过）。

- [ ] **Step 2: 实现 recover_stale_deploys**

在 `backend/app/services/staging_deploy_service.py` 的 `StagingDeployService` 类内加方法：

```python
    async def recover_stale_deploys(self, stale_after_sec: int = 900) -> int:
        """Mark any dev_task stuck in 'deploying' for > stale_after_sec as failed.

        Called once on backend startup; returns the number of rows updated.
        """
        from app.database import AsyncSessionLocal
        from sqlalchemy import text

        async with AsyncSessionLocal() as db:
            result = await db.execute(text("""
                UPDATE dev_tasks
                SET staging_deploy_status = 'failed',
                    staging_deploy_log = 'marker: backend restart while deploying'
                WHERE staging_deploy_status = 'deploying'
                  AND staging_deployed_at IS NULL
                  AND started_at < NOW() - make_interval(secs => :stale_after)
                RETURNING id
            """), {"stale_after": stale_after_sec})
            updated = list(result.scalars())
            await db.commit()
            if updated:
                logger.warning(
                    "staging_deploy: recovered %d stale 'deploying' tasks: %s",
                    len(updated), updated,
                )
            return len(updated)
```

- [ ] **Step 3: Wire 到 main.py 的 lifespan**

编辑 `backend/app/main.py`，把现有的 `lifespan` 改成：

```python
@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    # 启动时清理卡死的 staging deploy 任务
    try:
        from app.services.staging_deploy_service import StagingDeployService
        from app.gateway.wechat_client import WeChatClient
        from app.config import get_settings
        settings = get_settings()
        svc = StagingDeployService(
            wechat_client=WeChatClient(),
            ssh_key_path=settings.staging_ssh_key_path,
            ssh_user_default=settings.staging_ssh_user_default,
            deploy_timeout_sec=settings.staging_deploy_timeout_sec,
            log_tail_lines=settings.staging_log_tail_lines,
        )
        await svc.recover_stale_deploys()
    except Exception:
        logging.getLogger(__name__).exception("staging_deploy: stale recovery failed at startup")
    yield
    await close_db()
```

- [ ] **Step 4: 跑测试**

```bash
cd /Users/gujiwei/python/superUserAI/backend && /Users/gujiwei/python/superUserAI/.venv/bin/python tests/test_staging_deploy_service.py 2>&1 | tail -3
```
Expected: `all test_staging_deploy_service checks passed`（如果库为空 recover 测试会 SKIP 但其他 11 个全过）。

- [ ] **Step 5: 烟雾测试 — 启动 backend 不报错**

```bash
cd /Users/gujiwei/python/superUserAI/backend && /Users/gujiwei/python/superUserAI/.venv/bin/python -c "
import asyncio
from app.main import app, lifespan
async def go():
    async with lifespan(app):
        pass
asyncio.run(go())
print('lifespan ok')
"
```
Expected: `lifespan ok`，无 traceback。

- [ ] **Step 6: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add backend/app/services/staging_deploy_service.py backend/app/main.py backend/tests/test_staging_deploy_service.py && git commit -m "feat(staging_deploy): startup recovery for stale 'deploying' tasks"
```

---

## Task 11: webhook 集成（PR opened/synchronize/reopened）

**Files:**
- Modify: `backend/app/api/webhooks.py`
- Create: `backend/tests/e2e_staging_deploy.py`

- [ ] **Step 1: 写 e2e 测试 — 模拟 webhook → 验证 service 被调**

创建 `backend/tests/e2e_staging_deploy.py`：

```python
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
    """模拟 PR opened webhook → 验证 staging_deploy_service.deploy_pr 被异步调用一次。"""
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

    # 给该 repo 临时填 staging 字段
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
        # 没配 webhook secret 的话直接接受;有的话传一个空 signature 也接受（看现有逻辑）
        # 现有验证只在 settings.github_webhook_secret 非空时启用
        resp = client.post(
            "/api/webhooks/github",
            data=json.dumps(payload),
            headers={"X-GitHub-Event": "pull_request"},
        )
        assert resp.status_code == 200, (resp.status_code, resp.text)

    # 等 BackgroundTask 跑完
    asyncio.run(asyncio.sleep(0.2))

    assert len(deploy_calls) == 1, deploy_calls
    assert deploy_calls[0][3] == pr_number
    assert deploy_calls[0][4].startswith("deadbeef")
    print(f"webhook → deploy_pr triggered ok ({deploy_calls[0]})")


def main() -> None:
    test_pr_opened_webhook_triggers_deploy()
    print("\nall e2e_staging_deploy checks passed")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 跑 e2e（先 fail 因为还没 wire）**

```bash
cd /Users/gujiwei/python/superUserAI/backend && /Users/gujiwei/python/superUserAI/.venv/bin/python tests/e2e_staging_deploy.py 2>&1 | tail -5
```
Expected: 失败 — 找不到 `staging_deploy_service` 在 webhooks 模块，或 deploy_calls 长度为 0。

- [ ] **Step 3: 在 webhooks.py 集成**

编辑 `backend/app/api/webhooks.py`：

3a. 在 import 区加：
```python
from fastapi import BackgroundTasks
from app.config import get_settings as _get_settings
from app.services.staging_deploy_service import StagingDeployService
from app.models import DevTask, Repo
```

3b. 在文件顶部模块级（`wechat = WeChatClient()` 那行下面）实例化服务：
```python
def _build_staging_service() -> StagingDeployService:
    s = _get_settings()
    return StagingDeployService(
        wechat_client=wechat,
        ssh_key_path=s.staging_ssh_key_path,
        ssh_user_default=s.staging_ssh_user_default,
        deploy_timeout_sec=s.staging_deploy_timeout_sec,
        log_tail_lines=s.staging_log_tail_lines,
    )

staging_deploy_service = _build_staging_service()
```

3c. 改造 webhook 函数签名加入 `BackgroundTasks`：

```python
@router.post("/webhooks/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
```

3d. 在事件分发那段加新分支（替换现有 `if event == "pull_request":` 这段）：

```python
    if event == "pull_request":
        action = payload.get("action")
        if action in ("opened", "synchronize", "reopened"):
            await _dispatch_staging_deploy(payload, db, background_tasks)
        else:
            await _handle_pull_request_event(payload, db)
```

3e. 文件末尾加新函数 `_dispatch_staging_deploy`：

```python
async def _dispatch_staging_deploy(
    payload: dict[str, Any],
    db: AsyncSession,
    background_tasks: BackgroundTasks,
) -> None:
    pr = payload.get("pull_request") or {}
    pr_number = pr.get("number")
    head_sha = (pr.get("head") or {}).get("sha")
    if not isinstance(pr_number, int) or not head_sha:
        logger.info("staging dispatch: invalid pr payload, skipping")
        return

    # 用 pr_number 找 project，再拿 repo 和最新 dev_task
    proj_row = (await db.execute(
        select(Project).where(Project.github_pr_number == pr_number)
    )).scalar_one_or_none()
    if proj_row is None:
        logger.info("staging dispatch: no project for PR #%s", pr_number)
        return

    repo_row = (await db.execute(
        select(Repo).where(Repo.id == proj_row.repo_id)
    )).scalar_one_or_none()
    dt_row = (await db.execute(
        select(DevTask)
        .where(DevTask.project_id == proj_row.id)
        .order_by(DevTask.id.desc())
        .limit(1)
    )).scalar_one_or_none()

    if repo_row is None or dt_row is None:
        logger.info("staging dispatch: missing repo/dev_task for project %s", proj_row.id)
        return

    if dt_row.staging_deploy_status == "deploying":
        logger.info(
            "staging dispatch: dev_task %s already deploying, skip dispatch (lock will coalesce)",
            dt_row.id,
        )
        # 仍然调一次让 service 内部的 pending 机制接住最新 sha
    background_tasks.add_task(
        staging_deploy_service.deploy_pr,
        db, repo_row, proj_row, dt_row, pr_number, head_sha,
    )
```

- [ ] **Step 4: 跑 e2e，确认 pass**

```bash
cd /Users/gujiwei/python/superUserAI/backend && /Users/gujiwei/python/superUserAI/.venv/bin/python tests/e2e_staging_deploy.py 2>&1 | tail -3
```
Expected: 末尾 `all e2e_staging_deploy checks passed`（如果库里没合适的数据，SKIP 也算通过）。

- [ ] **Step 5: 跑现有所有 backend e2e 验证没破东西**

```bash
cd /Users/gujiwei/python/superUserAI/backend && for f in tests/e2e_*.py; do echo "=== $f ==="; /Users/gujiwei/python/superUserAI/.venv/bin/python "$f" 2>&1 | tail -2; done
```
Expected: 每个脚本末尾都是自己的 "passed" 句，无 traceback。

- [ ] **Step 6: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add backend/app/api/webhooks.py backend/tests/e2e_staging_deploy.py && git commit -m "feat(webhook): dispatch staging deploy on PR opened/synchronize/reopened"
```

---

## Task 12: 管理后台"重试部署"端点

**Files:**
- Modify: `backend/app/api/admin.py`

> 这个端点用 admin 认证（现有），点击"重试部署"按钮触发，复用 `staging_deploy_service.deploy_pr`。

- [ ] **Step 1: 看现有 admin.py 的鉴权 + 路由 pattern**

```bash
grep -n "@router\.\(post\|get\)\|require_admin\|Depends" /Users/gujiwei/python/superUserAI/backend/app/api/admin.py | head -20
```

记下鉴权依赖名（如 `Depends(require_admin)` / `Depends(get_current_admin)` / 类似）。下文 `<ADMIN_DEP>` 替换。

- [ ] **Step 2: 加 endpoint**

在 `backend/app/api/admin.py` **末尾**（或在跟 dev_task 相关的现有 endpoint 旁）加：

```python
from fastapi import BackgroundTasks
from app.api.webhooks import staging_deploy_service  # 复用单例
from app.models import DevTask, Project, Repo


@router.post("/admin/dev-tasks/{dev_task_id}/redeploy-staging")
async def admin_redeploy_staging(
    dev_task_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _admin = <ADMIN_DEP>,
) -> dict[str, Any]:
    dt = await db.get(DevTask, dev_task_id)
    if dt is None:
        raise HTTPException(status_code=404, detail="dev_task not found")
    project = await db.get(Project, dt.project_id)
    repo = await db.get(Repo, dt.repo_id)
    if project is None or repo is None:
        raise HTTPException(status_code=404, detail="project/repo missing")
    if dt.pr_number is None:
        raise HTTPException(status_code=400, detail="dev_task has no pr_number")
    # 用 GitHub 拿 head_sha 太麻烦；这里假设 PR head 没动，使用 PR 最新提交的 SHA
    # 简化：让 deploy_pr 远端 git fetch 时用 pull/N/head 拿到 GitHub 最新；本地传一个空字符串会让 reset 失败
    # 改进：用 GH API 拉 PR 最新 head_sha；MVP 阶段直接 fetch + checkout 默认头
    # 简单起见：让脚本去 fetch 之后 checkout 远端 branch 的 head；spec 里写的是 reset --hard {head_sha}，
    # 这里我们用一个特殊 marker 让 service 跳过 reset
    background_tasks.add_task(
        staging_deploy_service.deploy_pr,
        db, repo, project, dt, dt.pr_number, "FETCH_HEAD",  # 让 reset --hard FETCH_HEAD 用最新远端
    )
    return {"queued": True, "dev_task_id": dev_task_id}
```

> 注：上面用 `"FETCH_HEAD"` 作为 head_sha 传入，远端 git 命令会 `git reset --hard FETCH_HEAD`（git fetch 后该引用即指向最新远端 PR head）。这是 MVP 简化；将来可加 GH API 拉取真实 sha。

- [ ] **Step 3: 烟雾测试**

```bash
cd /Users/gujiwei/python/superUserAI/backend && /Users/gujiwei/python/superUserAI/.venv/bin/python -c "
import inspect
from app.api.admin import admin_redeploy_staging
src = inspect.getsource(admin_redeploy_staging)
assert 'staging_deploy_service.deploy_pr' in src
assert 'pr_number' in src
print('admin redeploy endpoint ok')
"
```
Expected: `admin redeploy endpoint ok`

- [ ] **Step 4: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add backend/app/api/admin.py && git commit -m "feat(admin): /admin/dev-tasks/{id}/redeploy-staging button endpoint"
```

---

## Task 13: 管理后台模板改动

**Files:**
- Modify: `backend/templates/repos.html`
- Modify: `backend/templates/project_detail.html`

- [ ] **Step 1: 看 repos.html 的现有 form 结构**

```bash
grep -n "name=\"\|fieldset\|form" /Users/gujiwei/python/superUserAI/backend/templates/repos.html | head -30
```

- [ ] **Step 2: repos.html 加 staging fieldset**

在 `backend/templates/repos.html` 的 repo 编辑表单内（具体定位：现有最后一个 `name=` 输入框之后、`</form>` 之前）插入：

```html
<fieldset style="margin-top: 1rem; padding: 0.75rem; border: 1px solid #ccc;">
  <legend>Staging 部署配置（可选，留空则该 repo 不做自动 staging 部署）</legend>

  <div>
    <label>staging_url：</label>
    <input type="url" name="staging_url" value="{{ repo.staging_url or '' }}"
           placeholder="https://staging.myapp.com" style="width: 100%;">
  </div>

  <div>
    <label>SSH target：</label>
    <input type="text" name="staging_ssh_target" value="{{ repo.staging_ssh_target or '' }}"
           placeholder="deploy@server.com[:port]" style="width: 100%;">
  </div>

  <div>
    <label>Deploy path：</label>
    <input type="text" name="staging_deploy_path" value="{{ repo.staging_deploy_path or '' }}"
           placeholder="/srv/staging/myapp" style="width: 100%;">
  </div>

  <div>
    <label>Compose file：</label>
    <input type="text" name="staging_compose_file"
           value="{{ repo.staging_compose_file or 'docker-compose.staging.yml' }}"
           style="width: 100%;">
  </div>
</fieldset>
```

并把对应的 admin POST handler（在 `admin.py` 里 repo 保存的地方）扩展接收这 4 个字段并写到 model。grep 找位置：

```bash
grep -n "staging_url\|name = \|description = " /Users/gujiwei/python/superUserAI/backend/app/api/admin.py | head -10
```

找到 repo 保存逻辑（form 解析），扩展加 4 行：
```python
repo.staging_url = form.get("staging_url") or None
repo.staging_ssh_target = form.get("staging_ssh_target") or None
repo.staging_deploy_path = form.get("staging_deploy_path") or None
repo.staging_compose_file = form.get("staging_compose_file") or "docker-compose.staging.yml"
```

> 如果 admin.py 用的是 Pydantic body 而不是 form，需要相应在 schema 里加字段。具体根据 grep 结果决定。

- [ ] **Step 3: project_detail.html 加 staging 卡片**

在 `backend/templates/project_detail.html` 的合适位置（如项目详情主卡片下面），插入：

```html
{% if dev_task %}
<section style="margin-top: 1rem; padding: 0.75rem; border: 1px solid #ddd; border-radius: 6px;">
  <h3>Staging 部署</h3>
  <div>状态：
    {% set s = dev_task.staging_deploy_status %}
    <span style="color:
      {% if s == 'success' %}#0a0
      {% elif s == 'failed' %}#c00
      {% elif s == 'deploying' %}#c80
      {% else %}#888{% endif %};
      font-weight: bold;">{{ s }}</span>
  </div>
  {% if dev_task.staging_deployed_at %}
  <div>最近成功部署：{{ dev_task.staging_deployed_at.strftime('%Y-%m-%d %H:%M:%S') }}</div>
  {% endif %}
  {% if repo.staging_url %}
  <div>Staging URL：<a href="{{ repo.staging_url }}" target="_blank">{{ repo.staging_url }}</a></div>
  {% endif %}
  {% if dev_task.staging_deploy_log %}
  <details>
    <summary>查看部署日志</summary>
    <pre style="max-height: 240px; overflow: auto; background: #f7f7f7; padding: 0.5rem;">{{ dev_task.staging_deploy_log }}</pre>
  </details>
  {% endif %}
  {% if s in ('failed', 'success') %}
  <form method="post" action="/admin/dev-tasks/{{ dev_task.id }}/redeploy-staging" style="margin-top: 0.5rem;">
    <button type="submit">重试部署</button>
  </form>
  {% endif %}
</section>
{% endif %}
```

注意：如果模板上下文目前没有 `dev_task` / `repo` 变量，需要在 `admin.py` 渲染该模板的 handler 里查询并传入。

- [ ] **Step 4: 烟雾测试 — 模板能渲染**

```bash
cd /Users/gujiwei/python/superUserAI/backend && /Users/gujiwei/python/superUserAI/.venv/bin/python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('templates'), autoescape=True)
for name in ('repos.html', 'project_detail.html'):
    t = env.get_template(name)
    print(name, '— template loads ok')
"
```
Expected: 两行都打印 `... template loads ok`，无 traceback。

> 真正渲染（带数据）需要起 backend + 浏览器实测，留到 Task 15 真机验证。

- [ ] **Step 5: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add backend/templates/repos.html backend/templates/project_detail.html backend/app/api/admin.py && git commit -m "feat(admin-ui): repo staging fieldset + project staging deploy card"
```

---

## Task 14: 服务器一次性配置 README

**Files:**
- Create: `docs/staging-server-setup.md`

- [ ] **Step 1: 写 README**

创建 `docs/staging-server-setup.md`：

```markdown
# Staging 服务器一次性配置指南

> 给"自管 staging 服务器 + 公网 IP + 域名"场景准备的步骤。
> 完成这些之后，superUserAI 后端就能 SSH 上来自动部署 PR 到 staging。

## 前置

- 一台 Linux 服务器，有公网 IP，可 22 端口入站
- 一个域名 `your-domain.com`，DNS 管理权限
- 你的 superUserAI backend 运行机器（`backend-host`）

## 1. 服务器侧：装基础软件 + 建 deploy 用户

```bash
# 装 docker
curl -fsSL https://get.docker.com | sudo sh

# 装 docker compose plugin（Ubuntu/Debian）
sudo apt install docker-compose-plugin

# 装 nginx + certbot
sudo apt install nginx certbot python3-certbot-nginx

# 建 deploy 用户
sudo useradd -m -s /bin/bash deploy
sudo usermod -aG docker deploy
```

## 2. backend 机器：生成 SSH key

```bash
sudo mkdir -p /etc/superuserai
sudo ssh-keygen -t ed25519 -f /etc/superuserai/staging_id_ed25519 -N ""
sudo chown $(id -u):$(id -g) /etc/superuserai/staging_id_ed25519
sudo chmod 600 /etc/superuserai/staging_id_ed25519
```

把公钥（`/etc/superuserai/staging_id_ed25519.pub`）内容贴到 staging 服务器上 `deploy` 用户的 `~/.ssh/authorized_keys`：

```bash
# 在 staging 服务器上
sudo -iu deploy
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo "<贴入公钥内容>" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
exit
```

测试 backend 能不能免密 SSH 上来：

```bash
# 在 backend 机器上
ssh -i /etc/superuserai/staging_id_ed25519 deploy@<staging-server-ip> "echo ok"
```
应该输出 `ok`，无密码提示。

## 3. staging 服务器：给 deploy 用户配 GitHub 拉取权限

需要 staging 服务器能 `git fetch` 你的 GitHub repo。最安全方案是给每个 repo 加一个 read-only deploy key：

```bash
# 在 staging 服务器上，作为 deploy 用户
sudo -iu deploy
ssh-keygen -t ed25519 -f ~/.ssh/<repo-name>_ed25519 -N ""
cat ~/.ssh/<repo-name>_ed25519.pub
```

把这个公钥贴到 GitHub repo Settings → Deploy keys → Add deploy key（**不勾** "Allow write access"）。

然后配 SSH alias：

```bash
# ~/.ssh/config
Host github-<repo-name>
  HostName github.com
  User git
  IdentityFile ~/.ssh/<repo-name>_ed25519
  IdentitiesOnly yes
```

## 4. staging 服务器：第一次 git clone

```bash
sudo -iu deploy
sudo mkdir -p /srv/staging && sudo chown deploy:deploy /srv/staging
cd /srv/staging
git clone github-<repo-name>:<owner>/<repo>.git <repo-name>
```

之后 superUserAI 就只 `git fetch` + `git checkout`，不再 clone。

## 5. DNS：把 staging 子域名指向服务器

到你 DNS 管理面板，加一条 A 记录：
```
staging.your-domain.com  →  <staging-server-public-ip>
```

等 DNS 生效（通常 1~10 分钟），可用 `dig staging.your-domain.com` 验证。

## 6. nginx 反向代理 + Let's Encrypt 证书

假设你的 docker-compose.staging.yml 把 app 暴露到 `127.0.0.1:8080`。

写 `/etc/nginx/sites-available/staging.your-domain.com`：

```nginx
server {
    server_name staging.your-domain.com;
    listen 80;
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

启用 + 申请证书：

```bash
sudo ln -s /etc/nginx/sites-available/staging.your-domain.com /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d staging.your-domain.com
```

certbot 会自动改 nginx 配启用 HTTPS + 配 80→443 跳转 + 写 cron 自动续证。

## 7. 项目侧：写 docker-compose.staging.yml

在你的 GitHub repo 根目录加一个 `docker-compose.staging.yml`，最小示例：

```yaml
services:
  app:
    build: .
    ports:
      - "127.0.0.1:8080:8080"
    environment:
      - DATABASE_URL=postgres://user:pass@postgres:5432/staging
    depends_on:
      - postgres

  postgres:
    image: postgres:16
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=pass
      - POSTGRES_DB=staging
    volumes:
      - staging_pg_data:/var/lib/postgresql/data

volumes:
  staging_pg_data:
```

要点：
- **app 端口绑 `127.0.0.1`**（让 nginx 反代来流量；不暴露 0.0.0.0 防绕过 TLS）
- DB / 上传文件 / 缓存 用 named volume 持久化
- 别在 staging 用生产数据，README 提示客户

## 8. backend 配置

backend 的 `.env` 里设：

```
STAGING_SSH_KEY_PATH=/etc/superuserai/staging_id_ed25519
STAGING_SSH_USER_DEFAULT=deploy
STAGING_DEPLOY_TIMEOUT_SEC=600
STAGING_LOG_TAIL_LINES=200
```

到 superUserAI admin 后台，编辑你的 repo，填：
- staging_url: `https://staging.your-domain.com`
- staging_ssh_target: `deploy@<staging-server-ip>`
- staging_deploy_path: `/srv/staging/<repo-name>`
- staging_compose_file: `docker-compose.staging.yml`

## 9. 验证

让 dev-agent 跑一个简单 issue → 提 PR → 看 backend 日志：

```bash
journalctl -u superuserai-backend -f --since "2 minutes ago" | grep staging
```

应该看到：
- `staging deploy ... starting`
- 远端 docker compose 输出
- `staging deploy ... success`

然后企微 creator 应该收到一条文本 + 链接。
```

- [ ] **Step 2: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add docs/staging-server-setup.md && git commit -m "docs: staging server one-time setup guide"
```

---

## Task 15: 全量回归 + 真机验证准备

- [ ] **Step 1: backend 所有 e2e 全过**

```bash
cd /Users/gujiwei/python/superUserAI/backend && for f in tests/e2e_*.py tests/test_*.py; do echo "=== $f ==="; /Users/gujiwei/python/superUserAI/.venv/bin/python "$f" 2>&1 | tail -2; done
```
Expected: 每个脚本末尾都是自己的 "passed" 句，无 traceback。

- [ ] **Step 2: dev-agent + bridge 测试也过**

```bash
cd /Users/gujiwei/python/superUserAI/dev-agent && /Users/gujiwei/python/superUserAI/.venv/bin/python tests/e2e_git_ops_worktree.py 2>&1 | tail -2
cd /Users/gujiwei/python/superUserAI/vworkapi-bridge && /Users/gujiwei/python/superUserAI/.venv/bin/python tests/e2e_bridge.py 2>&1 | tail -2
```
Expected: 都 passed。

- [ ] **Step 3: 启动 backend 烟雾测**

```bash
cd /Users/gujiwei/python/superUserAI/backend && /Users/gujiwei/python/superUserAI/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 2888 &
sleep 3
curl -s http://127.0.0.1:2888/api/health 2>&1 | head -1 || echo "(no health endpoint, that's fine)"
# 测一下 webhook endpoint 接受请求
curl -s -X POST http://127.0.0.1:2888/api/webhooks/github \
  -H 'X-GitHub-Event: ping' \
  -H 'Content-Type: application/json' \
  -d '{"zen": "test"}' | head -c 200
echo
# 杀掉
kill %1 2>/dev/null
```
Expected: webhook 接受 ping 返回 `{"status":"ok"}` 之类。

- [ ] **Step 4: 真机验证清单（用户人工执行，留作 hand-off）**

按 `docs/staging-server-setup.md` 配好测试服务器后：

a. admin 后台编辑一个测试 repo，填齐 4 个 staging 字段
b. 让 dev-agent 跑一个简单 issue → 提 PR
c. 看 backend 日志：`staging deploy ... starting` → SSH → docker compose 输出 → `success`
d. 企微 creator 应收到一条文本含 staging URL
e. 故意把 docker-compose.staging.yml 改坏（比如 build 错），重提 PR；看失败通知 + admin 后台 staging deploy log
f. 在 admin 后台点"重试部署"，验证能再次触发

- [ ] **Step 5: Final commit (如果有 docs 改动)**

```bash
cd /Users/gujiwei/python/superUserAI && git status -sb
# 如果还有 untracked / unstaged 跟本计划相关的，归档；如已干净直接进入 hand-off
```

---

## Self-Review Notes

**Spec coverage:**
- §3.1 repos +4 字段 → Task 2 + Task 3 ✓
- §3.2 dev_tasks +3 字段 → Task 2 + Task 3 ✓
- §3.3 ProjectStatus.STAGED → Task 1 ✓
- §3.4 alembic migration → Task 2 ✓
- §4.1 StagingDeployService → Task 5-10 ✓
- §4.2 webhook 改动 → Task 11 ✓
- §4.3 admin 重试端点 → Task 12 ✓
- §4.4 配置项 → Task 4 ✓
- §5.1 SSH 命令 + target 解析 → Task 5 + Task 7 ✓
- §5.2 超时与失败判定 → Task 7 + Task 8 ✓
- §5.3 并发控制 → Task 9 ✓
- §5.4 进程重启清理 → Task 10 ✓
- §6.1 / §6.2 / §6.3 通知（文本 + notify_creator_targeted）→ Task 7（_notify_success / _notify_failure）✓
- §7 admin 模板改动 → Task 13 ✓
- §8 服务器准备 README → Task 14 ✓
- §11.1 单元测试 → Task 5-10 ✓
- §11.2 端到端测试 → Task 11 ✓
- §11.3 真机验证清单 → Task 15 ✓

**Placeholder scan:** 无 TBD / TODO / "implement later"。
- Task 12 里 `<ADMIN_DEP>` 是占位符 —— 但有明确的 grep 步骤让实施者拿到真实依赖名，可接受。
- Task 13 里 `staging_deploy_log` 模板分支不确定 admin handler 是否已传 `dev_task` —— 有 fallback 提示。

**Type/name consistency:**
- `_parse_ssh_target(target, *, default_user) -> tuple[str, str, Optional[int]]` — Task 5 定义，Task 7 使用同签名 ✓
- `StagingDeployService.__init__(wechat_client, ssh_key_path, ssh_user_default, deploy_timeout_sec, log_tail_lines)` — Task 6 定义，Task 10/11 使用同 kwargs ✓
- `deploy_pr(db, repo, project, dev_task, pr_number, head_sha)` — Task 6 定义，Task 7-12 全部使用同签名 ✓
- `_deploy_pr_inner` — Task 9 引入，Task 10 复用 ✓
- `recover_stale_deploys(stale_after_sec)` — Task 10 定义并用 ✓
- 字段名 `staging_url / staging_ssh_target / staging_deploy_path / staging_compose_file / staging_deploy_status / staging_deployed_at / staging_deploy_log` — 跨 Task 1-13 一致 ✓
- `ProjectStatus.STAGED.value == "staged"` — Task 1 + Task 7 一致 ✓

**Scope:** 单个 spec、单个 plan，15 个 task；最大 task（Task 7、11、13）也都是 5 步内。每个 task 独立可测、可 commit。
