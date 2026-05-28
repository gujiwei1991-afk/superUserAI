# 生产环境自动部署 — 设计方案

**日期：** 2026-05-23
**作者：** Claude (Opus) + 用户协同 brainstorming
**状态：** 已与用户对齐 5 项关键决策（不同服务器 / 自动触发 / docker-compose.prod.yml / 部署脚本跑 alembic / 仅记录 sha 不实现回滚）

---

## 1. 背景与目标

### 1.1 现状

`feat/staging-auto-deploy` 落地后，PR opened/synchronize 会被自动部署到 staging 服务器，客户能在企微点开链接看效果。但 PR 合并到 main 后只是把 `project.status` flip 成 `DEPLOYED`、发一条文字通知，**并没有任何真正的生产部署动作**。等价于：

- 用户在企微看到「已部署」，但生产环境上的代码其实是上次手动 `docker compose pull && up` 时留下的旧版本
- 自动化链路在 merge 这一步断了

### 1.2 目标

- PR 合并到 main → backend 自动 SSH 到 **生产服务器**，跑 `docker compose -f docker-compose.prod.yml up -d --build`，把 main 的最新代码部署上去
- 默认在部署脚本末尾跑一次 `alembic upgrade head`（仓库级开关）
- 部署成功 → 翻 `project.status -> DEPLOYED`、给 creator 发企微通知，附生产 URL
- 部署失败 → 状态保持 `STAGED` 不翻，发失败摘要 + 后台链接
- 后台保留「手动重新部署生产」按钮（参照 staging 的 redeploy）
- 不实现回滚，仅在 `dev_tasks.prod_deployed_sha` 字段记录本次部署的 sha，供后台显示

### 1.3 核心设计决策（已与用户对齐）

| 决策点 | 选择 | 理由 |
|---|---|---|
| 生产服务器与 staging 关系 | **不同服务器** | 生产不应和测试共享主机；Repo 表新增 `prod_*` 字段，SSH key 可单独配置（未配则复用 staging key） |
| 触发模式 | **PR 合并即自动部署** | 和 staging 一致的体验；后台保留「重新部署」按钮，不引入"管理员审批"步骤 |
| Compose 文件 | **`docker-compose.prod.yml`** | 与 staging 的 compose 文件物理分离；`Repo.prod_compose_file` 可自定义 |
| 数据库迁移 | **部署脚本跑 `alembic upgrade head`** | 在 backend 容器内跑，避免出现"代码 vs schema"漂移；`Repo.prod_run_migrations` 可关闭 |
| 回滚 | **仅记录 `prod_deployed_sha`，不实现自动回滚** | YAGNI，复杂度大且使用频率低 |

---

## 2. 架构

整体复用 `StagingDeployService` 的所有模式（per-repo asyncio.Lock、coalesce、startup recovery、SSH 子进程驱动 docker compose），只在以下 3 点上做差异化：

| 维度 | StagingDeployService | ProductionDeployService |
|---|---|---|
| 触发事件 | PR opened/synchronize/reopened | PR closed + merged=true |
| 拉代码方式 | `git fetch origin pull/{n}/head:pr-{n}` → `git reset --hard <head_sha>` | `git fetch origin main` → `git reset --hard <merge_commit_sha>` |
| 迁移步骤 | 无 | 可选 `docker compose run --rm backend alembic upgrade head` |
| 成功后状态 | `ProjectStatus.STAGED` | `ProjectStatus.DEPLOYED` |
| 成功后写字段 | `staging_deployed_at` | `prod_deployed_at` + `prod_deployed_sha` |
| 默认超时 | 600s | 1200s（生产 build 通常更重） |

### 2.1 数据模型变更

**Alembic migration `j4d5e6f7a8b9_add_prod_deploy_fields.py`**

```sql
ALTER TABLE repos ADD COLUMN prod_url TEXT;
ALTER TABLE repos ADD COLUMN prod_ssh_target VARCHAR(255);
ALTER TABLE repos ADD COLUMN prod_deploy_path TEXT;
ALTER TABLE repos ADD COLUMN prod_compose_file VARCHAR(255) NOT NULL DEFAULT 'docker-compose.prod.yml';
ALTER TABLE repos ADD COLUMN prod_run_migrations BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE dev_tasks ADD COLUMN prod_deploy_status VARCHAR(32) NOT NULL DEFAULT 'pending';
ALTER TABLE dev_tasks ADD COLUMN prod_deployed_at TIMESTAMP;
ALTER TABLE dev_tasks ADD COLUMN prod_deploy_log TEXT;
ALTER TABLE dev_tasks ADD COLUMN prod_deployed_sha VARCHAR(40);
```

### 2.2 配置项

`backend/app/config.py` 新增：

| 字段 | 默认值 | 说明 |
|---|---|---|
| `prod_ssh_key_path` | `""` | 留空时回退到 `staging_ssh_key_path` |
| `prod_ssh_user_default` | `"deploy"` | SSH 用户兜底 |
| `prod_deploy_timeout_sec` | `1200` | 比 staging 长 |
| `prod_log_tail_lines` | `200` | 日志保留行数 |

### 2.3 Webhook 接线

`_handle_pull_request_event(payload, db, background_tasks)`：

1. 校验 `action == "closed" and merged == True`
2. 取 `pull_request.merge_commit_sha`（fallback：`head.sha`）
3. 用 `pr_number` 找 project，再 fetch 它的 repo + 最近的 dev_task
4. `background_tasks.add_task(production_deploy_service.deploy_merge, db, repo, project, dev_task, merge_sha, pr_number)`

同时清空 `_handle_workflow_run_event` 里原本「flip DEPLOYED」的代码（避免双触发），只保留日志。

### 2.4 后台 UI

- `project_detail.html`：新增「生产部署配置」表单 + 「生产部署状态（最新）」卡片
- `admin.py`：`POST /admin/projects/{repo_id}/prod`、`POST /admin/dev-tasks/{id}/redeploy-prod`

### 2.5 启动时 stale recovery

`main.py` 的 lifespan 启动时按顺序调：
1. `staging_deploy_service.recover_stale_deploys()`（已有）
2. `production_deploy_service.recover_stale_deploys(stale_after_sec=1800)`（新增）

---

## 3. 故意不做的事

| 项 | 不做的理由 |
|---|---|
| 自动回滚 | 复杂度高、使用频次低；仅记录 `prod_deployed_sha` |
| 蓝绿/灰度 | 单台生产机部署不适用；后续若多节点再设计 |
| 部署到多个生产环境 | 同样 YAGNI |
| 部署前人工审批 | 与「PR 合并即部署」决策冲突 |
| 备份数据库 | 由运维侧 cron 单独负责 |

---

## 4. 风险

| 风险 | 缓解 |
|---|---|
| `docker compose run --rm backend alembic ...` 假设 compose 里有 `backend` service | 在 README 里说明该约定；用户可关掉 `prod_run_migrations` |
| 长时间 build 撞超时 | `prod_deploy_timeout_sec` 默认 1200s，repo 级可调（未做，列入 v2） |
| merge_commit_sha 在 GitHub webhook 上有时为 null（极少见） | fallback 到 `head.sha`；都没有则直接 skip 并 log |
| 并发多 PR merge | per-repo `asyncio.Lock` + coalesce 复用 staging 模式 |

---

## 5. 验收标准

- [ ] PR opened/synchronize/reopened 仍走 staging，未受影响
- [ ] PR closed+merged 触发 prod deploy，dev_task.prod_deploy_status 走 deploying→success
- [ ] 部署成功后 project.status == DEPLOYED 且 prod_deployed_sha 与 merge_commit_sha 一致
- [ ] 失败/超时分支不翻状态，企微通知发出
- [ ] 缺 prod 配置字段 → 静默 skip，dev_task.prod_deploy_status = skipped
- [ ] 启动时 stale deploying 任务被 recover 为 failed
- [ ] 后台「生产配置」表单可保存、「重新部署生产」按钮工作
- [ ] 单元测试 `test_production_deploy_service.py` 全绿（10 个 case）
