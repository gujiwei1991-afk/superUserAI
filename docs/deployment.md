# SuperUserAI 部署指南

本指南覆盖三个服务的部署：**backend**（FastAPI 主服务）、**dev-agent**（自动写代码的 worker）、**vworkapi-bridge**（企微图片中转，跑在 Windows 上）。

> 相关文档：
> - 环境变量逐项说明见 [env-reference.md](./env-reference.md)
> - staging/生产目标服务器的一次性准备见 [staging-server-setup.md](./staging-server-setup.md)
> - 日常运维与故障处理见 [runbook.md](./runbook.md)

---

## 0. 架构与端口一览

```
企微用户 ──▶ vworkApi(Windows) ──▶ backend(:8000) ──▶ Postgres / GitHub
                  ▲                      │
                  │ 图片URL              ├─▶ dev-agent 轮询 /tasks/claim 接活儿写代码开 PR
            vworkapi-bridge(:9100)       └─▶ SSH+docker compose 部署 staging / 生产
```

| 服务 | 运行平台 | 端口 | 启动命令 |
|---|---|---|---|
| backend | Linux/Docker | 8000 | `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| dev-agent | Linux/Docker | 无（出站轮询） | `python -m app.main` |
| Postgres | Docker | 5432（仅本机） | compose 内置 |
| vworkapi-bridge | Windows | 9100 | `uvicorn app.main:app --host 0.0.0.0 --port 9100` |

> Redis 在 `docker-compose.yml` 里仍会起一个容器，但**当前后端代码未实际使用 Redis**（仅保留 `redis_url` 配置占位）。如需精简可移除该服务。

---

## 1. 推荐方式：Docker Compose（backend + dev-agent + Postgres）

仓库自带 `docker/docker-compose.yml`，一把拉起 backend、dev-agent、Postgres、Redis。

```bash
cd docker
cp .env.example .env
vim .env            # 填 POSTGRES_PASSWORD / GITHUB_TOKEN / LLM_* / JWT_SECRET / VWORK_API_HOST 等
docker compose up -d --build
docker compose ps
```

`.env` 关键项（详见 env-reference.md）：

```ini
POSTGRES_PASSWORD=<强密码>
VWORK_API_HOST=<跑 vworkApi 的 Windows 机器 IP>
GITHUB_TOKEN=ghp_xxx
GITHUB_WEBHOOK_SECRET=<与 GitHub webhook 配置一致>
LLM_PROVIDER=openai
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4.1-mini
JWT_SECRET=<openssl rand -hex 32>
```

### 1.1 首次启动后的初始化（必做）

```bash
# 1) 跑数据库迁移（建表 / 升级到最新）
docker compose exec backend alembic upgrade head

# 2) 创建管理员账号（后台登录 + 企微审核权限）
#    具体脚本见 scripts/ 目录或后台说明；管理员 = users.role == 'admin'

# 3) 健康检查
curl -s localhost:8000/healthz       # {"status":"ok","checks":{"database":"ok"}}
```

> ⚠️ 迁移不会自动跑。每次拉取含新 migration 的代码后，都要重新 `alembic upgrade head`。

---

## 2. 手动部署 backend（不用 Docker）

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e .                      # 生产依赖
pip install -e ../shared              # shared 包
cp .env.example .env && vim .env      # 填配置
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

生产建议用 `systemd` 守护（示例见 runbook.md），并在前面挂 nginx 反代 + HTTPS。

---

## 3. 部署 dev-agent

dev-agent 是无端口的出站 worker：轮询 backend 的 `POST /tasks/claim`，接到 `status==APPROVED` 且挂了 GitHub issue 的项目就拉代码、调 LLM 写代码、开 PR。

Docker（推荐，已包含在 compose 里）：随 `docker compose up -d` 一起起来。

手动：

```bash
cd dev-agent
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e . && pip install -e ../shared
cp .env.example .env && vim .env      # backend_url / github_token / llm_* / workspace_dir
python -m app.main
```

关键配置：
- `backend_url`：能访问到 backend 的地址（compose 内为 `http://backend:8000`）
- `workspace_dir`：clone 仓库的工作目录，需可写且空间充足
- `github_token`：需有目标仓库的 `repo` 权限（建 PR）

---

## 4. 部署 vworkapi-bridge（Windows）

跑在装了 vworkApi 的 Windows 机器上，负责把企微图片下载并上传七牛，回传 CDN URL 给 backend。

```bat
:: Python 3.10+
python -m venv .venv
.venv\Scripts\activate
pip install -e .
copy .env.example .env
notepad .env          :: 填 QINIU_* 和 IMAGE_BRIDGE_TOKEN（须与 backend 的 image_bridge_token 一致）

uvicorn app.main:app --host 0.0.0.0 --port 9100
```

长期运行用 `nssm` 注册为 Windows 服务（见 `vworkapi-bridge/README.md`）。

backend 侧对应配置：`image_bridge_url=http://<windows-ip>:9100`、`image_bridge_token=<同一密钥>`。

---

## 5. 自动部署链路（staging + 生产）配置

backend 通过 SSH + `docker compose` 把 PR 部署到目标服务器，全程由 GitHub webhook 驱动：

- **PR opened/更新** → 部署到 **staging**（`docker-compose.yml`，PR head）
- **PR 合并到 main** → 部署到 **生产**（`docker-compose.prod.yml`，merge commit）→ 项目翻 `ACCEPTANCE` → 企微通知验收

### 5.1 一次性准备

1. 目标服务器准备（deploy 用户、docker、目录、SSH key 授权）→ 见 [staging-server-setup.md](./staging-server-setup.md)，生产同理。
2. 在 backend `.env` 配 SSH key 路径：`staging_ssh_key_path` / `prod_ssh_key_path`（生产留空则回退到 staging key）。
3. GitHub 仓库配 webhook：
   - Payload URL：`https://<backend-域名>/api/webhooks/github`
   - Content type：`application/json`
   - Secret：与 `github_webhook_secret` 一致
   - 事件：至少勾选 **Pull requests**

### 5.2 在后台逐仓库填部署配置

后台 → 项目/仓库详情，分别填 staging 与生产两组：

| 字段 | 说明 |
|---|---|
| `staging_url` / `prod_url` | 部署后的访问地址（通知里回传给用户） |
| `staging_ssh_target` / `prod_ssh_target` | `user@host[:port]`，省略 user 用默认 `deploy` |
| `staging_deploy_path` / `prod_deploy_path` | 服务器上仓库所在目录 |
| `staging_compose_file` / `prod_compose_file` | compose 文件名，生产默认 `docker-compose.prod.yml` |
| `staging_compose_project` / `prod_compose_project` | **compose 项目名（`-p`），可选**。线上既有 stack 若是用 `-p <名字>` 或 `COMPOSE_PROJECT_NAME` 起的，**必须填对应项目名**，否则部署会按"工作目录名"解析项目名、起出一套平行容器。留空则不带 `-p`。 |
| `prod_run_migrations` | 勾选则生产部署后跑 `docker compose run --rm backend alembic upgrade head`；目标 compose 须有 `backend` service，否则关掉 |

配好后合并一个 PR 即可验证整条链路；失败会私聊 creator 并告警所有管理员。

---

## 6. 上线前检查清单

- [ ] `docker compose up -d` 后 `docker compose ps` 全部 healthy
- [ ] `alembic upgrade head` 已执行（含最新 `prod_*` 字段迁移）
- [ ] `curl /healthz` 返回 200
- [ ] 已创建管理员（`role=='admin'` 且绑定 `wechat_user_id`，否则收不到告警）
- [ ] GitHub webhook 已配且 secret 一致
- [ ] 每个仓库的 staging/生产部署字段已填、SSH key 已授权
- [ ] 目标服务器存在对应的 `docker-compose.yml` / `docker-compose.prod.yml`
- [ ] vworkapi-bridge 在 Windows 上常驻，token 与 backend 一致
