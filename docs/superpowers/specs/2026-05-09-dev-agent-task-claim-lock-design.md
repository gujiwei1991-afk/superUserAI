# Dev-Agent 任务认领锁 + 子进程清理 — 设计方案

**日期：** 2026-05-09
**作者：** Claude (Opus) + 用户协同 brainstorming
**状态：** 待用户最终审阅
**触发事件：** 2026-05-09 19:42-19:54 出现一个 worker (PID 60550) spawn 出 4 个并发 claude 子进程跑同一个 issue #3 的现象，PR #4 提交后 backend 没正确切状态，worker 持续重新 claim → 失控

## 1. 背景与目标

### 1.1 故障复盘

| 故障点 | 表现 | 根因 |
|---|---|---|
| 单 worker 同时跑多个 claude 子进程 | 看到 4 个 `claude -p ... feat/issue-3` 同时存在 | `ClaudeCoder.develop` 异常路径下未 kill+wait 子进程，`proc.kill()` 仅在 readline timeout 分支生效 |
| 同一个 task 被反复处理 | 19:42 / 19:44 / 19:51 / 19:54 四次"开始分析" | `/api/tasks/pending` 仅看 `Project.status==approved`，无认领锁；worker 失败重 poll 又拿到 |
| PR 已创建但状态不切 | GitHub 上 PR #4 存在，DB 里 `github_pr_number=NULL` 且 `status=approved` | `_notify_backend_completed` 路径没成功，但 PR 本身已 push 到 GitHub；下一轮 poll 重 claim |

### 1.2 目标

- **同一个 project 在任何时刻最多只有一个 worker 在处理它**——并发安全。
- **worker 中途 crash 不会让 task 永久卡死**——按时间窗自动回收。
- **`ClaudeCoder.develop` 函数返回时，子进程一定退出**——无论成功/异常路径。
- **不动 `projects` 表**——复用 `dev_tasks` 作为认领记录的天然载体。

### 1.3 核心设计决策（已与用户对齐）

| 决策点 | 选择 |
|---|---|
| 认领记录载体 | 复用 `dev_tasks` 表 + 加 `worker_id` 字段 |
| 并发去重机制 | Partial unique index：同 project 同时只能有一条 active 的 dev_task |
| 超时回收 | 固定 60 分钟（`started_at < now - 60min` 视为孤儿，回收为 failed）|
| 心跳 | 不做（YAGNI，60min 固定阈值已足够）|
| claude 子进程清理 | `develop()` 的 `finally` 强制 `proc.kill()` + `await proc.wait(timeout=5)` |

## 2. 架构总览

```
┌─────────── dev-agent worker ─────────────┐
│  worker_id = "<hostname>-<pid>"          │
│                                          │
│  loop every 30s:                         │
│    claim = POST /api/tasks/claim         │
│            { worker_id }                 │  ← 服务端原子操作
│    if claim: process_task(claim)         │
│      ├ POST /api/dev-tasks/{id}/started  │  ← claimed → in_progress
│      ├ ClaudeCoder.develop()             │  ← finally kill+wait 子进程
│      ├ git push + GitHub PR              │
│      └ POST /api/tasks/{pid}/completed   │  ← 找 active dev_task 更新
└──────────────────────────────────────────┘

┌─────────── backend ──────────────────────┐
│  /api/tasks/claim:                       │
│    BEGIN                                 │
│    1. UPDATE dev_tasks SET status=failed │  ← stale recovery
│       WHERE status IN ('claimed',        │
│         'in_progress')                   │
│       AND started_at < now() - 60 min    │
│                                          │
│    2. SELECT project WHERE               │
│       status='approved'                  │
│       AND NOT EXISTS (select 1 from      │
│         dev_tasks where project_id =     │
│         project.id AND status NOT IN     │
│         ('failed'))                      │
│       LIMIT 1                            │
│                                          │
│    3. INSERT dev_tasks (project_id,      │
│         worker_id, status='claimed',     │
│         started_at=now())                │
│       ← unique index race-fails here?    │
│         IntegrityError → return None     │
│         (try next project next tick)     │
│    COMMIT                                │
└──────────────────────────────────────────┘
```

## 3. 数据模型

### 3.1 `dev_tasks` 表新增字段

```python
class DevTask(Base):
    # ...原有字段...
    worker_id: Mapped[str | None]
```

### 3.2 Partial unique index

```sql
CREATE UNIQUE INDEX idx_dev_tasks_active_per_project
ON dev_tasks (project_id)
WHERE status IN ('claimed', 'in_progress', 'pr_open', 'merged', 'deployed');
```

**为什么是这些 status：** `failed` 和 `acceptance` 不算"active"——同一个 project 失败后可以重新 claim；验收阶段也允许新 task。其余状态都代表"这个 project 当前有活跃的工作记录"，互斥。

### 3.3 `status` 取值新增

`pending` (legacy) → `claimed` (新) → `in_progress` (新) → `pr_open` → `merged` / `deployed` / `failed`

`pending` 字段保留为 default（向后兼容，未来可移除）。

### 3.4 Alembic Migration

单条 migration：alter table 加 `worker_id` 字段 + 创建 partial unique index。

## 4. Backend API 改造

### 4.1 新增 `POST /api/tasks/claim`

**请求：**
```json
{ "worker_id": "<hostname>-<pid>" }
```

**响应（拿到 task）：**
```json
{
  "claimed": true,
  "dev_task_id": 42,
  "project_id": 10,
  "github_owner": "gujiwei1991-afk",
  "github_repo": "oaSys",
  "github_issue_number": 3,
  "title": "..."
}
```

**响应（无可用 task 或 race lost）：**
```json
{ "claimed": false }
```

**实现步骤（一个 transaction 内）：**

1. **Stale recovery**：`UPDATE dev_tasks SET status='failed', summary=summary || '\n[auto-recovered: stale claim > 60min]', finished_at=now() WHERE status IN ('claimed','in_progress') AND started_at < now() - interval '60 minutes'`
2. **Find candidate**：`SELECT projects.* FROM projects WHERE status='approved' AND github_issue_number IS NOT NULL AND NOT EXISTS (select 1 from dev_tasks where project_id=projects.id AND status NOT IN ('failed')) ORDER BY created_at LIMIT 1`
3. **Try insert**：`INSERT INTO dev_tasks (project_id, repo_id, worker_id, status, started_at) VALUES (..., 'claimed', now())`
   - 命中 partial unique index → IntegrityError → catch + commit + 返回 `{claimed: false}`（race lost，下个 tick 再试）
   - 成功 → COMMIT，返回 task 信息

### 4.2 新增 `POST /api/dev-tasks/{dev_task_id}/started`

把 status 从 `claimed` 切到 `in_progress`，标志 worker 真的开始干活（而不是刚拿到任务就 crash）。

```python
@router.post("/dev-tasks/{dev_task_id}/started")
async def mark_started(dev_task_id: int, db: AsyncSession = Depends(get_db)):
    task = await db.get(DevTask, dev_task_id)
    if task is None:
        raise HTTPException(404, "dev task not found")
    if task.status == "claimed":
        task.status = "in_progress"
        await db.commit()
    return {"status": task.status}
```

### 4.3 修改 `POST /api/tasks/{project_id}/completed`

**当前行为：** 直接 INSERT 一条新 dev_task（这就是为什么数据库里会有重复行）。

**改造后：** 找到该 project 当前 active 的 dev_task（status in `claimed`/`in_progress`），UPDATE 它而不是 INSERT。如果找不到（异常情况），fallback 到 INSERT 一条 + 记 warning log。

```python
stmt = select(DevTask).where(
    DevTask.project_id == project_id,
    DevTask.status.in_(["claimed", "in_progress"]),
).order_by(DevTask.id.desc()).limit(1)
active = (await db.execute(stmt)).scalar_one_or_none()
if active is not None:
    active.status = "pr_open"
    active.pr_number = payload.pr_number
    active.branch = payload.branch
    active.summary = payload.summary
    active.finished_at = datetime.now(timezone.utc)
else:
    logger.warning("complete_task: no active dev_task for project=%s, inserting fallback row", project_id)
    db.add(DevTask(...))  # 旧行为兜底
project.github_pr_number = payload.pr_number
project.status = ProjectStatus.DEVELOPING.value
await db.commit()
```

### 4.4 修改 `POST /api/tasks/{project_id}/failed`

类似 4.3——UPDATE 当前 active dev_task 的 status='failed'，不再 INSERT 新行。

### 4.5 `GET /api/tasks/pending` 退役

不再被 worker 调用。保留为只读 endpoint（admin 后台诊断用），但在文档里标注 deprecated。

## 5. dev-agent worker 改造

### 5.1 文件结构

```
dev-agent/app/
├── worker.py           # 修：poll → claim
└── claude_coder.py     # 修：develop() finally 强制 cleanup
```

### 5.2 `worker.py:poll_tasks` → `claim_one_task`

```python
import os
import socket

def _build_worker_id() -> str:
    return f"{socket.gethostname()}-{os.getpid()}"


class Worker:
    def __init__(self) -> None:
        # ...
        self.worker_id = _build_worker_id()
        logger.info("worker started worker_id=%s", self.worker_id)

    async def claim_one_task(self) -> dict[str, Any] | None:
        response = await self.backend_client.post(
            "/api/tasks/claim",
            json={"worker_id": self.worker_id},
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("claimed"):
            return None
        return payload

    async def mark_started(self, dev_task_id: int) -> None:
        try:
            await self.backend_client.post(f"/api/dev-tasks/{dev_task_id}/started")
        except Exception:
            logger.exception("mark_started failed for dev_task_id=%s", dev_task_id)
```

### 5.3 `worker.run` 主循环

```python
async def run(self, interval: int = 30) -> None:
    try:
        while True:
            try:
                claim = await self.claim_one_task()
                if claim is not None:
                    try:
                        await self.process_task(claim)
                    except Exception as exc:
                        logger.exception("Failed to process task: %s", claim)
                        project_id = claim.get("project_id")
                        if isinstance(project_id, int):
                            await self._notify_backend_failed(project_id, str(exc))
            except Exception:
                logger.exception("Failed to claim task")
            await asyncio.sleep(interval)
    finally:
        await self.aclose()
```

每个 tick 至多 claim 一条；处理完才进下一轮。

### 5.4 `process_task` 加 mark_started

```python
async def process_task(self, task: dict[str, Any]) -> None:
    dev_task_id = int(task["dev_task_id"])
    project_id = int(task["project_id"])
    # ...
    await self.mark_started(dev_task_id)
    # rest unchanged
```

### 5.5 `ClaudeCoder.develop` 强制 cleanup

```python
async def develop(self, prompt, repo_path, on_milestone=None) -> ClaudeRunResult:
    # ...
    proc = await asyncio.create_subprocess_exec(...)
    stderr_task = asyncio.create_task(drain_stderr())
    try:
        # main streaming loop (existing)
        ...
        await proc.wait()
    finally:
        # === NEW: hard kill + wait, no matter how we exit ===
        if proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("claude subprocess did not exit within 5s after kill; PID=%s", proc.pid)
        # === existing stderr task cancel ===
        stderr_task.cancel()
        try:
            await stderr_task
        except (asyncio.CancelledError, Exception):
            pass
    # ...
```

**为什么必须 kill+wait：** 如果 readline timeout 之外的异常（如 backend HTTP 失败、IO 错误）发生在主循环里，原代码不 kill 子进程；子进程会继续跑 + 占资源 + 把 git push 等做完——但 worker 已经异常退出且不在等结果了，造成"幽灵 PR"。

## 6. 错误处理与边界

| 场景 | 策略 |
|---|---|
| 多个 worker 同时调 `/claim` 看上同一个 project | 一个 INSERT 成功（unique index），其他 IntegrityError → 返回 `{claimed: false}` → worker 下个 tick 拿别的 project |
| Worker crash 后 dev_task 卡在 `claimed`/`in_progress` | 60 分钟后下次 `/claim` 时被 stale recovery mark='failed'，project 重新可被 claim |
| `_notify_backend_completed` 失败但 PR 已 push | dev_task 仍是 `in_progress`，60 分钟后 stale recovery → mark='failed'，project 状态仍是 `approved`，下一轮被 claim 重新跑——**这次不会撞 branch 名**，因为 git_ops.create_branch 应当 idempotent（已有则 reset 到 base） |
| Branch 已存在 (`feat/issue-N`)（重启场景）| `GitOps.create_branch` 行为依赖现有实现——本期不改，假设它能 reset。如果实测仍有冲突，单独修。 |
| `/dev-tasks/{id}/started` 接收时 status 已经不是 `claimed`（比如已被 stale recovery） | 不报错，no-op，return current status |
| Project 已 `developing`/`completed`，worker 误以为还要做 | 不可能——`/claim` 的 SELECT 已经 filter `status='approved'` |
| `process_task` 内部抛异常但 `_notify_backend_failed` 也失败 | dev_task 仍是 `in_progress` → 60min 后被 stale recovery 兜底；至少不会无限重 claim |
| Worker_id 冲突（两个机器同 hostname/pid 重启）| 不影响——锁在 partial unique index 上，worker_id 仅为审计字段 |

## 7. 测试策略

| 测试 | 覆盖 |
|---|---|
| `tests/e2e_task_claim_lock.py`（新）| `/claim` happy path、并发场景两个 worker 同时 claim 只有一个拿到、stale recovery 60min 之后能重新 claim、completed 路径 UPDATE 现有 dev_task 而非 INSERT 新行、failed 同理 |
| `tests/e2e_review_command.py`（已有）| 回归：审核流程不受影响 |
| dev-agent 端：手动重启 worker 后用 `oneshot.py` 验证一条端到端 | 手动 e2e |

## 8. 范围（YAGNI）

### 8.1 本期包含

- migration + worker_id 字段 + partial unique index
- `/api/tasks/claim` 新 endpoint + stale recovery
- `/api/dev-tasks/{id}/started` 新 endpoint
- `/api/tasks/{project_id}/completed` 改 INSERT → UPDATE
- `/api/tasks/{project_id}/failed` 改 INSERT → UPDATE
- worker.py：poll → claim + mark_started
- claude_coder.py：finally kill + wait
- 单元 + 集成测试

### 8.2 本期不做

- worker 心跳机制（5min 短超时）—— 60min 固定阈值已足够
- admin 后台显示"谁在 claim 哪条 task"—— 字段写入了，UI 可后续加
- `acceptance` 状态后允许多个 dev_task —— partial index 排除了，再加需求时再考虑
- worker 优雅退出（SIGTERM 主动释放当前 claim）—— 60min 兜底足够

## 9. 配置项新增

无新增（worker_id 自动生成，超时阈值 hardcode 60 min）。如果生产想调，未来再加 `dev_task_stale_minutes` config。

## 10. 风险评估

| 风险 | 影响 | 缓解 |
|---|---|---|
| Stale recovery 把"还在跑但慢"的 worker 误判 | 中 | 60 分钟阈值足够宽（claude_cli 一般 5-15 min）；超时后即使重 claim，也只是多跑一次，结果幂等 |
| Partial unique index 在 PostgreSQL 之外的 DB 不支持 | 低 | 我们只跑 PostgreSQL（asyncpg）|
| `develop()` finally 里 await proc.wait() 卡住 | 低 | 用 wait_for(5s) 包住，超时也能继续往外走 |
| Existing failed dev_tasks 数量增多 | 低 | failed 行有审计价值，不清理；admin 后台可加 filter |
| Worker_id 长度 / 字符冲突 | 低 | hostname-pid 是 ASCII 安全字符；DB 列设 nullable str 即可 |
