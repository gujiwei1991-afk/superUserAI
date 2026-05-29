# 环境变量参考

变量名大小写不敏感（pydantic-settings）。每个服务读各自目录下的 `.env`；Docker Compose 则在 `docker/.env` 注入（compose 里用大写形式）。

---

## backend（`backend/.env`）

来源：`backend/app/config.py`。

### 核心
| 变量 | 默认值 | 说明 |
|---|---|---|
| `database_url` | `postgresql+asyncpg://postgres:postgres@localhost:5432/superuserai` | Postgres 异步连接串（必须 `+asyncpg`） |
| `redis_url` | `redis://localhost:6379` | 占位，当前代码未使用 |
| `jwt_secret` | `CHANGE_ME...` | **生产必改**：`openssl rand -hex 32` |
| `jwt_algorithm` | `HS256` | JWT 算法 |
| `jwt_expire_minutes` | `1440` | 后台登录 token 有效期（分钟） |
| `admin_password` | `admin123` | **生产必改** |

### 企微（vworkApi）
| 变量 | 默认值 | 说明 |
|---|---|---|
| `vwork_api_host` | `127.0.0.1` | vworkApi 所在机器 IP |
| `vwork_api_port` | `8989` | vworkApi HTTP 端口 |
| `vwork_msg_port` | `9000` | 接收回调端口 |

### GitHub
| 变量 | 默认值 | 说明 |
|---|---|---|
| `github_token` | `""` | 默认 PAT，需 `repo` 权限（建 issue/读 PR）；仓库可单独覆盖 |
| `github_webhook_secret` | `""` | 校验 webhook 签名，须与 GitHub 配置一致 |

### LLM
| 变量 | 默认值 | 说明 |
|---|---|---|
| `llm_provider` | `openai` | `openai` / 兼容网关 |
| `llm_api_key` | `""` | LLM key |
| `llm_base_url` | `""` | LLM 网关地址 |
| `llm_model` | `""` | 主模型 |
| `intent_llm_model` | `""` | 群意图识别模型，空=用 `llm_model` |
| `intent_llm_timeout_seconds` | `15.0` | 意图识别超时 |
| `claude_cli_executable` | `claude` | 若用 claude CLI 适配 |
| `claude_cli_timeout_seconds` | `180` | CLI 超时 |

### 群 / 交互
| 变量 | 默认值 | 说明 |
|---|---|---|
| `group_bound_auto_activate` | `true` | 绑定群是否自动激活会话 |
| `pmagent_ready_hint_after_turns` | `3` | 几轮后提示可 #确认 |

### 图片中转（vworkapi-bridge）
| 变量 | 默认值 | 说明 |
|---|---|---|
| `image_bridge_url` | `""` | bridge 地址，如 `http://1.2.3.4:9100` |
| `image_bridge_token` | `""` | 与 bridge 的 `IMAGE_BRIDGE_TOKEN` 一致 |
| `image_bridge_timeout_seconds` | `30.0` | 拉图超时 |

### Staging 自动部署
| 变量 | 默认值 | 说明 |
|---|---|---|
| `staging_ssh_key_path` | `""` | 部署私钥路径 |
| `staging_ssh_user_default` | `deploy` | ssh_target 省略 user 时的默认用户 |
| `staging_deploy_timeout_sec` | `600` | 部署超时 |
| `staging_log_tail_lines` | `200` | 保留日志尾行数 |

### 生产自动部署
| 变量 | 默认值 | 说明 |
|---|---|---|
| `prod_ssh_key_path` | `""` | 生产部署私钥，**留空回退到 `staging_ssh_key_path`** |
| `prod_ssh_user_default` | `deploy` | 同上 |
| `prod_deploy_timeout_sec` | `1200` | 生产部署超时（含建镜像+迁移，给足） |
| `prod_log_tail_lines` | `200` | 日志尾行数 |

> 仓库级部署字段（`prod_url`/`prod_ssh_target`/`prod_deploy_path`/`prod_compose_file`/`prod_run_migrations` 及 staging 对应项）存在数据库 `repos` 表，**在后台逐仓库填**，不走 `.env`。

---

## dev-agent（`dev-agent/.env`）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `backend_url` | `http://localhost:8000` | backend 地址（compose 内 `http://backend:8000`） |
| `github_token` | `""` | 建 PR 用，需 `repo` 权限 |
| `llm_provider` / `llm_api_key` / `llm_base_url` / `llm_model` | 同 backend | 写代码用的 LLM |
| `workspace_dir` | `/tmp/superuserai/workspace` | clone 仓库的工作目录，需可写 |

---

## vworkapi-bridge（`vworkapi-bridge/.env`，Windows）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `QINIU_AK` / `QINIU_SK` | `""` | 七牛 AccessKey / SecretKey |
| `QINIU_BUCKET` | `""` | 七牛存储空间名 |
| `QINIU_DOMAIN` | `https://cdn.example.qiniu.com` | CDN 域名 |
| `IMAGE_BRIDGE_TOKEN` | `""` | 与 backend `image_bridge_token` 一致 |
| `VWORKAPI_HOST` | `127.0.0.1` | 本机 vworkApi |
| `VWORKAPI_PORT` | `8989` | vworkApi 端口 |
| `TMP_DIR` | `C:\tmp\superuserai-images` | 临时图片目录 |
| `MAX_IMAGE_BYTES` | `10485760` | 单图上限（10MB） |

---

## Docker Compose（`docker/.env`，大写形式）

`docker-compose.yml` 用大写变量注入容器。最少需要：

```ini
POSTGRES_PASSWORD=<强密码>
VWORK_API_HOST=<windows-ip>
VWORK_API_PORT=8989
GITHUB_TOKEN=ghp_xxx
GITHUB_WEBHOOK_SECRET=xxx
LLM_PROVIDER=openai
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4.1-mini
JWT_SECRET=<openssl rand -hex 32>
```
