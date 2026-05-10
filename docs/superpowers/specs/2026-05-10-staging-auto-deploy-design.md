# Staging 自动部署 — 设计方案

**日期：** 2026-05-10
**作者：** Claude (Opus) + 用户协同 brainstorming
**状态：** 待用户最终审阅
**总目标：** PR 创建/更新时，由 backend 集中 SSH 到用户自管服务器跑 docker compose，把当前 PR 部署到一个固定的 staging URL，并通过企业微信通知客户去看效果。失败则文字通知开发者。

---

## 1. 背景与目标

### 1.1 现状

平台已经能完成"用户企微提需求 → PM 出 PRD → 审核 → dev-agent 编码 → 提 PR"全链路，但 PR 提完之后没有任何"客户能看到效果"的环节：客户必须等到 PR merge + 用户手动 SSH 部署到生产，才能看到最终成果。整个流程的反馈周期被拉长到不可接受。

`repos` 表已经有 `deploy_server`、`deploy_config` 两个未使用的字段（最初为生产部署预留），未实际填充。`webhooks.py` 处理 `pull_request.closed (merged)` 事件，对其他 PR 事件不响应。

### 1.2 目标

- PR 创建（`opened`）+ 每次 push（`synchronize`）+ 重新打开（`reopened`）→ 自动把当前 head 部署到 **该 repo 唯一固定的 staging URL**
- 部署成功 → 给项目 creator 在企微发卡片链接，点开就是 staging URL
- 部署失败 → 给项目 creator 发文字消息，附简短错误摘要 + 管理后台链接
- 不引入 Cloudflare、不每 PR 一个独立 URL、不引入 GitHub Actions（集中由 backend SSH 推）
- staging 是覆盖式：同 repo 后到的 PR 部署会覆盖前一个

### 1.3 核心设计决策（已与用户对齐）

| 决策点 | 选择 | 理由 |
|---|---|---|
| Cloudflare 是否接入 | 否 | 用户有公网 IP + 域名，Let's Encrypt 已够；YAGNI |
| PR 预览隔离粒度 | 覆盖式（同 repo 唯一 staging URL） | 资源消耗最低，单人/小团队场景够用 |
| 部署触发点 | `pull_request` opened/synchronize/reopened | 越早给客户反馈越好 |
| 谁负责 SSH | backend（不是 dev-agent，也不是用户 repo 的 GitHub Actions） | webhook 驱动覆盖所有 PR 来源；SSH key 集中管 |
| SSH 实现 | Python stdlib `asyncio.create_subprocess_exec` 调系统 `ssh` 命令 | 不引第三方依赖（无 paramiko / asyncssh） |
| 部署失败通知形式 | 文字消息（不是卡片） | 卡片是给客户看的"效果就绪"，失败给开发者看 |
| 重试入口 | 管理后台按钮 | 不开放企微命令，避免客户误触 |
| 项目 docker 配置 | 用户在自己 repo 提供 `docker-compose.staging.yml`（或自定义文件名） | 平台不替项目决定怎么跑 |

---

## 2. 整体架构

```
Dev-agent push feat/issue-N 到 GitHub
         │
         ▼
GitHub: PR opened/synchronize/reopened
         │
   webhook 推送到 backend (POST /api/webhooks/github)
         │
         ▼
backend/app/api/webhooks.py 新增分支：
  - 解析出 (repo, project, dev_task, pr_number, head_sha)
  - 校验 repo.staging_* 都配齐了（缺则 status=skipped 直接返回）
  - 把任务加入 BackgroundTasks：
        staging_deploy_service.deploy_pr(repo, project, dev_task,
                                         pr_number, head_sha)
         │
         ▼
StagingDeployService.deploy_pr (在 background task 里跑):
  1. dev_task.staging_deploy_status = "deploying"
  2. 拿到 per-repo asyncio.Lock（同 repo 串行部署）
  3. SSH 到 repo.staging_ssh_target 执行：
        cd {staging_deploy_path} &&
        git fetch origin pull/{pr_number}/head:pr-{pr_number} &&
        git checkout -f pr-{pr_number} &&
        git reset --hard {head_sha} &&
        docker compose -f {staging_compose_file} up -d --build &&
        docker compose -f {staging_compose_file} ps
  4. stdout/stderr 最后 200 行写入 dev_task.staging_deploy_log
  5. 成功：
       - dev_task.staging_deploy_status = "success"
       - dev_task.staging_deployed_at = now
       - project.status = STAGED
       - 调 wechat_client.send_card_link(creator, ...)
     失败：
       - dev_task.staging_deploy_status = "failed"
       - 调 wechat_client.send_text(creator, "...")

服务器侧（一次性配好，详见 §8）:
  nginx + Let's Encrypt 证书
  staging.<your-domain>.com → docker compose 暴露的端口
  /srv/staging/{repo-name}/ 工作目录
  deploy 用户（受限 shell）
```

### 2.1 数据流不影响的部分

- `pull_request.closed (merged)` 仍走原来"通知用户去验收生产部署"逻辑
- dev-agent 流程完全不改
- 用户的评分（`#评分 N`）流程不改
- 现有 `repos.deploy_server` / `deploy_config` 字段不动（留给将来生产部署用）

---

## 3. 数据模型变更

### 3.1 `repos` 表新增 4 个字段

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `staging_url` | `str \| None`, `Text` | `NULL` | 给客户的 URL，如 `https://staging.myapp.com`。**为空则该 repo 跳过 staging 部署** |
| `staging_ssh_target` | `str \| None`, `String(255)` | `NULL` | SSH 目标，如 `deploy@server.com`（可包含端口：`deploy@server.com:2222`） |
| `staging_deploy_path` | `str \| None`, `Text` | `NULL` | 服务器上工作目录，如 `/srv/staging/oaSys` |
| `staging_compose_file` | `str`, `String(255)` | `"docker-compose.staging.yml"` | 用哪个 compose 文件（在 `staging_deploy_path` 内的相对路径） |

校验：`StagingDeployService` 在执行前判定四字段是否都有值；任意一个 NULL → `staging_deploy_status = "skipped"`，不报错、不发企微通知（开发者通过管理后台看 status 即可知道）。

### 3.2 `dev_tasks` 表新增 3 个字段

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `staging_deploy_status` | `str`, `String(32)` | `"pending"` | 五选一：`pending` / `deploying` / `success` / `failed` / `skipped` |
| `staging_deployed_at` | `datetime \| None` | `NULL` | 最近一次成功部署的时刻 |
| `staging_deploy_log` | `str \| None`, `Text` | `NULL` | 最后一次部署的 stdout+stderr 合并后的最后 200 行（截取后存） |

`staging_deploy_status` 用普通字符串字段（不用 Postgres enum），便于以后增删值不需要 alembic 改 enum。

### 3.3 `ProjectStatus` 枚举新增 `STAGED`

`shared/shared/constants.py`：

```
DRAFTING → REVIEWING → APPROVED → DEVELOPING → STAGED → ACCEPTANCE → COMPLETED
                                          ↘ DEPLOYED ↗  （生产部署后路径，不变）
```

新增 `STAGED = "staged"`，语义："PR 已部署到 staging，等客户验收"。`STAGED` 是稳定终态（直到客户交互），不在通知发送时立即切到 `ACCEPTANCE`；`ACCEPTANCE` 由现有的客户回复评分/反馈流程触发切换（不在本 spec 范围）。

### 3.4 Alembic 迁移

单个 migration 完成上述三处改动：
- `ALTER TABLE repos ADD COLUMN staging_url TEXT NULL`
- `ALTER TABLE repos ADD COLUMN staging_ssh_target VARCHAR(255) NULL`
- `ALTER TABLE repos ADD COLUMN staging_deploy_path TEXT NULL`
- `ALTER TABLE repos ADD COLUMN staging_compose_file VARCHAR(255) NOT NULL DEFAULT 'docker-compose.staging.yml'`
- `ALTER TABLE dev_tasks ADD COLUMN staging_deploy_status VARCHAR(32) NOT NULL DEFAULT 'pending'`
- `ALTER TABLE dev_tasks ADD COLUMN staging_deployed_at TIMESTAMP NULL`
- `ALTER TABLE dev_tasks ADD COLUMN staging_deploy_log TEXT NULL`

`ProjectStatus` 是 Python enum 不入库（`projects.status` 是 `String`），无需迁移。

---

## 4. 新模块与接口改动

### 4.1 `backend/app/services/staging_deploy_service.py`（新文件）

```python
class StagingDeployService:
    def __init__(self, wechat_client: WeChatClient, ssh_key_path: str,
                 ssh_user_default: str = "deploy"):
        self.wechat_client = wechat_client
        self.ssh_key_path = ssh_key_path
        # per-repo lock，保证同 repo 部署串行
        self._locks: dict[int, asyncio.Lock] = {}

    def _lock_for(self, repo_id: int) -> asyncio.Lock:
        if repo_id not in self._locks:
            self._locks[repo_id] = asyncio.Lock()
        return self._locks[repo_id]

    async def deploy_pr(
        self,
        db: AsyncSession,
        repo: Repo,
        project: Project,
        dev_task: DevTask,
        pr_number: int,
        head_sha: str,
    ) -> None:
        # 配置完整性校验
        # 锁 + 状态切到 deploying
        # 构造 SSH 命令
        # 执行 + 捕获日志（带 10 分钟超时）
        # 成功 / 失败两条路径，分别更新 DB + 通知企微
```

完整行为见 §5。

### 4.2 `backend/app/api/webhooks.py` 改动

在现有的 `github_webhook` handler 里加入分支：

```python
event = request.headers.get("X-GitHub-Event")
payload = await request.json()

if event == "pull_request":
    action = payload.get("action")
    if action in ("opened", "synchronize", "reopened"):
        pr = payload["pull_request"]
        # 通过 head ref 解析出 dev_task（dev-agent 命名规范是 feat/issue-N）
        # 拿到 repo / project / dev_task / pr_number / head_sha
        # 校验 dev_task.staging_deploy_status 不是 "deploying"（避免重入）
        background_tasks.add_task(
            staging_deploy_service.deploy_pr,
            db, repo, project, dev_task, pr_number, pr["head"]["sha"],
        )
        return {"ok": True, "queued": "staging_deploy"}
    elif action == "closed" and pr.get("merged"):
        # 现有逻辑保持不动
        ...
```

要求：
- backend 已经在 `main.py` 通过 DI 实例化了 `StagingDeployService`，注入到 webhook 路由
- 不暴露新的 HTTP API（部署是 webhook 驱动 + 管理后台触发的内部行为）

### 4.3 管理后台新增"重试部署"按钮的接口

仅供 admin 用户调用：

```
POST /admin/dev-tasks/{dev_task_id}/redeploy-staging
  → 用 dev_task 当前的 pr_number + head_sha 重新触发 deploy_pr
  → 返回 {"queued": True}
```

（已存在 `/admin/...` 鉴权中间件复用）

### 4.4 配置项

`backend/app/config.py` 新增：

```python
staging_ssh_key_path: str = ""    # 后端机器上 SSH 私钥路径，如 /etc/superuserai/staging_id_ed25519
staging_ssh_user_default: str = "deploy"  # 当 staging_ssh_target 没写 user@ 时的默认 user
staging_deploy_timeout_sec: int = 600     # 单次 deploy_pr 最长执行时间（10 分钟）
staging_log_tail_lines: int = 200          # 失败时保留的 stdout/stderr 行数
```

`.env.example` 同步更新。

---

## 5. SSH 部署执行细节

### 5.1 SSH 命令构造

```python
# 拼出 SSH 调用
ssh_args = [
    "ssh",
    "-i", self.ssh_key_path,
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", "BatchMode=yes",          # 禁止任何交互（密码 / 确认）
    "-o", "ConnectTimeout=15",
    repo.staging_ssh_target,
    "bash", "-s",                    # 把 stdin 当 bash 脚本
]

# 远端要跑的脚本（通过 stdin 喂进去）
remote_script = f"""
set -euo pipefail
cd {shlex.quote(repo.staging_deploy_path)}
git fetch origin pull/{pr_number}/head:pr-{pr_number}
git checkout -f pr-{pr_number}
git reset --hard {shlex.quote(head_sha)}
docker compose -f {shlex.quote(repo.staging_compose_file)} up -d --build
docker compose -f {shlex.quote(repo.staging_compose_file)} ps
"""

proc = await asyncio.create_subprocess_exec(
    *ssh_args,
    stdin=asyncio.subprocess.PIPE,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.STDOUT,
)
stdout, _ = await asyncio.wait_for(
    proc.communicate(remote_script.encode()),
    timeout=settings.staging_deploy_timeout_sec,
)
```

**关键点：**
- `set -euo pipefail` 让任何一步失败立即终止
- `BatchMode=yes` 杜绝交互式提示挂死
- `accept-new` 第一次连接自动信任 host key（避免人工干预），但不接受变更过的 key（防中间人）
- `staging_ssh_target` 解析规则（实现里要处理）：
  - 默认格式 `user@host`，整体作为 ssh 最后一个位置参数传入
  - 带端口 `user@host:NNNN`：拆出端口数字，加 `-p NNNN` 到 ssh 参数列表，剩下 `user@host` 作位置参数
  - 不含 `@`（只有 host）：补 `settings.staging_ssh_user_default` 当 user
  - 端口非数字 / 整体格式异常 → 在 `deploy_pr` 里直接 status=failed + 错误日志写明"target 解析失败"，不调 SSH
- `head_sha` 从 GitHub webhook 拿，已经是可信的；用 `shlex.quote` 兜底防注入

### 5.2 超时与失败判定

| 情况 | 判定 |
|---|---|
| `proc.returncode != 0` | 失败（远端 bash 报错） |
| `asyncio.TimeoutError` | 失败，原因 = "deploy timeout (10 min)"，强制 `proc.kill()` |
| SSH 连接失败（远端不可达 / key 拒绝） | 失败，stdout/stderr 包含 ssh 自己的报错 |
| 远端 bash 跑完 + `docker compose ps` 输出有任何容器不是 `Up` | **不算失败**（MVP 简化）：只要脚本没非零退出就算成功；容器没起来由开发者通过日志发现 |

后续可加"`docker compose ps --format json` 解析检查所有 service 是否 healthy"，留作 v2。

### 5.3 并发控制

- 同 repo 串行：`asyncio.Lock()` per repo_id。如果一个部署还在跑，新的 webhook 来的请求 **不排队**，**直接更新一个 "pending head_sha" 字段**（在内存里 per repo），等当前部署完成后用最新的 head_sha 再触发一次（合并多次 push 的部署，避免 N 次 push 触发 N 次部署）
- 不同 repo 并行：互不阻塞
- 实现：`StagingDeployService` 内部维护 `_pending_redeploys: dict[repo_id, str]`，部署完成后检查并清空

### 5.4 进程重启的清理

backend 进程在部署中途崩溃 / 重启 → DB 里某些 `dev_task.staging_deploy_status = "deploying"` 永远卡住。

**清理策略：** backend 启动时跑一次 `_recover_stale_deploys()`：
- 找 `staging_deploy_status = "deploying" AND staging_deployed_at IS NULL AND started_at < now() - 15 min` 的 dev_task
- 强制改成 `staging_deploy_status = "failed"`，`staging_deploy_log = "marker: backend restart while deploying"`
- 不发企微通知（避免重启时给用户发一堆）

---

## 6. 企业微信通知模板

### 6.1 部署成功 — 卡片链接

调 `wechat_client.send_card_link(user_id, title, desc, url, cover_url)`：

| 字段 | 取值 |
|---|---|
| `user_id` | `project.creator.wechat_user_id`（如果项目绑了群，发到群） |
| `title` | `f"{project.title}"` （30 字内截断） |
| `desc` | `f"PR #{pr_number} 已部署到测试环境，点开看效果"` |
| `url` | `repo.staging_url` |
| `cover_url` | 留空 / 用一个固定 placeholder |

接着发一条文本：
```
满意请回复 #评分 1-10 [意见]
需要修改请回复 #修改 [说明]
```

### 6.2 部署失败 — 文本消息

```
PR #{pr_number} 部署到测试环境失败 ❌
错误摘要：{error_summary}
详情见管理后台：https://{admin_host}/projects/{project_id}
```

`error_summary` 是给企微通知用的**短摘要**（区别于 §3.2 存进 DB 的 `staging_deploy_log` 全量 200 行）。**MVP 简化：直接取 `staging_deploy_log` 最后 200 字符**，过得去就行；将来可改成"匹配 error/failed/traceback 优先"。

### 6.3 通知接收人路由

复用现有 `project_service` 里"项目通知发给谁"的判定逻辑（绑群 → 群；不绑群 → creator 私聊）。

---

## 7. 管理后台改动

### 7.1 `backend/templates/repos.html`

repo 编辑表单新增一个 fieldset："Staging 部署配置（可选）"：
- `staging_url`：URL 输入框，提示"留空则该 repo 不做 staging 自动部署"
- `staging_ssh_target`：文本框，placeholder `deploy@server.com[:port]`
- `staging_deploy_path`：文本框，placeholder `/srv/staging/myapp`
- `staging_compose_file`：文本框，默认值 `docker-compose.staging.yml`

页面下面加一段小文字提示："首次配置请参考 [README]({readme_url})"

### 7.2 `backend/templates/project_detail.html`

新增"Staging 部署"卡片：
- 当前关联的 dev_task（一般是最新的）的 `staging_deploy_status`（带颜色标记：success 绿、failed 红、deploying 黄、pending/skipped 灰）
- `staging_deployed_at`（如非 NULL）
- `staging_url`（点击新窗口打开）
- 若 status=failed：展开按钮显示 `staging_deploy_log` 全文
- "重试部署"按钮（只在 status ∈ {failed, success} 时显示），点击调 §4.3 的 `POST /admin/dev-tasks/{dev_task_id}/redeploy-staging`

### 7.3 `backend/templates/dashboard.html` （可选小改）

顶部新增一个"近 24h staging 部署"统计卡片：成功 N / 失败 M。**MVP 不做**，留作后续。

---

## 8. 服务器侧一次性准备

写一个 README 给用户照做：`docs/staging-server-setup.md`（spec 落地后由实施计划阶段产出）。

### 8.1 服务器需要的状态

```
1. 装 docker + docker compose plugin
2. 建 deploy 用户：
   sudo useradd -m -s /bin/bash deploy
   sudo usermod -aG docker deploy
3. 把 backend 机器的 SSH 公钥加到 /home/deploy/.ssh/authorized_keys
   （限制：不给 sudo，shell 不强制限制 —— 留出灵活性，必要时用 ForceCommand 加固）
4. 给 GitHub 仓库加 deploy key（只读），存到 /home/deploy/.ssh/<repo>_key
   并配 ~/.ssh/config 让 git 用对应 key
5. 装 nginx：
   sudo apt install nginx
6. 装 certbot：
   sudo apt install certbot python3-certbot-nginx
7. DNS 配 staging.<your-domain>.com → 服务器公网 IP
8. nginx 写 server block：staging.<your-domain>.com → proxy_pass http://127.0.0.1:<port>
   （port 由 docker-compose.staging.yml 暴露）
9. 申请证书：
   sudo certbot --nginx -d staging.<your-domain>.com
10. 第一次 git clone 用户的 repo：
    sudo -iu deploy
    git clone git@github.com:owner/repo.git /srv/staging/<repo-name>
```

### 8.2 backend 机器需要的状态

```
1. 生成 SSH key：
   ssh-keygen -t ed25519 -f /etc/superuserai/staging_id_ed25519 -N ""
   chown <backend-user>:<backend-user> /etc/superuserai/staging_id_ed25519
   chmod 600 /etc/superuserai/staging_id_ed25519
2. 把公钥（.pub）加到 §8.1 第 3 步
3. .env 里设：
   STAGING_SSH_KEY_PATH=/etc/superuserai/staging_id_ed25519
```

### 8.3 用户 repo 需要的内容

`<repo>/docker-compose.staging.yml`：用户提供。**平台不替写**，但 README 给一个最小示例：

```yaml
services:
  app:
    build: .
    ports:
      - "127.0.0.1:8080:8080"
    environment:
      - DATABASE_URL=postgres://...
  postgres:
    image: postgres:16
    volumes:
      - staging_pg_data:/var/lib/postgresql/data
volumes:
  staging_pg_data:
```

要求：
- 端口绑 `127.0.0.1` 不绑 `0.0.0.0`（让 nginx 反代来流量）
- DB / 上传文件 / 缓存等用 named volume 持久化，避免每次重建丢数据

---

## 9. 范围（YAGNI）

### 9.1 包含

- §3 数据模型变更
- §4 新服务 + webhook 改动 + 管理后台重试 API + 配置项
- §5 SSH 部署完整逻辑（含超时、并发控制、进程重启清理）
- §6 企微通知（成功卡片 + 失败文本）
- §7 管理后台 2 个模板小改
- §8 服务器准备 README
- §11 单元 + 端到端测试

### 9.2 不做

| 不做 | 理由 |
|---|---|
| 每个 PR 独立 staging URL | 用户已选覆盖式 |
| Cloudflare 接入 | 用户已选纯自管 |
| 自动 DB 迁移 | 由项目自己的 docker entrypoint 处理 |
| 部署失败自动回滚 | 失败时上一版仍在跑（覆盖式 docker compose 失败不会删旧容器，只是新版没起来）；手动重试 |
| 一台服务器同时跑多 repo staging | MVP 假设每 repo 独立服务器；多 repo 共享需要端口管理 / nginx 多 server block，留作后续 |
| staging 访问控制 | staging URL 公开，README 标注"别在 staging 放敏感数据" |
| docker 镜像版本管理 | 每次 `--build` 重 build，旧镜像靠用户手动 `docker system prune` |
| staging 健康检查 / 自动重启 | `docker compose ps` 完跑就算成功 |
| 把 staging 配置生成到用户 repo | 由用户自己提供 docker-compose.staging.yml |
| 多人通知 / 抄送 | 只通知 creator（或绑定的群） |
| 部署队列 / 历史记录页 | 当前 dev_task 的 status + log 已够；历史回溯靠数据库直接查 |

---

## 10. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| SSH 私钥泄露 | 高 — 攻击者拿到部署权 | 私钥仅在 backend 机器上、文件权限 600、deploy 用户不给 sudo |
| 客户在 staging 把数据搞坏 | 中 — staging 数据丢失 | docker-compose.staging.yml 用独立 volume + 独立 DB；README 标注"staging 数据可丢" |
| 同 repo 短时间多次 push | 中 — 频繁触发部署浪费资源 | §5.3 合并 pending head_sha 策略 |
| 部署超时 docker build 卡住 | 中 — backend 资源占用 | 10 分钟硬超时，强 kill |
| GitHub webhook 重复投递 | 低 — 同一个 PR 事件可能被 deliver 多次 | 部署是幂等的（git fetch + reset + docker up）；最多多花一次时间 |
| backend 进程崩溃中断部署 | 低 — DB 状态卡 deploying | §5.4 启动时自动恢复 |
| webhook secret 校验失败 | 低 — 攻击者伪造 webhook 触发部署 | 现有 webhook 已有 secret 校验，复用 |
| `docker compose up` 失败但 `git fetch + checkout` 已完成 | 低 — staging 仓库目录处于 PR 分支但旧版镜像还在跑 | 返回 status=failed + 通知；旧容器仍可访问；下次部署或重试覆盖 |
| `staging_url` 域名 DNS 没指向服务器 | 中 — 客户点链接 404/超时 | 平台不校验；README 提示用户先做 DNS |
| 多 repo 同 SSH 用户但不同 deploy_path | 低 — 路径冲突 | 用户责任，README 提示路径不能复用 |

---

## 11. 测试策略

### 11.1 单元测试 (`backend/tests/test_staging_deploy_service.py`)

| 测试 | 覆盖 |
|---|---|
| `test_deploy_pr_skips_when_staging_url_missing` | 缺任一 staging_* 字段 → status=skipped，不调 SSH，不发企微 |
| `test_deploy_pr_success_path_updates_state_and_sends_card` | mock SSH 返回 0 + mock wechat_client，验证 status/at/log + send_card_link 被调用 |
| `test_deploy_pr_failure_path_sends_text_notification` | mock SSH 返回非 0，验证 status=failed + send_text 被调用 + log 被截断到 200 行 |
| `test_deploy_pr_timeout_kills_process_and_marks_failed` | mock SSH 永远不返回，验证 10 秒（测试用短超时）后被 kill + status=failed |
| `test_deploy_pr_concurrent_same_repo_serializes` | 同 repo 两次并发调 `deploy_pr`，验证 SSH 只被启动一次（第二次合并） |
| `test_deploy_pr_concurrent_different_repos_parallel` | 不同 repo 并发，验证两次 SSH 同时启动 |
| `test_recover_stale_deploys_marks_failed` | 预置 `staging_deploy_status="deploying"` 且 `started_at < now-15min` 的 dev_task → 启动恢复后 status=failed |

### 11.2 端到端测试 (`backend/tests/e2e_staging_deploy.py`)

stand-alone 风格（同其他 e2e_*.py）：
1. 起一个 fixture postgres（或直接连测试库）
2. 插入一条 repo（4 个 staging_* 字段都填）+ project + dev_task
3. mock `staging_deploy_service` 的 SSH 调用（只验证 webhook → 调用 deploy_pr 这条路径）
4. 模拟一次 GitHub `pull_request.opened` webhook POST 到 `/api/webhooks/github`
5. 验证：`dev_task.staging_deploy_status` 最终落到 `success`、企微 send 被调用一次

### 11.3 真机验证（人工，spec 落地后）

1. 配好一台测试服务器（按 §8）
2. 在 admin 后台找一个测试 repo，填 staging_* 字段
3. 让 dev-agent 跑一个简单 issue → 提 PR
4. 看：webhook 收到 → backend 启 SSH → 服务器 docker up → 企微卡片到达 creator
5. 故意把 docker-compose.staging.yml 改坏 → 重试部署 → 看失败通知 + 错误日志

---

## 12. 后续迭代留白（不属本 spec）

- staging 健康检查（service-level health probe）
- 多 repo 共享一台服务器的端口/路径自动管理
- staging 数据自动 reset（如每天凌晨）
- staging URL 加密访问（Cloudflare Access / nginx basic auth）
- dev-agent 自动生成 docker-compose.staging.yml 到用户 repo
- 部署历史 / 多 PR 切换面板
