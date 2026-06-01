# vwork-msg-forwarder

把 vworkApi DLL 推来的微信消息转发到 Mac mini 上的 SuperUserAI 后端。

**为什么需要它**：DLL 收到消息后只会 POST 到本机 `127.0.0.1:9000/msg`（接收服务必须和 DLL 同机）。后端跑在 Mac mini、藏在家庭 NAT 后，DLL 够不到。本转发器与 DLL 同机监听 `:9000/msg`，把消息转发到后端（经 cloudflared 隧道）。

```
微信消息 → vworkApi DLL → 127.0.0.1:9000/msg (本转发器) → https://<隧道>/msg (Mac mini 后端)
```

## 部署（在 vworkApi 所在的 Windows 机器 1.94.215.136 上）

```bat
:: 与 vworkapi-bridge 同一台机器，Python 3.10+
cd <放置目录>\vwork-msg-forwarder
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
notepad .env          :: 填 TARGET_MSG_URL（当前隧道 /msg）和 FORWARD_SECRET（随机串）

:: 启动（DLL 推 127.0.0.1:9000，故监听本机即可）
uvicorn app:app --host 0.0.0.0 --port 9000
```

> ⚠️ 启动前确认 **9000 端口没被占用**——如果以前有旧的接收服务/后端在这台机器的 9000 上跑，先停掉。

长期运行用 `nssm` 注册为服务（同 vworkapi-bridge 做法）：

```bat
nssm install vwork-msg-forwarder "C:\path\to\.venv\Scripts\uvicorn.exe" "app:app --host 0.0.0.0 --port 9000"
nssm set vwork-msg-forwarder AppDirectory "C:\path\to\vwork-msg-forwarder"
nssm start vwork-msg-forwarder
```

## 验证

```bat
:: 本机健康检查（应返回当前 target）
curl http://127.0.0.1:9000/healthz
```

然后在企微群里发消息，看 Mac mini 后端日志是否出现 `POST /msg`。

## 自愈（可选，解决隧道换 URL）

隧道重启会换 URL。Mac mini 端的 `scripts/cloudflared-webhook-sync.sh` 可在隧道起来后，
自动调用本服务的 `POST /set-target` 把新 `/msg` 地址推过来——前提：

1. 本服务对 Mac mini 公网可达（在 Windows 防火墙 / 云安全组放行入站 9000）
2. `.env` 里设了 `FORWARD_SECRET`
3. Mac mini 的 sync 脚本里配上本服务的公网地址 + 同一个 secret

未启用自愈时，隧道换 URL 后需手动改 `.env` 的 `TARGET_MSG_URL` 并重启本服务
（或直接 `curl -X POST .../set-target` 更新）。

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/msg` | DLL 推消息进来 → 转发到后端；始终回 200（防 DLL 重试风暴） |
| POST | `/set-target` | 更新转发目标，需 `X-Forward-Secret` 头匹配 `FORWARD_SECRET` |
| GET | `/healthz` | 健康检查，返回当前 target |
