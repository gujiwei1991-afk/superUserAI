# 群消息图片输入支持 — 设计方案

**日期：** 2026-05-09
**作者：** Claude (Opus) + 用户协同 brainstorming
**状态：** 待用户最终审阅
**前置依赖：** `2026-05-09-group-project-binding-design.md`（群-仓库绑定 + 自然语言对话）

## 1. 背景与目标

### 1.1 当前局限

群-仓库绑定 + 自然语言对话已经上线，但 `wechat_gateway.py:56` 只放行 `msg_type == TEXT` 的消息——用户在群里发图（截图、原型、手画稿）会被静默丢弃。
对真实业务场景（PM 经常截屏指着屏幕说"就像这张图这样"）这是个明显短板。

### 1.2 目标

- 已绑定群里、已开过 active project 的用户在对话中途发图，AI 能"看懂"这张图，并把它纳入对话上下文继续后续问询和 PRD 生成。
- 改动尽量集中在新增组件，**不动 vworkApi 本身**。
- 跨机器（Mac backend ↔ Windows vworkApi）通过七牛云中转图片，避免共享文件系统/打洞内网的复杂度。

### 1.3 核心设计决策（已与用户对齐）

| 决策点 | 选择 |
|---|---|
| 交互方向 | 用户发图 → AI 看（输入） |
| 触发条件 | 已绑定群 + 发言人已有 active drafting project |
| 图片传输管道 | vworkApi-bridge（新组件）→ 七牛云 → backend 拿到 https URL |
| bridge 部署位置 | 1.94.215.136（与 vworkApi 同机，Windows）|
| 图片格式落库 | `messages.media_url` + `messages.media_type` 新字段 |
| LLM 调用方式 | OpenAI/Claude vision messages 标准格式（直传 URL）|
| Ollama 兼容性 | 检测无视觉能力时降级为"图片转描述"再走文字对话 |
| 群内私聊场景 | 本期不支持私聊图片 |

## 2. 架构总览

```
[Mac backend]                            [1.94.215.136 Windows]
    │                                        │
    │  msg_type=14 (image)                   │
    │  GroupImageHandler:                    │
    │   ├ 触发条件检查                       │
    │   ├ POST /fetch-image  ─────────────▶  vworkapi-bridge (new, FastAPI)
    │   │                                   │   ① POST localhost:8989 (type=9001)
    │   │                                   │     vworkApi 写入 C:\tmp\<msg_id>.jpg
    │   │                                   │   ② 七牛 SDK upload C:\tmp\<msg_id>.jpg
    │   │                                   │   ③ 删本地临时文件
    │   │  { url, media_type } ◀────────────│   ④ 返回七牛 URL
    │   │
    │   ├ 写 messages 行 (media_url=url)
    │   ├ PMAgent.chat(history + image URL) → 文字回复
    │   └ 发回群 @发言人
    │
    │ 视觉 LLM API (OpenAI / Claude / Claude CLI 直接传 URL)
```

## 3. 数据模型

### 3.1 `messages` 表新增字段

```python
class Message(Base):
    # ...原有字段...
    media_url: Mapped[str | None] = mapped_column(Text)  # 七牛 URL；文本为 NULL
    media_type: Mapped[str | None]                       # "image/jpeg"、"image/png" 等
```

- 现有 `content` 字段：保留。图片消息 content 写入"[图片]"或可选的简短摘要（不带 URL，URL 在 media_url）。
- text + image 混发：按 vworkApi 推送顺序记多行。

### 3.2 Alembic Migration

单条 migration `add_media_to_messages`：alter table 加两个字段，全部 nullable，无回填。

## 4. vworkapi-bridge 服务

### 4.1 仓库布局

新建顶层目录 `vworkapi-bridge/`：

```
vworkapi-bridge/
├── pyproject.toml         # 独立 Python 项目，最小依赖
├── README.md              # Windows 部署说明
├── .env.example
├── app/
│   ├── __init__.py
│   ├── main.py            # FastAPI 入口
│   ├── config.py          # 七牛 AK/SK + bucket + vworkApi host/port
│   ├── vworkapi_client.py # POST localhost:8989 (type=9001) 同步包装
│   ├── qiniu_uploader.py  # 七牛 SDK 上传 + 返回 URL
│   └── tmp_storage.py     # tmpdir 路径管理 + cleanup
└── tests/
    └── e2e_bridge.py      # stand-alone 风格端到端
```

依赖：`fastapi`, `uvicorn`, `httpx`, `qiniu`, `pydantic-settings`。

### 4.2 协议

```
POST http://1.94.215.136:9100/fetch-image
Content-Type: application/json

{
  "cdn_key": "...",
  "aes_key": "...",
  "size": 230192,
  "img_type": 2,
  "msg_id": "abc123"      // 用作临时文件名
}

→ 200 OK
{
  "url": "https://cdn.example.qiniu.com/sua/<sha256>.jpg",
  "media_type": "image/jpeg",
  "size": 230192
}

→ 502 Bad Gateway
{ "error": "vworkapi_9001_failed: <detail>" }

→ 504 Gateway Timeout
{ "error": "qiniu_upload_timeout" }

→ 413 Payload Too Large
{ "error": "image_too_large", "size": 12345678, "limit": 10485760 }
```

**鉴权：** bridge 监听 `0.0.0.0:9100`，Windows 防火墙只对 backend 出口 IP 开白；请求头要求 `X-Bridge-Token: <env IMAGE_BRIDGE_TOKEN>`。token 不匹配返 401。

### 4.3 内部流程

```python
@app.post("/fetch-image")
async def fetch_image(req: FetchImageRequest, ...):
    verify_token(...)                         # 401 if mismatch
    if req.size > settings.max_image_bytes:   # 413
        ...

    tmp_path = tmp_storage.allocate(req.msg_id)
    try:
        # ① 调本机 vworkApi 9001
        await vworkapi_client.download_image(
            cdn_key=req.cdn_key,
            aes_key=req.aes_key,
            size=req.size,
            img_type=req.img_type,
            save_path=str(tmp_path),
        )

        # ② 上传到七牛
        url, media_type = await qiniu_uploader.upload(tmp_path, key_prefix="sua/")

        return {"url": url, "media_type": media_type, "size": tmp_path.stat().st_size}
    finally:
        tmp_storage.cleanup(tmp_path)         # 删临时文件，无论成败
```

### 4.4 七牛配置

`vworkapi-bridge/.env`：
```
QINIU_AK=...
QINIU_SK=...
QINIU_BUCKET=...
QINIU_DOMAIN=https://cdn.example.qiniu.com
IMAGE_BRIDGE_TOKEN=<random_32_bytes_hex>
VWORKAPI_HOST=127.0.0.1
VWORKAPI_PORT=8989
TMP_DIR=C:\\tmp\\superuserai-images
MAX_IMAGE_BYTES=10485760
```

七牛 key 用 `sua/<sha256>.jpg`，SHA256 取自图片二进制（天然去重——重复内容不重复上传）。

### 4.5 Windows 部署

文档：`vworkapi-bridge/README.md` 写清楚：
- 安装 Python 3.10+、`pip install -e .`
- 配 `.env`
- `uvicorn app.main:app --host 0.0.0.0 --port 9100`
- 防火墙开 9100 给 backend IP

可选：用 `nssm` / `pm2-windows-service` / 计划任务做开机自启（README 给示例命令）。

## 5. backend 改造

### 5.1 文件结构

```
backend/app/
├── services/
│   ├── group_image_handler.py     # 新：图片消息接入入口（与 GroupMessageRouter 平行）
│   └── image_bridge_client.py     # 新：调 bridge 的 HTTP 客户端
├── llm/
│   ├── base.py                    # 修：chat() 签名扩 Multimodal content
│   ├── openai_adapter.py          # 修：透传 list[dict] content
│   ├── claude_adapter.py          # 修：把 OpenAI 风格 image_url 转 Anthropic 风格
│   ├── claude_cli_adapter.py      # 修：参考 claude_adapter
│   └── ollama_adapter.py          # 修：检测视觉能力，不支持时降级转描述
├── agents/
│   └── pm_agent.py                # 修：build_messages 时把 media_url 拼进 user 消息
├── models/
│   └── message.py                 # 修：加 media_url + media_type
├── gateway/
│   └── wechat_gateway.py          # 修：放行 msg_type=14 + 分支到 GroupImageHandler
└── config.py                      # 修：加 image_bridge_url + image_bridge_token
```

### 5.2 LLM 抽象升级

**`BaseLLM.chat`** 签名不变（`messages: list[dict]`），但允许 `content` 是 `str | list[dict]`：

```python
# 文本 message（不变）
{"role": "user", "content": "我想加登录"}

# 多模态 message
{"role": "user", "content": [
    {"type": "text", "text": "用户发了一张图"},
    {"type": "image_url", "image_url": {"url": "https://..."}}
]}
```

各 Adapter：
- **OpenAI**：直接把 list[dict] 透传给 `client.chat.completions.create`，原生支持。
- **Anthropic**：把 OpenAI 风格 `{"type":"image_url","image_url":{"url":"..."}}` 转换成 Anthropic 风格 `{"type":"image","source":{"type":"url","url":"..."}}`。
- **Claude CLI**：参考 anthropic adapter 转换 + 把图片 URL 拼到提示词里（CLI 工具支持 `--image-url` 或类似 flag，按实际能力实现）。
- **Ollama**：用一个 `_supports_vision()` 检测当前 model（白名单 `llava`/`bakllava`/`llama3.2-vision` 等），支持就传 base64；不支持就调一次"描述这张图"得到文字 → 把文字塞回 messages（content 仍是 str）。

### 5.3 PMAgent 调用图片

`PMAgent._build_messages` 改造：遍历 history 时，遇到 `media_url` 非空的 message → 输出 list[dict] content。

```python
def _build_messages(self, project, repo, history):
    messages = [{"role": "system", "content": SYSTEM_PROMPT.format(...)}]
    for item in history:
        if item.media_url:
            messages.append({
                "role": self._normalize_role(item.role),
                "content": [
                    {"type": "text", "text": item.content or "[图片]"},
                    {"type": "image_url", "image_url": {"url": item.media_url}},
                ],
            })
        else:
            messages.append({
                "role": self._normalize_role(item.role),
                "content": item.content,
            })
    return messages
```

### 5.4 GroupImageHandler

新组件，与 `GroupMessageRouter` 平行。`wechat_gateway.receive_message` 在 `is_group + msg_type=14` 时直接 dispatch 到这里：

```python
class GroupImageHandler:
    def __init__(self, db, wechat, bridge_client, llm=None):
        ...

    async def try_handle(self, sender_id, group_id, image_meta) -> bool:
        # ① bound group?
        repo = await self.project_service.get_repo_by_wechat_group_id(group_id)
        if repo is None:
            return False  # ignored

        # ② sender + active drafting project?
        user = await self.session_manager.get_or_create_user_for_bound_group(...)
        if user.role != "admin" and not user.is_active:
            return True  # whitelist gate, silent
        session = await self.session_manager.get_session(user)
        project = await self.project_service.get_project(session.active_project_id) \
            if session.active_project_id else None
        if project is None or project.status != ProjectStatus.DRAFTING.value:
            return True  # ignored (no active drafting context)

        # ③ fetch URL via bridge
        try:
            result = await self.bridge_client.fetch_image(image_meta)
        except BridgeError as exc:
            await self.wechat.send_at_group(group_id, [sender_id],
                f"@{sender_id} 刚才那张图我读不到（{exc.short}）。"
                "能用文字补充一下吗？")
            return True

        # ④ persist + run PMAgent
        await self.project_service.add_message(
            project.id, sender_id, "user", "[图片]",
            media_url=result.url, media_type=result.media_type,
        )
        history = await self.project_service.get_messages(project.id)
        ai_reply = await self.pm_agent.chat(project, repo, history, "")
        await self.project_service.add_message(
            project.id, sender_id, "assistant", ai_reply
        )
        # ⑤ send (with [READY_TO_CONFIRM] strip pipeline)
        ...
```

### 5.5 wechat_gateway 入口

`receive_message` 当前在 line 56 拒绝非 TEXT 消息。改造：

```python
if message.msg_type == VWorkMsgType.TEXT.value:
    # 现有路径
    ...
elif message.msg_type == VWorkMsgType.IMAGE.value:
    # 新分支：仅在群里处理
    if not message.sender:        # 私聊忽略
        return {"status": "ok"}
    # 群消息中图片不需要 @bot（图片场景下 at_list 通常空）
    sender_id = message.sender
    group_id = message.user_id
    image_meta = message.content    # dict with cdn_key/aes_key/size/img_type
    if not isinstance(image_meta, dict):
        return {"status": "ok"}
    background_tasks.add_task(
        _process_bound_group_image_async,
        sender_id, group_id, image_meta, message.msg_id,
    )
else:
    return {"status": "ok"}
```

**注意：群里发图不要求 @bot**——发图就是表达，跟文字消息的"@bot 才回"约定不同。但 `try_handle` 内部还是会校验 `active drafting project`，未在跟 AI 聊天的人发图依然会被忽略。

### 5.6 配置项新增

```python
# config.py
class Settings(BaseSettings):
    # ...
    image_bridge_url: str = ""              # http://1.94.215.136:9100
    image_bridge_token: str = ""            # 与 bridge 端 IMAGE_BRIDGE_TOKEN 一致
    image_bridge_timeout_seconds: float = 30.0
```

## 6. 错误处理与边界

| 场景 | 策略 |
|---|---|
| bridge 5xx / 超时 | 给用户群内回复"刚才那张图我读不到（<原因短句>），能不能用文字描述一下？"。**不**写 message 行 |
| 七牛上传失败 | bridge 内部不重试（fail fast），返 504；backend 同上 |
| 用户在 reviewing/completed 状态发图 | ignore（与文字 chat 一致）|
| 用户发图但还没开 active project | ignore（避免误读群聊截图）|
| 一次发多张图 | vworkApi 推多条 IMAGE，按顺序各处理一条，分别写 message 行；同 turn 内 PMAgent 一起看到 |
| 图片大小超限 | bridge 返 413，backend 提示用户压缩（默认 10MB）|
| 图片格式 vworkApi 不支持 | vworkApi 9001 失败 → 502 |
| Ollama provider 不支持视觉 | adapter fallback 到"图片转描述"（先调一次 LLM 把图描述成文字）|
| 同一图片重复发送 | bridge 用 SHA256 当 key 自动去重，七牛不会重复上传 |
| bridge 不可用（网络/服务挂） | 用户回退提示，admin 可在后台看日志重启 bridge |
| 七牛 URL 公开可访问的隐私顾虑 | URL 是 `<sha256>` 不可猜测；bucket 可设私有 + signed URL（v2 增强）|

### 6.1 日志与可观测

- 接图：`logger.info("group_image_received user=%s group=%s msg_id=%s")`
- bridge 调用：`logger.info("bridge_fetch_image msg_id=%s status=%s latency_ms=%d")`
- 错误：`logger.warning/exception` 带 cdn_key 前 8 位（不打全 key）

## 7. 测试策略

### 7.1 bridge 端

- `vworkapi-bridge/tests/e2e_bridge.py`：
  - 健康检查端点 OK
  - token 缺失 → 401
  - mock vworkApi 9001 + mock 七牛 → 完整 happy path
  - vworkApi 失败 → 502
  - 七牛失败 → 504
  - 大文件 → 413

### 7.2 backend 端

- `backend/tests/e2e_image_input.py` （新）：
  - GroupImageHandler：未绑定群 ignore
  - GroupImageHandler：无 active project ignore
  - GroupImageHandler：bridge 失败时给用户错误回复
  - GroupImageHandler：happy path（mock bridge + stub LLM）→ 写 message 行 + 发回群
- `backend/tests/e2e_pm_chat.py` 扩展：
  - history 中含 media_url 的 message → PMAgent 构造的 messages 是多模态格式
- `backend/tests/e2e_llm_adapters.py` （新）：
  - OpenAI/Anthropic/Ollama adapter 处理多模态 content 的 round-trip

### 7.3 集成

仅手动验证（需要真实七牛 + 真实 vworkApi）：
- 后台绑定群 → 群里 @bot 发文字开 active project → AI 引导 → 用户发一张原型图 → AI 回复体现"看到了图"

## 8. 范围（YAGNI）

### 8.1 本期包含

- migration + Message 字段
- vworkapi-bridge 完整服务
- BaseLLM 多模态接口扩展（OpenAI / Anthropic / Claude CLI / Ollama 四个 adapter）
- GroupImageHandler + wechat_gateway 接入
- 图片群内回复（@发言人）
- 错误回退提示
- 单元 + 集成测试

### 8.2 本期不做

- AI 输出图片（v2）
- 私聊图片（v2）
- 视频/语音/文件（v2）
- 七牛 signed URL（私有 bucket，v2 增强）
- 图片审核（涉政涉黄过滤，v2）
- 图片 EXIF / 地理信息提取（v2）
- 跨多 active project 的图片复用（不同需求间共享同一张图）

## 9. 风险评估

| 风险 | 影响 | 缓解 |
|---|---|---|
| Windows 部署门槛（需要在远端跑 Python）| 中 | 提供 README + nssm 服务化命令 |
| 七牛流量成本 | 低 | 文件不大，群频率不高，初期成本可忽略 |
| LLM 视觉调用成本（OpenAI/Anthropic） | 中 | URL 复用、Ollama 降级、监控 token 用量 |
| bridge 单点故障 | 中 | bridge 简单单文件可快速重启；监控可后续加 |
| 用户隐私 / 业务图泄露七牛 | 中 | 七牛 URL 不可猜（SHA256）；如果敏感可 v2 走私有 bucket+signed URL |
| 图片消息洪水攻击 | 低 | 已绑定群 + active project 双重门槛；上限 10MB |
| Adapter 对多模态的兼容性差异 | 中 | 写充分的 adapter 单测；不支持的 provider fallback |
