# 运维 Runbook

日常巡检、监控、故障处理。部署见 [deployment.md](./deployment.md)，变量见 [env-reference.md](./env-reference.md)。

---

## 1. 健康检查与监控

| 端点 | 用途 | 期望 |
|---|---|---|
| `GET /health` | 存活探针（liveness），不查依赖 | `{"status":"ok"}` |
| `GET /healthz` | 就绪探针（readiness），查数据库连通 | 200 + `{"status":"ok","checks":{"database":"ok"}}`；DB 挂时 503 |
| `GET /metrics` | Prometheus 文本指标 | 见下 |

```bash
curl -s localhost:8000/healthz
curl -s localhost:8000/metrics
```

`/metrics` 暴露的关键序列：
- `superuserai_projects{status="..."}` — 各状态项目数（drafting/reviewing/approved/developing/staged/deployed/acceptance/completed/rejected）
- `superuserai_prod_deploys{status="..."}` — dev_tasks 按生产部署状态（pending/deploying/success/failed/skipped）
- `superuserai_staging_deploys{status="..."}` — 同上，staging
- `superuserai_build_info{version="..."}` — 版本

接 Prometheus：抓 `/metrics` 即可。可对 `superuserai_prod_deploys{status="failed"}` 增长、`/healthz` 非 200 配告警。无 Prometheus 时直接 `curl` 人读。

> K8s/编排探针建议：liveness 用 `/health`，readiness 用 `/healthz`。

---

## 2. 部署失败处理

部署失败时系统会：
1. 把 `dev_tasks.{staging,prod}_deploy_status` 置 `failed`，日志尾部存进 `..._deploy_log`
2. 私聊项目 creator
3. **私聊所有管理员**（`role=='admin'` 且绑定 `wechat_user_id`）

> 收不到管理员告警？检查是否存在 `role=='admin'` 且 `wechat_user_id` 非空的用户。

排查步骤：
```bash
# 看后台项目详情的部署日志，或直接查库
docker compose exec postgres psql -U postgres -d superuserai \
  -c "select id, prod_deploy_status, left(prod_deploy_log, 500) from dev_tasks order by id desc limit 5;"
```

重新部署：后台项目详情页点 **redeploy-prod**（用 `prod_deployed_sha`，无则 `FETCH_HEAD`），或重新触发对应 webhook。

常见原因：
| 现象 | 可能原因 |
|---|---|
| `ssh target parse error` | 仓库 `prod_ssh_target` 格式错，应为 `user@host[:port]` |
| `deploy timeout` | 建镜像/迁移太久 → 调大 `prod_deploy_timeout_sec` |
| `Permission denied (publickey)` | deploy 私钥未授权到目标服务器 / `prod_ssh_key_path` 路径错 |
| alembic 步骤报错 | 目标 `docker-compose.prod.yml` 没有 `backend` service → 关掉仓库 `prod_run_migrations` |
| `skipped: missing prod fields` | 后台该仓库的生产部署字段没填全 |

---

## 3. 卡死部署的自愈

backend 启动时会把卡在 `deploying`（且超过 30 分钟、未完成）的 staging/prod 任务标记为 `failed`（见 `main.py` lifespan → `recover_stale_deploys`）。所以**重启 backend** 是清理卡死部署的安全手段：

```bash
docker compose restart backend
```

dev-agent 侧：`/api/tasks/claim` 自带 stale recovery——超过 60 分钟的 `claimed/in_progress` dev_task 会被判死亡并释放，项目可被重新接走。

---

## 4. 数据库迁移

```bash
# 升级到最新（每次拉含新 migration 的代码后必做）
docker compose exec backend alembic upgrade head

# 查看当前版本 / 历史
docker compose exec backend alembic current
docker compose exec backend alembic history

# 回滚一步（谨慎）
docker compose exec backend alembic downgrade -1
```

> 生产部署若开了 `prod_run_migrations`，会在部署脚本里自动 `alembic upgrade head`；否则需手动执行。

备份（升级前建议）：
```bash
docker compose exec postgres pg_dump -U postgres superuserai > backup_$(date +%F).sql
```

---

## 5. 日志

```bash
docker compose logs -f backend       # 后端（含部署、webhook、企微管道日志）
docker compose logs -f dev-agent     # 写代码 worker
docker compose logs --tail=200 backend
```

日志格式：`时间 级别 logger名 — 消息`（`app/main.py` 里 `logging.basicConfig`）。关键 logger 在 `INFO`：`app.gateway.wechat_gateway`、`app.services.message_handler`、各部署服务等。

定位部署问题搜关键字：`prod deploy` / `staging deploy` / `notify_admins`。

---

## 6. 重启 / 升级流程

```bash
cd docker
git pull
docker compose up -d --build         # 重建并滚动起新容器
docker compose exec backend alembic upgrade head
curl -s localhost:8000/healthz       # 确认 200
```

vworkapi-bridge（Windows）单独升级：`git pull` → 重装 `pip install -e .` → 重启 nssm 服务。

---

## 7. systemd 守护（非 Docker 手动部署时）

`/etc/systemd/system/superuserai-backend.service`：
```ini
[Unit]
Description=SuperUserAI Backend
After=network.target postgresql.service

[Service]
User=deploy
WorkingDirectory=/opt/superuserai/backend
EnvironmentFile=/opt/superuserai/backend/.env
ExecStart=/opt/superuserai/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now superuserai-backend
sudo systemctl status superuserai-backend
journalctl -u superuserai-backend -f
```

dev-agent 同理，`ExecStart=.../python -m app.main`。

---

## 8. 巡检清单（建议每日/告警驱动）

- [ ] `/healthz` 返回 200
- [ ] `superuserai_prod_deploys{status="failed"}` 无异常增长
- [ ] 无项目长期卡在 `developing`（dev-agent 是否在跑、LLM key 是否有效）
- [ ] 磁盘：dev-agent `workspace_dir`、Postgres 卷、Docker 镜像缓存
- [ ] vworkapi-bridge 在线（企微图片功能依赖它）
