# 群与项目绑定 + 自然语言需求引导 — 设计方案

**日期：** 2026-05-09
**作者：** Claude (Opus) + 用户协同 brainstorming
**状态：** 待用户最终审阅

## 1. 背景与目标

### 1.1 当前状态

- 项目已支持群聊路由：`wechat_gateway.py` 识别群消息，仅 `@bot` 时进入 `MessageHandler`。
- `Project.wechat_group_id` 字段已存在，记录"项目从哪个群发起"，审核通知会优先回流到原群。
- 但群里仍依赖 `#新需求 <仓库> <需求描述>`、`#确认`、`#修改`、`#审核` 等 `#` 命令，对非技术用户不友好。
- 需求文档生成、审核流程已闭环，仅入口形式不符合"用户不专业"的诉求。

### 1.2 目标

让"群"成为长期承载需求对话的载体：
- **群与仓库 1:1:1 绑定**（一个群 = 一个仓库 = 一个本地目录）。
- 群里支持**自然语言**对话提需求，AI 主动引导补充细节。
- AI 输出"开发方案小结"后，必须用户**明确说"确认"**才进入审核（"确认门禀"）。
- 管理员审核仍走 `#审核` 命令保留稳健性，并新增对自然语言审核语句的支持。
- **改动局部化**：仅在已绑定的群里启用自然语言模式；私聊、未绑定群维持现状。

### 1.3 核心设计决策（已与用户对齐）

| 决策点 | 选择 |
|---|---|
| 绑定粒度 | 群 ↔ 仓库（1:1:1） |
| 交互风格 | 自然对话 + 「确认」门禀 |
| 绑定建立 | 仅管理后台手动 |
| 多人并发 | 按发言人隔离（每个用户独立 active project） |
| 群权限 | 绑定即授权（白名单也由绑定群暗中开启） |
| 生效范围 | 仅在已绑定群里 |
| 意图识别 | 启发式 + LLM 兑底（方案 A） |
| 自然语言审核 | 本期包含 |

## 2. 架构总览

```
[企业微信群] @bot 自然语言消息
    ↓ vworkApi POST /msg
[wechat_gateway.receive_message]
    │
    ├── is_group?  no  → 旧路径（parse_command → MessageHandler.handle）
    │   yes ↓
    ├── 查 Repo.wechat_group_id == group_id
    │       ├── None    → 旧路径（向后兼容未绑定群）
    │       └── repo ↓  → 新路径
    │
    ├── [GroupMessageRouter.process(sender, group_id, repo, content)]
    │       │
    │       ├── 自动激活/创建 user（白名单跳过）
    │       ├── [GroupIntentClassifier.classify(content, session, project)]
    │       │   │
    │       │   ├── 第一层：启发式（正则、关键词、状态联动）
    │       │   │       ├── # 开头 → 旧 parse_command 兜底
    │       │   │       ├── 太短/纯标点 → OTHER（静默）
    │       │   │       ├── 状态查询关键词 → STATUS
    │       │   │       ├── confirm 候选词 + 有 active drafting → CONFIRM_CANDIDATE
    │       │   │       ├── modify 候选词 + reviewing → MODIFY
    │       │   │       ├── 没有 active project → NEW_PROJECT
    │       │   │       └── 兜底 → CHAT
    │       │   │
    │       │   └── 第二层（仅 CONFIRM_CANDIDATE 触发）：LLM 双重核对
    │       │           prompt = (PRD 摘要 + 最近 5 条消息 + 当前消息)
    │       │           output = "yes" | "no" | (其他视为 no)
    │       │           yes → CONFIRM；no → CHAT
    │       │
    │       └── 路由到 MessageHandler 内部方法（NEW_PROJECT/CHAT/CONFIRM/MODIFY/STATUS/REVIEW）
    │
    ↓
[现有 PMAgent / project_review / GitHub 链路（基本不变）]
```

## 3. 数据模型

### 3.1 `repos` 表新增 3 字段

```python
class Repo(Base):
    __tablename__ = "repos"
    # ...原有字段保持不变...
    wechat_group_id: Mapped[str | None] = mapped_column(unique=True, index=True)
    wechat_group_bound_at: Mapped[datetime | None]
    wechat_group_bound_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
```

- `unique=True + nullable=True`：保证一个群只绑一个仓库；未绑定的仓库正常存在。
- `wechat_group_bound_at` / `wechat_group_bound_by`：审计字段，便于排错。

### 3.2 `Project.wechat_group_id` 字段保留

不变。语义是**项目快照**——记录该需求从哪个群发起，与 `Repo.wechat_group_id` 通常一致，但保留快照能优雅处理"群解绑/换绑后旧项目仍回流原群"的场景。

### 3.3 Alembic Migration

单条 migration `add_wechat_group_to_repos`：alter table + 唯一索引。无需数据回填，新增字段全部为 NULL，等管理员逐个绑定。

## 4. 后台绑定流程

### 4.1 UI 位置

复用现有仓库管理区域（settings 页或 repos 列表），加"群绑定"列：

```
[sandbox]   github_owner/repo                                未绑定 [+ 绑定企业微信群]
[xiaowei]   xy/xiaowei-app   群: 7821xxxx (2026-04 由 admin 绑定)  [换绑] [解绑]
```

### 4.2 API

- `POST   /admin/repos/{repo_id}/bind-group` — body `{"group_id": "...", "note": "..."}`
- `DELETE /admin/repos/{repo_id}/bind-group`

### 4.3 行为

| 操作 | 行为 |
|---|---|
| 绑定 | 校验 group_id 非空、unique 不冲突；写入 3 个字段；给该群发欢迎消息："本群已绑定 [repo_name] 仓库。@我并直接说出你的需求即可，例如：'我想加个登录功能'。" |
| 解绑 | 清空 3 个字段；可选给群发"已解绑"提示 |
| 换绑 | 旧群发解绑通知 + 新群发欢迎消息 |
| 重复绑定同一对 (repo, group) | 视为 no-op，返回 200 |
| group_id 已被其他仓库占用 | 返回 4xx + 提示 |

## 5. 核心：消息路由 + 意图识别

### 5.1 文件结构

```
backend/app/services/
├── group_intent.py              # 启发式 + LLM 兑底意图分类器（新）
├── group_message_router.py      # 绑定群消息路由（新）
└── message_handler.py           # 现有，少量重构（暴露内部方法）
backend/app/agents/prompts/
└── intent_prompts.py            # 意图判定 prompt（新）
```

### 5.2 入口分支

`wechat_gateway.receive_message` 在剥离 `@bot` 前缀后，**调用 `parse_command` 之前**插入：

```python
if is_group:
    repo = await get_repo_by_wechat_group_id(group_id)
    if repo is not None:
        background_tasks.add_task(
            process_bound_group_message_async,
            sender_id, group_id, repo.id, content_text
        )
        return {"status": "ok"}
# fallback to legacy parse_command path
```

### 5.3 Intent 枚举

```python
class Intent(Enum):
    NEW_PROJECT = "new_project"   # 用户没有 active project → 默认新需求
    CHAT       = "chat"           # 多轮对话，给当前 active project 补充
    CONFIRM    = "confirm"        # 用户明确同意进入审核
    MODIFY     = "modify"         # 用户对已生成的 PRD 提修改意见
    STATUS     = "status"         # "现在到哪一步了 / 怎么样了"
    REVIEW     = "review"         # admin 自然语言审核（"通过项目 #123" / "拒绝项目 #123 理由是xxx"）
    OTHER      = "other"          # 闲聊、纯表情等，静默不回
```

### 5.4 第一层启发式

| 规则（按顺序短路） | 输出 |
|---|---|
| `content.startswith("#")` | 走旧 `parse_command` 路径 |
| `len(content.strip()) < 2` 或纯标点/单 emoji | `OTHER` |
| `user.role == "admin"` 且匹配正则 `^(通过\|拒绝)项目\s*#?\d+(\s+理由是\s*.+)?$`（容忍前后空白） | `REVIEW`（解析 project_id 与可选 reason） |
| 含 "进度" / "状态" / "到哪" / "怎么样" / "进展" | `STATUS` |
| 已有 active drafting/reviewing project + 含 confirm 候选词："确认" / "通过" / "同意" / "可以了" / "开发吧" / "没问题" / "就这样" | `CONFIRM_CANDIDATE` → 第二层 |
| 已有 active reviewing project + 含 modify 候选词："改" / "调" / "不对" / "重新" / "再" | `MODIFY` |
| `session.active_project_id is None` | `NEW_PROJECT` |
| 兜底 | `CHAT` |

### 5.5 第二层 LLM 双重核对（仅 CONFIRM_CANDIDATE）

`backend/app/agents/prompts/intent_prompts.py:CONFIRM_VERIFY_PROMPT`：

```
你是用于核对用户是否同意进入开发的 AI 守门员。

下面是某项目的需求摘要 / 当前 PRD 草稿：
{summary}

最近 5 条对话：
{history}

用户刚刚发的消息：
"{content}"

请回答：用户是否在明确同意进入"开发审核"阶段？
- 答 yes 当且仅当用户的"同意"是确定的、无保留的（如"确认"、"开发吧"、"可以了"）
- 答 no 当用户表达不确定、提问、或讨论中（如"我觉得可以"、"应该差不多吧"、"这样确认下"、"确认一下没问题再说"）

只输出一个词：yes 或 no。
```

模型选择：默认与 PMAgent 同 provider 的轻量模型（如 GPT-4o-mini / Haiku），具体由 `config.py` 的 `INTENT_LLM_MODEL` 配置项控制。

### 5.6 路由到 handler

| Intent | Handler |
|---|---|
| NEW_PROJECT | 抽出来的 `_handle_new_project_internal(user, session, repo, desc)`——repo 由群绑定关系直接给出，不再要求用户输入仓库别名 |
| CHAT | `_handle_chat_internal` |
| CONFIRM | `_handle_confirm_internal` |
| MODIFY | `_handle_modify_internal(content as feedback)` |
| STATUS | `_handle_status_internal` |
| REVIEW | `_handle_review_internal(project_id, decision, reason)` |
| OTHER | `return ""`（不发送任何回复，避免群里 spam） |

### 5.7 PMAgent 的"摘要+确认门"机制

PMAgent 内部增加状态判定：每次 `chat()` 后，若对话已成熟（基于消息条数 ≥ N，或 PMAgent 输出的特定标记 `[READY_TO_CONFIRM]`），追加一段固定文案：

```
我这样理解你的需求：
• <要点 1>
• <要点 2>
• <要点 3>

如果没问题，回复"确认"我就提交审核。
```

**关键约束：**
- `[READY_TO_CONFIRM]` 标记字符串绝不能泄漏到给用户的最终回复里——`MessageHandler` 输出前 strip。
- 标记本身仅用作 PMAgent 自我判断"是否已展示了确认门"，不参与 Intent 判定。

## 6. 审核流程

### 6.1 现有审核闭环（不变）

- `#审核 <id> 通过/拒绝 [理由]` 命令保留，admin 在群、私聊均可发。
- 审核通知优先发到 `project.wechat_group_id`（已实现，无需改动）。
- `notify_creator_approved` / `notify_creator_rejected` 在新模式下仍生效——NEW_PROJECT 流程会写 `wechat_group_id`。

### 6.2 新增：自然语言审核

绑定群里 admin 发"通过项目 #123" / "拒绝项目 #123 理由是测试不充分"时：
- 启发式直接路由到 REVIEW intent，不走 LLM。
- 仅当 `user.role == "admin"`、消息含数字（项目 ID）+ "通过"/"拒绝" 关键词。
- 解析 project_id 与 reason，调用现有 `_handle_review_internal`。

## 7. 错误处理与边界

| 场景 | 策略 |
|---|---|
| **绑定群里第一次出现的成员**（系统未见过的 wechat_user_id） | 自动创建 user 并 `is_active=true`——绑定群本身充当白名单凭据。日志：`auto_activate user=%s via bound_group=%s repo=%s` |
| 未绑定群 / 私聊里第一次出现的用户 | 沿用现有白名单闸：`is_active=false`，drop message |
| 群已绑定但仓库被后台删除 | 给群发"本群绑定的仓库已被删除，请联系管理员"+静默 |
| 群解绑后用户继续 @bot | 走旧 `parse_command`，自然降级到 `_handle_help` |
| LLM 第二层判定超时/异常 | fail-safe：保守判定为 `CHAT`，不进入审核 |
| LLM 答非 yes/no（"unsure" / 其他文本） | 视为 no → 提示"我没完全确定你是否同意，请明确回复『确认』或继续讨论" |
| 用户在 reviewing 状态又表达新需求意图 | 启发式优先：reviewing 项目存在 → CHAT/MODIFY；要真正开新需求需明确说"开新需求"或用 `#新需求` 旧命令兜底 |
| 同一用户群里消息 burst | `SessionManager` 给 active_project_id 写操作加 `SELECT ... FOR UPDATE` 行锁 |
| group_id 后台绑定时已被其他仓库占用 | 4xx + 提示文案 |
| PMAgent 输出 `[READY_TO_CONFIRM]` 标记 | `MessageHandler` 输出前 strip |
| 群成员被踢出群 | 不主动回收 `is_active`——本期不做自动同步。需要回收时 admin 在后台手动改。 |
| 绑定群里有 admin 用户 | 仍按 admin 处理（`role=='admin'` 优先），不会被自动激活逻辑影响 |

### 7.1 日志与可观测

- 意图判定：`logger.info("intent_classify user=%s group=%s heuristic=%s llm=%s final=%s")`
- 已绑定群命中：`logger.info("bound_group_route group=%s repo=%s sender=%s intent=%s")`
- 自动激活：`logger.info("auto_activate user=%s via bound_group=%s repo=%s")`
- LLM 第二层调用次数 / latency：用 `logger.info` 打点，后续可接监控

## 8. 测试策略

### 8.1 单元测试

| 测试文件 | 覆盖范围 |
|---|---|
| `tests/services/test_group_intent.py` | 启发式各分支（confirm 候选、modify、status、admin review 模式、闲聊兜底）；LLM 第二层 mock yes/no/unsure；与 active_project 状态的联动 |
| `tests/services/test_group_message_router.py` | 绑定群消息分支：未绑定降级、首次发言者自动激活、admin 跳白名单、PMAgent 摘要+确认门、CONFIRM 第二层 mock 通过/拒绝、PMAgent 标记 strip |
| `tests/api/test_admin_repo_bind.py` | 后台 bind/unbind/换绑 endpoint：成功、unique 冲突、非法 group_id、解绑后查询返回 None |
| `tests/services/test_message_handler_existing.py` | 回归：`#新需求` `#确认` `#修改` `#审核` 等旧命令不受影响（不能 break 老用户） |

### 8.2 集成测试

| 测试文件 | 覆盖范围 |
|---|---|
| `tests/integration/test_bound_group_e2e.py` | 端到端：管理员后台绑定群 → 群里 @bot "我想加个登录" → AI 引导追问 → 用户回"加上 OAuth" → AI 摘要 → 用户回"确认" → 项目进入 reviewing → 群里收到审核通知 → 管理员 `#审核 通过` → GitHub Issue 创建 → 用户群里收到通过通知 |
| `tests/integration/test_concurrent_users.py` | 同一群里两个用户同时发不同需求消息，各自进各自的 active project，互不污染 |

### 8.3 LLM mock 策略

- 单元测试里 LLM 调用全部 mock（patch `pm_agent.classify_confirm` / `pm_agent.chat`）
- 集成测试用 `LLMProvider="dummy"`（`config.py` 里已有的测试桩）

### 8.4 关键不变量

1. 未绑定群消息走旧路径，行为字节级一致
2. 绑定群里 `#新需求 ...` 旧命令仍能工作（向前兼容）
3. CONFIRM 在 LLM 第二层失败时**不会**让项目进入 reviewing
4. 同一 group_id 不能被绑定到两个不同 repo（DB unique 约束 + 应用层 4xx）

## 9. 范围（YAGNI）

### 9.1 本期包含

- `repos` 表 3 字段 + alembic migration
- 后台 bind/unbind/换绑 UI + API
- `GroupIntentClassifier` 启发式 + LLM 兑底
- `GroupMessageRouter` 路由层
- `MessageHandler` 内部方法重构（暴露 `_handle_*_internal`）
- PMAgent 摘要 + `[READY_TO_CONFIRM]` 机制
- 自动激活白名单（绑定群首发言者）
- 自然语言审核（admin "通过/拒绝项目 #N"）
- 单元 + 集成测试

### 9.2 本期不做（明确排除）

- 群成员变动（踢人/加人）的自动同步——vworkApi 不一定推群成员事件
- 一仓库多群（M:1）支持
- 私聊里的自然语言模式
- LLM 全消息分类（方案 B）
- 群-仓库绑定的群成员自助申请
- 多语言意图词表
- 群里查看 PRD 全文的命令（用户可走后台或 `#状态` 看摘要）

## 10. 配置项新增

```python
# config.py
class Settings(BaseSettings):
    # ...原有...
    INTENT_LLM_MODEL: str = "gpt-4o-mini"  # 第二层 LLM 模型
    INTENT_LLM_TIMEOUT_SECONDS: float = 5.0  # 超时 fail-safe to CHAT
    GROUP_BOUND_AUTO_ACTIVATE: bool = True  # 绑定群自动激活白名单（生产可关）
    PMAGENT_READY_HINT_AFTER_TURNS: int = 3  # 至少 N 轮对话后才考虑追加摘要
```

## 11. 风险评估

| 风险 | 影响 | 缓解 |
|---|---|---|
| LLM 第二层成本累积 | 中 | 仅 CONFIRM_CANDIDATE 触发，预估 < 10% 消息走 LLM；可监控 |
| 启发式词表覆盖不全 → 误判 | 中 | 测试集合覆盖典型表达；有问题随时扩词表（不是设计性问题） |
| 自动激活白名单引入安全风险 | 中 | 企微群已是受信任的内部协作环境；如担心可用 `GROUP_BOUND_AUTO_ACTIVATE=False` 回退到原行为 |
| 多用户并发导致 active_project_id 竞争 | 低 | 行锁兜底 |
| `[READY_TO_CONFIRM]` 标记泄漏 | 低 | 单测 + 输出层 strip |
| PMAgent 摘要质量不稳定 | 中 | 现有 PMAgent 已能写 PRD，"摘要"只是更轻量版本，prompt 微调即可 |
