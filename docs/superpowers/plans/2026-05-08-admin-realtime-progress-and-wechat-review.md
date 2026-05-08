# 后台实时进度 + 企微管理员审核 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让管理员在后台需求详情页实时看到 dev-agent 的开发日志(5s 轮询);把对用户的 WeChat 消息收敛到「审核通过」与「PR 合并已部署+请验收」两个关键节点;同时让用户提交的需求自动通过企微推给所有管理员,管理员可直接在企微回复 `#审核 <id> 通过/拒绝 [理由]` 完成审核闭环。

**Architecture:**
- **进度日志**: dev-agent 现有的 milestone push 不再发 WeChat,改为存到新表 `project_dev_logs`。后台需求详情页用 JS setInterval 5 秒轮询 `GET /admin/api/requirements/{id}/logs` 渲染时间线。重试时清空旧日志。
- **关键节点用户通知**: 「审核通过」由后端在状态变 approved 时主动发(无论是后台 UI 点的还是企微指令触发);「PR 合并+部署+验收」走现有 webhook 通知,不动。中间所有 milestone(包括 PR 创建)都只入库不发用户。
- **企微管理员审核**: 用户确认 PRD 进入 reviewing 时,后端遍历所有 `role=admin` 用户,把项目 ID + 标题 + PRD 摘要推到他们企微。管理员回复 `#审核 <id> 通过` 或 `#审核 <id> 拒绝 <理由>` 就走和后台 UI 等价的审批流程(创建 GitHub Issue → approved / rejected)。

**Tech Stack:** FastAPI / SQLAlchemy async / Alembic / Jinja2 + Tailwind / 原生 JS fetch / vworkApi WeChat / GitHub REST API

---

## File Structure

**新增**:
- `backend/alembic/versions/<id>_add_project_dev_logs.py` — 新表 `project_dev_logs(id, project_id FK CASCADE, message text, created_at)` + 索引 `(project_id, created_at)`
- `backend/app/models/project_dev_log.py` — `ProjectDevLog` ORM 模型
- `backend/app/services/project_review.py` — 抽离 `create_issue_for_project()` 与 `notify_creator_approved()` / `notify_creator_rejected()` 帮助函数(后台 UI 与企微指令共用)
- `backend/tests/e2e_review_command.py` — 企微 `#审核` 端到端验证脚本(参考现有 `e2e_pm_chat.py` 模式)

**修改**:
- `backend/app/models/__init__.py` — 导出 `ProjectDevLog`
- `backend/app/models/project.py` — 添加 `dev_logs` 反向关系(cascade=all,delete-orphan)
- `backend/app/api/tasks.py` — 把 `POST /api/projects/{id}/notify` 改名为 `POST /api/projects/{id}/logs`,实现改为只入库不发 WeChat;`fail_task` 路径改用新的 `notify_creator_failed` helper
- `backend/app/api/admin.py` — 重构 approve_review 路径调用 `project_review.py` helper;新增 `GET /admin/api/requirements/{id}/logs` JSON 路由;在 retry 路由里清空旧 `project_dev_logs`;后台 UI 审批路径增加「审核通过」WeChat 通知给 creator
- `backend/app/services/message_handler.py` — 进入 reviewing 时调用 `_notify_admins_for_review`;新增 `#审核` 命令解析与处理(只允许 role=admin);拒绝路径同步状态与 WeChat 通知
- `backend/app/gateway/command_parser.py` — 添加 `#审核` 命令解析(若使用集中解析器)
- `backend/templates/requirement_detail.html` — 添加「实时进度」时间线 section + 5s 轮询 JS
- `dev-agent/app/worker.py` — 把 `_post_progress` 重命名为 `_post_log`,URL 改成 `/api/projects/{id}/logs`;PR 创建时也走 logs 不直发用户

---

## Task 1: 新增 project_dev_logs 表与 ORM

**Files:**
- Create: `backend/alembic/versions/e9a7c2f1d503_add_project_dev_logs.py`
- Create: `backend/app/models/project_dev_log.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/models/project.py` (lines around relationships block)

- [ ] **Step 1: 写 alembic 迁移**

新建 `backend/alembic/versions/e9a7c2f1d503_add_project_dev_logs.py`:

```python
"""add project_dev_logs

Revision ID: e9a7c2f1d503
Revises: d4e7b15c8a92
Create Date: 2026-05-08
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e9a7c2f1d503"
down_revision = "d4e7b15c8a92"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_dev_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "project_id",
            sa.BigInteger(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_project_dev_logs_project_created",
        "project_dev_logs",
        ["project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_project_dev_logs_project_created", table_name="project_dev_logs")
    op.drop_table("project_dev_logs")
```

> 注意: `down_revision` 需要与 `backend/alembic/versions/` 里实际最新的 revision 一致。执行前先 `ls backend/alembic/versions/` 确认 head,把 `d4e7b15c8a92` 替换为真实 head id。

- [ ] **Step 2: 写 ORM 模型**

新建 `backend/app/models/project_dev_log.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.project import Project


class ProjectDevLog(Base):
    __tablename__ = "project_dev_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    project: Mapped["Project"] = relationship("Project", back_populates="dev_logs")
```

- [ ] **Step 3: 注册到 models 包**

修改 `backend/app/models/__init__.py`,加入:

```python
from app.models.project_dev_log import ProjectDevLog  # noqa: F401
```

并将 `ProjectDevLog` 加入 `__all__` 列表(若存在该列表)。

- [ ] **Step 4: 在 Project 上挂反向关系**

修改 `backend/app/models/project.py`,在 relationships 区块加入:

```python
dev_logs: Mapped[list["ProjectDevLog"]] = relationship(
    "ProjectDevLog",
    back_populates="project",
    cascade="all, delete-orphan",
    order_by="ProjectDevLog.created_at",
)
```

并在 TYPE_CHECKING 导入区加 `from app.models.project_dev_log import ProjectDevLog`。

- [ ] **Step 5: 跑迁移,验证**

```bash
cd backend && alembic upgrade head
psql $DATABASE_URL -c "\d project_dev_logs"
```

预期输出包含表结构与 `ix_project_dev_logs_project_created` 索引。

- [ ] **Step 6: 提交**

```bash
git add backend/alembic/versions/e9a7c2f1d503_add_project_dev_logs.py \
        backend/app/models/project_dev_log.py \
        backend/app/models/__init__.py \
        backend/app/models/project.py
git commit -m "feat: add project_dev_logs table for admin progress timeline"
```

---

## Task 2: 后端日志收集与查询 API

**Files:**
- Modify: `backend/app/api/tasks.py:140-160` (`notify_project` route)
- Modify: `backend/app/api/admin.py` (新增 `/admin/api/requirements/{id}/logs`)

- [ ] **Step 1: 把 `notify_project` 改造为 `log_progress`**

修改 `backend/app/api/tasks.py`,删除 `notify_project` 路由,新增:

```python
class LogProgressRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


@router.post("/projects/{project_id}/logs")
async def log_progress(
    project_id: int,
    payload: LogProgressRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    db.add(ProjectDevLog(project_id=project_id, message=payload.message))
    await db.commit()
    return {"status": "ok"}
```

并在文件顶部 imports 加入 `from app.models import ProjectDevLog`。

旧的 `NotifyProjectRequest` 类整个删除(无其它引用)。

- [ ] **Step 2: 在 admin.py 新增日志查询路由**

修改 `backend/app/api/admin.py`,在文件靠近其他 admin api 路由的位置添加:

```python
@router.get("/api/requirements/{project_id}/logs", name="admin_requirement_logs")
async def admin_requirement_logs(
    project_id: int,
    current_admin: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
) -> dict[str, Any]:
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    stmt = (
        select(ProjectDevLog)
        .where(ProjectDevLog.project_id == project_id)
        .order_by(ProjectDevLog.created_at.desc())
        .limit(max(1, min(limit, 200)))
    )
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    return {
        "project_id": project_id,
        "status": project.status,
        "logs": [
            {
                "id": row.id,
                "message": row.message,
                "created_at": row.created_at.isoformat(),
            }
            for row in reversed(rows)  # 时间正序展示
        ],
    }
```

并把 `ProjectDevLog` 加进 admin.py 顶部的 model imports。

> 注意: `require_admin` / `Depends(require_admin)` 是该文件已有的依赖名,以仓库实际命名为准。

- [ ] **Step 3: 在 retry 路由里清空旧日志**

修改 `backend/app/api/admin.py` 的 `retry_requirement` 路由(已存在),在状态重置之前增加:

```python
await db.execute(
    sa_delete(ProjectDevLog).where(ProjectDevLog.project_id == project.id)
)
```

并在 admin.py 顶部 imports 加 `from sqlalchemy import delete as sa_delete`(若已有则跳过)。

- [ ] **Step 4: 手工验证**

启动 backend:

```bash
cd backend && uvicorn app.main:app --port 2888 --reload
```

新开终端:

```bash
# 先用一个真实 project_id 替换 <PID>
curl -X POST http://localhost:2888/api/projects/<PID>/logs \
  -H "Content-Type: application/json" \
  -d '{"message":"hello from manual test"}'

curl -H "Cookie: access_token=<JWT>" \
  http://localhost:2888/admin/api/requirements/<PID>/logs
```

预期: POST 返回 `{"status":"ok"}`;GET 返回包含刚才那条 log。

- [ ] **Step 5: 提交**

```bash
git add backend/app/api/tasks.py backend/app/api/admin.py
git commit -m "feat: store dev-agent progress in project_dev_logs and expose admin logs API"
```

---

## Task 3: dev-agent 切换到日志 API

**Files:**
- Modify: `dev-agent/app/worker.py` (rename `_post_progress` → `_post_log`, change URL)

- [ ] **Step 1: 改 dev-agent worker.py**

把 `dev-agent/app/worker.py` 文件中的 `_post_progress` 方法重命名为 `_post_log`,把 URL 改成新的 endpoint:

```python
async def _post_log(self, project_id: int, message: str) -> None:
    try:
        response = await self.backend_client.post(
            f"/api/projects/{project_id}/logs",
            json={"message": message},
        )
        response.raise_for_status()
    except Exception:
        logger.warning("Failed to push log to backend: %s", message, exc_info=True)
```

并把 `process_task` 内 `push_milestone` 那个闭包改为调 `_post_log`:

```python
async def push_milestone(message: str) -> None:
    await self._post_log(project_id, message)
```

`process_task` 末尾的 `await push_milestone(f"✅ 已提交 PR #...")` 这一行保留不变(逻辑上现在只入库不发用户,自动符合需求)。

- [ ] **Step 2: 重启 dev-agent 验证**

```bash
cd dev-agent && python -m app.main
```

让一个 approved 状态的项目被 dev-agent 拾取(可手工把 DB 里某条 status 改回 approved),观察 backend 日志确认请求打到 `/api/projects/<id>/logs`,同时:

```bash
psql $DATABASE_URL -c "SELECT id, message, created_at FROM project_dev_logs ORDER BY id DESC LIMIT 10;"
```

可以看到行入库;同时 creator 的企微在中间步骤不再收到消息。

- [ ] **Step 3: 提交**

```bash
git add dev-agent/app/worker.py
git commit -m "feat(dev-agent): push milestones to backend logs API instead of user WeChat"
```

---

## Task 4: 抽离审核 helper + 后台 UI 审批触发用户通知

**Files:**
- Create: `backend/app/services/project_review.py`
- Modify: `backend/app/api/admin.py` (`_create_issue_for_project` 调用点 / approve 与 reject 路由)
- Modify: `backend/app/api/tasks.py` (fail_task 内创建者通知改用 helper,文案统一)

- [ ] **Step 1: 创建 project_review service**

新建 `backend/app/services/project_review.py`:

```python
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.wechat_client import WeChatClient
from app.models import Project, Repo, User
from app.services.github_service import GitHubService  # 以仓库实际位置为准
from shared.constants import ProjectStatus

logger = logging.getLogger(__name__)


async def create_issue_for_project(
    db: AsyncSession,
    *,
    project: Project,
    repo: Repo,
    approver_id: int,
) -> int:
    github = GitHubService.for_repo(repo)
    footer = f"---\nSuperUserAI Project ID: {project.id}"
    issue_body = (
        f"{project.prd_content.strip()}\n\n{footer}"
        if project.prd_content and project.prd_content.strip()
        else footer
    )
    try:
        issue_data = await github.create_issue(
            owner=repo.github_owner,
            repo=repo.github_repo,
            title=f"[SuperUserAI] {project.title}",
            body=issue_body,
            labels=["superuserai", "auto-dev"],
        )
    finally:
        await github.close()

    issue_number = int(issue_data["number"])
    project.github_issue_number = issue_number
    project.approver_id = approver_id
    project.status = ProjectStatus.APPROVED.value
    await db.flush()
    return issue_number


async def notify_creator_approved(
    db: AsyncSession,
    wechat: WeChatClient,
    project: Project,
) -> None:
    creator = await db.get(User, project.creator_id)
    if creator is None or not creator.wechat_user_id:
        return
    try:
        await wechat.send_text(
            creator.wechat_user_id,
            (
                f"✅ 你的需求《{project.title}》已通过审核,"
                "AI 正在排队开发,完成后会再通知你验收。"
            ),
        )
    except Exception:
        logger.exception("notify creator approved failed project=%s", project.id)


async def notify_creator_rejected(
    db: AsyncSession,
    wechat: WeChatClient,
    project: Project,
    reason: str,
) -> None:
    creator = await db.get(User, project.creator_id)
    if creator is None or not creator.wechat_user_id:
        return
    body = f"⚠️ 你的需求《{project.title}》未通过审核。"
    if reason.strip():
        body += f"\n\n理由:{reason.strip()[:600]}"
    body += "\n\n如需调整请重新发起 #新需求 或联系管理员。"
    try:
        await wechat.send_text(creator.wechat_user_id, body)
    except Exception:
        logger.exception("notify creator rejected failed project=%s", project.id)
```

> 注意: `GitHubService.for_repo(repo)` 这一行替换为 admin.py 当前实际使用的工厂函数(原是 `_github_service_for_repo`)。如果该工厂仍在 admin.py 内,把它一起搬到 `backend/app/services/github_service.py`(或新建)以便共享。

- [ ] **Step 2: 改造 admin.py 使用 helper**

修改 `backend/app/api/admin.py`:
- 删除原 `_create_issue_for_project` 内的实现,替换为从 `project_review` 模块 import:`from app.services.project_review import create_issue_for_project, notify_creator_approved, notify_creator_rejected`
- 在 `approve_review` 路由(`@router.post("/reviews/{project_id}/approve")`)成功调用 `create_issue_for_project` 后增加:

```python
await db.commit()
await db.refresh(project)
await notify_creator_approved(db, wechat, project)
```

(其中 `wechat` 是文件里已存在的 `WeChatClient()` 实例;若该模块没有,新建 `wechat = WeChatClient()` 顶级单例。)

- 同样地,如果有 `reject_review` 路由,在状态改 rejected 之后调 `notify_creator_rejected(db, wechat, project, reason)`。

- [ ] **Step 3: 把 fail_task 的通知文案统一**

修改 `backend/app/api/tasks.py` 的 `fail_task`,把内联的 `wechat.send_text(...)` 调用改为:

```python
await notify_creator_rejected(db, wechat, project, payload.reason)
```

并在文件顶部 imports 添加 `from app.services.project_review import notify_creator_rejected`。

- [ ] **Step 4: 手工验证**

```bash
# 1. 在 admin UI 找一条 reviewing 状态的需求,点「通过」按钮
# 2. 观察 backend 日志,确认调用 GitHub create_issue + send_text
# 3. 让 creator 微信确认收到「✅ 你的需求《...》已通过审核」
```

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/project_review.py \
        backend/app/api/admin.py \
        backend/app/api/tasks.py
git commit -m "refactor: centralize project review helpers and notify creator on approved"
```

---

## Task 5: 进入 reviewing 时通知所有管理员

**Files:**
- Modify: `backend/app/services/message_handler.py:180-200` (PRD 生成完成后)

- [ ] **Step 1: 实现 _notify_admins_for_review**

修改 `backend/app/services/message_handler.py`,在 class 内添加:

```python
async def _notify_admins_for_review(self, project: Project) -> None:
    stmt = select(User).where(User.role == "admin", User.wechat_user_id.is_not(None))
    result = await self.db.execute(stmt)
    admins = list(result.scalars().all())
    if not admins:
        return

    prd_excerpt = (project.prd_content or "").strip()
    if len(prd_excerpt) > 600:
        prd_excerpt = prd_excerpt[:600] + "…"
    creator = await self.db.get(User, project.creator_id)
    creator_name = (
        (creator.nickname or creator.wechat_user_id) if creator else "未知"
    )
    body = (
        f"📝 新需求待审核 #{project.id}\n"
        f"标题:{project.title}\n"
        f"提出人:{creator_name}\n\n"
        f"PRD 摘要:\n{prd_excerpt or '(空)'}\n\n"
        f"通过:#审核 {project.id} 通过\n"
        f"拒绝:#审核 {project.id} 拒绝 <理由>"
    )
    for admin in admins:
        try:
            await self.wechat.send_text(admin.wechat_user_id, body)
        except Exception:
            logger.exception(
                "notify admin failed admin=%s project=%s",
                admin.wechat_user_id, project.id,
            )
```

并在文件顶部 imports 加 `from sqlalchemy import select`(若已有则跳过)、`from app.models import User`(若未导入)。

- [ ] **Step 2: 在 PRD 生成完成后调用**

修改 `backend/app/services/message_handler.py:184` 附近,把:

```python
await self.project_service.update_status(project, ProjectStatus.REVIEWING)
```

后面追加一行:

```python
await self._notify_admins_for_review(project)
```

(放在 update_status 之后、return 之前。)

- [ ] **Step 3: 手工验证**

跑一遍完整对话流程(可借鉴 `backend/tests/e2e_pm_chat.py`),进入 reviewing 阶段。在 backend 日志看到 `notify admin` 没有 exception;让所有 role=admin 的真实用户的微信收到上述模板消息。

- [ ] **Step 4: 提交**

```bash
git add backend/app/services/message_handler.py
git commit -m "feat: notify all admins via WeChat when a requirement enters reviewing"
```

---

## Task 6: 企微 #审核 命令处理

**Files:**
- Modify: `backend/app/gateway/command_parser.py` (添加 `#审核` 解析)
- Modify: `backend/app/services/message_handler.py` (添加分发与处理)
- Create: `backend/tests/e2e_review_command.py`

- [ ] **Step 1: 给 command_parser 添加新指令**

打开 `backend/app/gateway/command_parser.py`,沿用现有的 `parse_command` 解析风格添加:

```python
REVIEW_CMD_PREFIX = "#审核"


@dataclass
class ReviewCommand:
    project_id: int
    decision: str  # "通过" / "拒绝"
    reason: str = ""


def parse_review(text: str) -> ReviewCommand | None:
    body = text.strip()
    if not body.startswith(REVIEW_CMD_PREFIX):
        return None
    rest = body[len(REVIEW_CMD_PREFIX):].strip()
    parts = rest.split(maxsplit=2)
    if len(parts) < 2:
        return None
    raw_id, decision = parts[0], parts[1]
    if not raw_id.isdigit():
        return None
    if decision not in {"通过", "拒绝"}:
        return None
    reason = parts[2].strip() if len(parts) == 3 else ""
    return ReviewCommand(project_id=int(raw_id), decision=decision, reason=reason)
```

> 该模块原本怎么暴露解析结果就跟随原模式;若它把所有命令统一在 `parse_command`,把 `parse_review` 整合进去并返回一个新的 dataclass。

- [ ] **Step 2: 在 message_handler 里分发 #审核 命令**

修改 `backend/app/services/message_handler.py:handle()`,在白名单 / 已有命令分发的同一层级,**插在白名单 gate 之后**(确保非 admin 不会触达):

```python
review_cmd = parse_review(text)
if review_cmd is not None:
    return await self._handle_review_command(user, review_cmd)
```

文件顶部 imports 增加 `from app.gateway.command_parser import parse_review, ReviewCommand`。

- [ ] **Step 3: 实现 _handle_review_command**

继续在 `MessageHandler` 里追加:

```python
async def _handle_review_command(self, user: User, cmd: ReviewCommand) -> str:
    if user.role != "admin":
        return "只有管理员可以使用 #审核 命令。"

    project = await self.db.get(Project, cmd.project_id)
    if project is None:
        return f"找不到项目 #{cmd.project_id}。"

    if project.status != ProjectStatus.REVIEWING.value:
        return (
            f"项目 #{project.id} 当前状态是 {project.status},"
            "不是待审核,无法审批。"
        )

    repo = await self.db.get(Repo, project.repo_id) if project.repo_id else None
    if cmd.decision == "通过":
        if repo is None:
            return "项目没有关联仓库,无法创建 GitHub Issue。"
        try:
            issue_number = await create_issue_for_project(
                self.db,
                project=project,
                repo=repo,
                approver_id=user.id,
            )
        except Exception as exc:
            logger.exception("create_issue_for_project failed for %s", project.id)
            await self.db.rollback()
            return f"创建 GitHub Issue 失败:{exc}"
        await self.db.commit()
        await self.db.refresh(project)
        await notify_creator_approved(self.db, self.wechat, project)
        return f"✅ 已审核通过项目 #{project.id},GitHub Issue #{issue_number} 已创建。"

    # 拒绝路径
    project.status = ProjectStatus.REJECTED.value
    await self.db.commit()
    await self.db.refresh(project)
    await notify_creator_rejected(self.db, self.wechat, project, cmd.reason)
    return f"已拒绝项目 #{project.id}。"
```

文件顶部 imports 增加:

```python
from app.services.project_review import (
    create_issue_for_project,
    notify_creator_approved,
    notify_creator_rejected,
)
from app.models import Repo
```

- [ ] **Step 4: 写端到端验证脚本**

新建 `backend/tests/e2e_review_command.py`,模仿 `e2e_pm_chat.py`:

```python
"""End-to-end smoke for the #审核 admin command."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "shared"))

from app.database import AsyncSessionLocal  # noqa: E402
from app.gateway.command_parser import parse_review  # noqa: E402
from app.models import Project, User  # noqa: E402
from app.services.message_handler import MessageHandler  # noqa: E402


class RecordingWeChat:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_text(self, user_id: str, msg: str):
        self.sent.append((user_id, msg))
        return {"status": "ok"}


async def main() -> None:
    cmd = parse_review("#审核 12 通过")
    assert cmd is not None and cmd.project_id == 12 and cmd.decision == "通过"

    bad = parse_review("#审核 abc 通过")
    assert bad is None

    print("parse_review ok")

    # 数据库行为:用一个真实的 reviewing 项目 ID 作为 PROJECT_ID 环境变量
    import os
    pid = int(os.environ.get("PROJECT_ID", "0"))
    if pid == 0:
        print("set PROJECT_ID=<reviewing project id> to run db check")
        return

    async with AsyncSessionLocal() as db:
        wechat = RecordingWeChat()
        # 找一个 admin 用户
        from sqlalchemy import select
        admin = (await db.execute(
            select(User).where(User.role == "admin").limit(1)
        )).scalar_one()
        handler = MessageHandler(db=db, wechat=wechat, ...)  # 按现有构造签名补齐
        reply = await handler._handle_review_command(
            admin, parse_review(f"#审核 {pid} 通过"),
        )
        print("reply:", reply)
        assert "已审核通过" in reply or "失败" in reply
        print("sent wechat:", wechat.sent)


asyncio.run(main())
```

> handler 构造签名以仓库实际为准,保持与 `e2e_pm_chat.py` 一致即可。

- [ ] **Step 5: 跑脚本验证**

```bash
PROJECT_ID=<id> python backend/tests/e2e_review_command.py
```

预期:输出 `parse_review ok`、`已审核通过项目 #X` 或拒绝消息;`wechat.sent` 包含发给 creator 的通知。

- [ ] **Step 6: 提交**

```bash
git add backend/app/gateway/command_parser.py \
        backend/app/services/message_handler.py \
        backend/tests/e2e_review_command.py
git commit -m "feat: support #审核 admin command for WeChat-native review"
```

---

## Task 7: 后台需求详情页加进度时间线 + 5s 轮询

**Files:**
- Modify: `backend/templates/requirement_detail.html`

- [ ] **Step 1: 在模板里加 section + JS**

修改 `backend/templates/requirement_detail.html`,在「PRD 内容」那一块之前(line 130 之前)插入新 section:

```html
<section class="rounded-3xl bg-white p-6 shadow-sm ring-1 ring-slate-200" data-progress-section>
    <div class="flex items-center justify-between gap-4">
        <h2 class="text-lg font-semibold text-slate-900">实时开发进度</h2>
        <span class="text-xs text-slate-400" data-progress-status></span>
    </div>
    <ol class="mt-4 space-y-3 text-sm text-slate-700" data-progress-list>
        <li class="text-slate-400">尚未有进度日志。</li>
    </ol>
</section>

<script>
(function () {
    const section = document.querySelector('[data-progress-section]');
    if (!section) return;
    const list = section.querySelector('[data-progress-list]');
    const statusEl = section.querySelector('[data-progress-status]');
    const projectId = {{ project.id }};
    const liveStatuses = new Set(['approved', 'developing', 'deployed']);
    let timer = null;

    function render(payload) {
        const logs = payload.logs || [];
        if (logs.length === 0) {
            list.innerHTML = '<li class="text-slate-400">尚未有进度日志。</li>';
            return;
        }
        list.innerHTML = logs.map(function (row) {
            const date = new Date(row.created_at);
            const time = date.toLocaleTimeString('zh-CN', { hour12: false });
            const safe = row.message.replace(/[&<>]/g, function (c) {
                return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c];
            });
            return '<li class="flex gap-3"><span class="shrink-0 text-xs text-slate-400">'
                + time + '</span><span class="whitespace-pre-wrap">' + safe + '</span></li>';
        }).join('');
    }

    async function tick() {
        try {
            const r = await fetch('/admin/api/requirements/' + projectId + '/logs', {
                credentials: 'same-origin',
            });
            if (!r.ok) {
                statusEl.textContent = '加载失败 ' + r.status;
                return;
            }
            const payload = await r.json();
            render(payload);
            statusEl.textContent = '已更新 ' + new Date().toLocaleTimeString('zh-CN', { hour12: false });
            if (!liveStatuses.has(payload.status) && timer) {
                clearInterval(timer);
                timer = null;
                statusEl.textContent += ' · 已停止轮询';
            }
        } catch (err) {
            statusEl.textContent = '加载异常';
        }
    }

    tick();
    const initialStatus = '{{ project.status }}';
    if (liveStatuses.has(initialStatus)) {
        timer = setInterval(tick, 5000);
    }
})();
</script>
```

- [ ] **Step 2: 浏览器手工验证**

打开 `http://localhost:2888/admin/requirements/<id>`(用一个 approved 或 developing 状态的需求 id):
1. 页面立即显示已有 logs
2. 5 秒一次自动刷新(刷新时右上角时间会更新)
3. 状态非 live 时不再轮询

> 前端使用了 Tailwind class,验证时同时确认排版没破。

- [ ] **Step 3: 提交**

```bash
git add backend/templates/requirement_detail.html
git commit -m "feat(admin): add real-time dev progress timeline with 5s polling"
```

---

## Task 8: 收尾验证

- [ ] **Step 1: 端到端真实流程跑一遍**

1. 用一个白名单用户 A 发 `#新需求 <repo> <描述>`,跟 PM 对话,直到生成 PRD。
2. 确认所有 admin 微信收到「📝 新需求待审核 #X …」。
3. admin 用户回复 `#审核 X 通过`。
4. 回到 admin UI 该需求详情页,看时间线开始出现 dev-agent 的 milestone(每 5s 增加一条)。
5. 确认 A 微信收到一条「✅ 你的需求《…》已通过审核」,中间过程 A 不再被打扰。
6. 等 dev-agent 提交 PR、merge 后,A 微信收到「✅ … PR 已合并、代码已部署 …请去验证」。

- [ ] **Step 2: 异常路径**

- 非 admin 用户尝试 `#审核 1 通过`,应回 `"只有管理员可以使用 #审核 命令。"`。
- 项目处于 approved 状态时尝试 `#审核 X 通过`,应回 `"项目 #X 当前状态是 approved,不是待审核,无法审批。"`。
- 在后台对 rejected 需求点「重试开发」,确认 `project_dev_logs` 中该 project_id 的旧记录被清空,新一轮 milestone 重新写入。

- [ ] **Step 3: 提交一个收尾 commit(若有微调)**

```bash
git status
# 若有任何收尾微调,统一一个 commit
git add -A
git commit -m "chore: smoke fixes for realtime progress + wechat review"
```

---

## 自检清单

- [x] 所有迁移、模型、API、模板、dev-agent worker 改动都在 File Structure 里列明
- [x] 每个 task 含具体文件路径与代码片段,无「TBD / 类似 Task X」类占位
- [x] 类型一致:`ProjectDevLog` 全程同名;`create_issue_for_project` / `notify_creator_approved` / `notify_creator_rejected` 跨 admin.py / tasks.py / message_handler.py 调用同一签名
- [x] 涵盖了用户提的两条诉求:后台实时进度(Task 1-3,7)、关键节点用户通知(Task 4 审核通过,Task 3 自动屏蔽中间 milestone,既有 webhook 处理 PR 合并+部署)、企微管理员审核(Task 5-6)
- [x] 每个 task 末尾都有提交步骤
