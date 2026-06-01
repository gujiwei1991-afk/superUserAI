# Mac mini 运维手册（本机常驻部署）

SuperUserAI 后端、cloudflared 隧道、dev-agent 都以 **LaunchAgent** 形式常驻在这台 Mac mini 上，崩溃自动拉起、登录自启。本文记录这台机器的常驻服务与电源策略，方便排查与重建。

> 配套：整体部署见 [deployment.md](./deployment.md)，故障处理见 [runbook.md](./runbook.md)，运行拓扑（含 Windows 端 qrrobot 入站）见下文「企微入站」。

---

## 1. 三个常驻服务（LaunchAgent）

plist 实际位于 `~/Library/LaunchAgents/`，日志在 `~/Library/Logs/`。仓库里存有一份副本便于重建：[`deploy/macmini/LaunchAgents/`](../deploy/macmini/LaunchAgents/)（重建时拷回 `~/Library/LaunchAgents/` 再 `launchctl bootstrap`）。

| 服务 | Label | 作用 | 端口/日志 |
|---|---|---|---|
| backend | `com.superuserai.backend` | FastAPI 主服务（uvicorn） | :8000 / `superuserai-backend.log` |
| 隧道 | `com.superuserai.cloudflared` | cloudflared 快速隧道 + 自动更新 GitHub webhook URL | `superuserai-cloudflared.log` |
| dev-agent | `com.superuserai.devagent` | 轮询接活、写代码、开 PR | `superuserai-devagent.log` |

### 关键参数（重建时照抄）

**backend** — `ProgramArguments`: `/Users/gujiwei/python/superUserAI/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000`；`WorkingDirectory`: `backend/`；`PATH`: `/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin`。

**cloudflared** — `ProgramArguments`: `/bin/bash /Users/gujiwei/python/superUserAI/scripts/cloudflared-webhook-sync.sh`；`ThrottleInterval`: 10。脚本启动 http2 快速隧道（QUIC 被本机代理拦，必须 `--protocol http2`），抓到 `*.trycloudflare.com` URL 后自动 PATCH 更新 oaSys 的 GitHub webhook（hook id 634610113）。

**dev-agent** — `ProgramArguments`: `/Users/gujiwei/python/superUserAI/.venv/bin/python -m app.main`；`WorkingDirectory`: `dev-agent/`；`PATH` 需含 node bin（claude CLI 是 node 程序）：`/Users/gujiwei/.nvm/versions/node/v22.17.1/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin`。

三者都设 `RunAtLoad=true` `KeepAlive=true`。

### 运维命令

```bash
UID=$(id -u)
# 状态
for s in backend cloudflared devagent; do
  echo -n "$s: "; launchctl print gui/$UID/com.superuserai.$s | grep -m1 'state ='
done
# 重启某个
launchctl kickstart -k gui/$UID/com.superuserai.backend
# 停止 / 重新加载
launchctl bootout gui/$UID/com.superuserai.backend
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/com.superuserai.backend.plist
# 日志
tail -f ~/Library/Logs/superuserai-backend.log
tail -f ~/Library/Logs/superuserai-cloudflared.log   # 含每次隧道 URL + webhook 同步结果
tail -f ~/Library/Logs/superuserai-devagent.log
```

---

## 2. 电源策略（无人值守）

```bash
pmset -g          # 查看当前策略
```

| 项 | 目标值 | 命令 |
|---|---|---|
| 系统睡眠 | 已禁用（`sleep 0`，勿让其睡，否则服务停摆） | 已是 0 |
| 断电自动开机 | **建议开**（停电恢复后自动开机） | `sudo pmset -a autorestart 1` |
| 磁盘睡眠 | 可选关闭 | `sudo pmset -a disksleep 0` |

---

## 3. FileVault 与重启恢复

本机 **FileVault 全盘加密开启**。因此：

- **无法配置自动登录**——开机必须在 FileVault 界面输一次密码解密磁盘（这道关在所有 LaunchAgent 之前）。
- 即 **重启后需人工输一次密码**，之后三个服务全自动恢复。这是保留磁盘加密的安全代价（已选定，不关 FileVault）。

### 重启后恢复清单

1. 在 FileVault 界面输密码解锁（同时登录桌面）
2. 三个 LaunchAgent 自动加载，等约 10~40s
3. 验证：
   ```bash
   curl -s localhost:8000/healthz                                  # backend
   grep -o 'https://[a-z-]*\.trycloudflare\.com' ~/Library/Logs/superuserai-cloudflared.log | tail -1   # 当前隧道URL
   tail -3 ~/Library/Logs/superuserai-devagent.log                # dev-agent 在轮询
   ```

---

## 4. 企微入站（跨机，重启后要留意）

企微消息入站路径：**微信 → vworkApi DLL(Windows 1.94.215.136) → qrrobot.py(同机, :9000/msg) → cloudflared 隧道 → 后端 /msg**。

- qrrobot.py（`/Users/gujiwei/python/qhrobot/qrrobot.py`，跑在 Windows）第 23 行 `SUPERUSERAI_URL` 指向隧道 `/msg`。
- ⚠️ **隧道 URL 会变**：cloudflared 重启会换 URL。GitHub webhook 由 sync 脚本自动更新；但 **qrrobot 的转发地址目前要手动改**（改完重启 qrrobot）。所以本机隧道重启后，记得同步更新 Windows 上 qrrobot 的 URL。
- **企微群里每条发给机器人的消息必须 @机器人（七禾小助手）**，否则 gateway 静默丢弃。

---

## 5. 其它

- 生产部署目标：oaSys → `root@115.227.28.138:/data/qihe/oaSys/docker`，compose `docker-compose.cloud.yml`，项目名 `-p oasys`（在后台仓库配置里设）。
- 部署/webhook SSH key：`/Users/gujiwei/.ssh/id_ed25519`（已配在 backend `.env` 的 `prod_ssh_key_path`）。
