# 生产环境自动部署 — 实施计划

**对应设计：** `../specs/2026-05-23-production-auto-deploy-design.md`

整体策略：镜像 `feat/staging-auto-deploy` 的实现，最大化复用。任务粒度参考 staging 那条 PR。

---

## Task 1 — Alembic migration + ORM 字段

**文件**
- `backend/alembic/versions/j4d5e6f7a8b9_add_prod_deploy_fields.py` （新增）
- `backend/app/models/repo.py`（追加 5 个 prod_* 字段）
- `backend/app/models/dev_task.py`（追加 4 个 prod_deploy_* 字段）

**字段清单**
- `repos.prod_url / prod_ssh_target / prod_deploy_path / prod_compose_file(默认 docker-compose.prod.yml) / prod_run_migrations(默认 true)`
- `dev_tasks.prod_deploy_status(默认 pending) / prod_deployed_at / prod_deploy_log / prod_deployed_sha`

**验证**：`alembic upgrade head` 走通，ORM 实例可读写新字段。

---

## Task 2 — `ProductionDeployService`

**文件**：`backend/app/services/production_deploy_service.py`（新增）

**核心方法**
- `deploy_merge(db, repo, project, dev_task, merge_sha, pr_number)`：入口
- `_deploy_inner(...)`：构造 SSH 脚本、subprocess 运行、状态机翻转、通知
- `recover_stale_deploys(stale_after_sec=1800)`：启动钩子用

**SSH 远端脚本结构**
```bash
set -euo pipefail
cd <prod_deploy_path>
git fetch origin main
git checkout -f main
git reset --hard <merge_sha>
docker compose -f <prod_compose_file> up -d --build
# 可选（受 repo.prod_run_migrations 控制）
docker compose -f <prod_compose_file> run --rm backend alembic upgrade head
docker compose -f <prod_compose_file> ps
```

**成功路径**
- 写 `dev_task.prod_deploy_status = success`、`prod_deployed_at = now()`、`prod_deployed_sha = merge_sha`
- 翻 `project.status = ProjectStatus.DEPLOYED.value`
- 调 `notify_creator_targeted` 发企微卡片（含 prod_url + PR 号）

**失败路径**
- 状态置 failed，project 状态不动
- 通知 creator 简短摘要 + 后台链接

**复用 staging 模式**
- per-repo `asyncio.Lock`
- `_pending` coalesce（同 repo 后到的合并请求）
- 子进程跑、log tail 200 行

---

## Task 3 — Webhook 接线

**文件**：`backend/app/api/webhooks.py`

**改动**
- 顶部新增 `production_deploy_service = _build_production_service()`，注入配置 + 复用 wechat client
- `_handle_pull_request_event` 签名加 `background_tasks: BackgroundTasks`
- merge 路径取 `merge_commit_sha`，找 repo / dev_task 后 `background_tasks.add_task(production_deploy_service.deploy_merge, ...)`
- `_handle_workflow_run_event` 改成仅记日志，去掉重复 flip
- 清理失效 import：`re`、`notify_creator_targeted`、`ProjectStatus`

---

## Task 4 — 启动钩子 + 配置

**文件**：`backend/app/main.py`、`backend/app/config.py`

- `config.py` 增加 `prod_ssh_key_path / prod_ssh_user_default / prod_deploy_timeout_sec / prod_log_tail_lines`
- `main.py` 的 lifespan 启动时调 `production_deploy_service.recover_stale_deploys()`，吃掉异常

---

## Task 5 — 后台 UI + redeploy 接口

**文件**
- `backend/app/api/admin.py`：`POST /admin/projects/{repo_id}/prod`、`POST /admin/dev-tasks/{id}/redeploy-prod`
- `backend/templates/project_detail.html`：staging 块之后新增「生产部署配置」表单 + 「生产部署状态（最新）」卡片

**redeploy-prod 行为**
- 优先用 `dt.prod_deployed_sha` 作为 sha（重放当前 prod 版本）
- 没有则传 `"FETCH_HEAD"`，由远端 `git fetch origin main` 后 reset 解析

---

## Task 6 — 单元测试 + 文档

**文件**
- `backend/tests/test_production_deploy_service.py`（新增）
- `docs/superpowers/specs/2026-05-23-production-auto-deploy-design.md`（已写）
- `docs/superpowers/plans/2026-05-23-production-auto-deploy.md`（本文件）

**单元测试覆盖**（mock SSH 子进程 + notify）
- `_parse_ssh_target` 基本用例
- skip：缺 prod_url
- success：状态→deployed、sha 记录、通知发出
- alembic：on/off 两种分支
- nonzero exit：状态→failed、project 不翻
- timeout：kill + 状态→failed
- bad ssh target：状态→failed + 通知

---

## 完成定义

- 单元测试全绿（10 个 case）
- 语法/import 全部 `python -m py_compile` 通过
- 后台手动操作流程跑通：填写 prod 配置 → 通过 mock PR webhook 验证一遍 flow
- spec / plan 文档落地

---

## 不在本期 scope

- 自动回滚
- 蓝绿/灰度
- 多生产环境
- DB 备份
- 部署审批流
