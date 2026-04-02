# SuperUserAI 开发计划

## 项目概述
企业微信 + GitHub 驱动的 AI 协作开发框架。用户在企业微信与 PM AI 对话 → 管理后台审核 → GitHub Issue → Dev AI 编码 → GitHub Actions 部署 → 企业微信通知验收。

## 技术栈
- **后端:** Python 3.12 + FastAPI + SQLAlchemy + Alembic + Redis
- **数据库:** PostgreSQL
- **用户交互:** 企业微信 (vworkApi REST API)
- **代码托管:** GitHub (Issue / PR / Actions / Webhook)
- **AI:** 多模型适配层 (Claude / OpenAI / Ollama)
- **Dev Agent:** 独立 Python 服务
- **管理后台:** FastAPI + Jinja2 (轻量级)
- **部署:** Docker + Docker Compose

---

## Task 1: 项目骨架搭建

**目标:** 搭建项目基础结构、依赖管理、配置系统。

**输出文件:**
```
superUserAI/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI 入口, CORS, 路由注册
│   │   ├── config.py            # Pydantic Settings 配置
│   │   └── database.py          # SQLAlchemy async engine + session
│   ├── pyproject.toml           # 依赖: fastapi, uvicorn, sqlalchemy[asyncio],
│   │                            #   asyncpg, alembic, redis, httpx, pydantic-settings
│   └── .env.example             # 环境变量模板
├── dev-agent/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   └── config.py
│   └── pyproject.toml
├── shared/
│   ├── __init__.py
│   ├── schemas.py               # Pydantic 共享数据结构
│   └── constants.py             # 状态枚举、消息类型常量
├── docker/
│   └── docker-compose.yml       # postgres + redis + backend
└── .gitignore
```

**配置项 (config.py):**
```python
class Settings(BaseSettings):
    # 数据库
    database_url: str
    redis_url: str

    # vworkApi
    vwork_api_host: str       # vworkApi DLL 所在 Windows 机器 IP
    vwork_api_port: int = 8989
    vwork_msg_port: int = 9000  # 本机接收消息的端口

    # GitHub
    github_token: str
    github_webhook_secret: str

    # LLM
    llm_provider: str = "openai"  # openai / claude / ollama
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""

    # JWT
    jwt_secret: str
    jwt_algorithm: str = "HS256"
```

**共享常量 (constants.py):**
```python
class ProjectStatus(str, Enum):
    DRAFTING = "drafting"
    REVIEWING = "reviewing"
    APPROVED = "approved"
    DEVELOPING = "developing"
    DEPLOYED = "deployed"
    ACCEPTANCE = "acceptance"
    COMPLETED = "completed"
    REJECTED = "rejected"

class SessionState(str, Enum):
    IDLE = "idle"
    CHATTING = "chatting"
    CONFIRMING = "confirming"
    SCORING = "scoring"

class VWorkMsgType(int, Enum):
    TEXT = 2
    IMAGE = 14
    FILE = 15
    VIDEO = 23
    VOICE = 16
    CARD_LINK = 13
    # ...

class VWorkSendType(int, Enum):
    SEND_TEXT = 3000
    # ...
```

---

## Task 2: 数据库模型 + 迁移

**目标:** 定义 SQLAlchemy ORM 模型，初始化 Alembic 迁移。

**输出文件:**
```
backend/app/models/
├── __init__.py          # 统一导出所有模型
├── user.py              # users 表
├── repo.py              # repos 表
├── project.py           # projects 表
├── message.py           # messages 表 (对话历史)
├── session.py           # sessions 表 (用户会话状态)
└── feedback.py          # feedbacks 表
backend/alembic/
├── alembic.ini
├── env.py
└── versions/
```

**模型定义:**
```python
# users: id, wechat_user_id(unique), nickname, role(user/admin), created_at
# repos: id, name(别名), github_owner, github_repo, github_token_encrypted,
#         deploy_server, deploy_config(JSONB), created_at
# projects: id, repo_id(FK), title, status, creator_id(FK), approver_id(FK),
#           github_issue_number, github_pr_number,
#           prd_content(TEXT), tech_doc(TEXT),
#           score, feedback, created_at, updated_at
# messages: id, project_id(FK), wechat_user_id, role, content, msg_type, created_at
# sessions: id, wechat_user_id(unique), active_project_id(FK), state, updated_at
# feedbacks: id, project_id(FK), user_id(FK), score, comment, created_at
```

---

## Task 3: LLM 多模型适配层

**目标:** 统一的 LLM 接口，支持切换 Claude / OpenAI / Ollama。

**输出文件:**
```
backend/app/llm/
├── __init__.py
├── base.py              # BaseLLM 抽象类
├── openai_adapter.py    # OpenAI / 兼容 API 适配
├── claude_adapter.py    # Anthropic Claude 适配
├── ollama_adapter.py    # Ollama 本地模型适配
└── factory.py           # LLMFactory.create(config) -> BaseLLM
```

**接口设计:**
```python
class BaseLLM(ABC):
    async def chat(self, messages: list[dict], **kwargs) -> str:
        """单次对话，返回完整回复"""

    async def stream_chat(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        """流式对话，逐步返回内容片段"""
```

**要求:**
- OpenAI adapter 使用 `httpx` 直接调用（不依赖 openai SDK），因为同时要兼容其他 OpenAI 兼容 API（如 DeepSeek、本地 vLLM）
- Claude adapter 使用 `anthropic` SDK
- Ollama adapter 调用本地 Ollama REST API
- factory.py 根据 `config.llm_provider` 自动创建对应实例

---

## Task 4: 企业微信网关 (WeChat Gateway)

**目标:** 接收 vworkApi 推送的消息，解析指令，发送回复。

**输出文件:**
```
backend/app/gateway/
├── __init__.py
├── wechat_gateway.py    # FastAPI 路由: POST /msg 接收消息
├── wechat_client.py     # httpx 客户端: 向 vworkApi 发送消息
└── command_parser.py    # 解析用户指令 (#新需求, #确认, #评分 等)
```

**wechat_gateway.py:**
- 注册路由 `POST /msg`，接收 vworkApi 推送
- 过滤 `is_self_msg=1` 的消息
- 调用 command_parser 解析指令
- 根据指令类型路由到相应处理逻辑
- 兜底：作为普通对话消息转发给 PM Agent

**wechat_client.py:**
```python
class WeChatClient:
    def __init__(self, host: str, port: int):
        self.base_url = f"http://{host}:{port}/api"

    async def send_text(self, user_id: str, msg: str) -> dict:
        """发送文本消息"""

    async def send_card_link(self, user_id: str, title, desc, url, cover_url) -> dict:
        """发送卡片链接消息（用于发送验收链接等）"""
```

**command_parser.py:**
```python
class Command:
    type: str          # new_project / confirm / modify / score / status / list / help / chat
    args: dict         # 解析出的参数

def parse_command(content: str) -> Command:
    """
    #新需求 web-app 我需要登录功能  → Command(type="new_project", args={"repo": "web-app", "desc": "我需要登录功能"})
    #确认                           → Command(type="confirm")
    #修改 加上手机号登录             → Command(type="modify", args={"content": "加上手机号登录"})
    #评分 8 很好用                   → Command(type="score", args={"score": 8, "comment": "很好用"})
    #状态                           → Command(type="status")
    #列表                           → Command(type="list")
    #帮助                           → Command(type="help")
    (其他文本)                      → Command(type="chat", args={"content": "..."})
    """
```

---

## Task 5: 用户会话管理 + PM Agent

**目标:** 管理用户对话状态，PM Agent 与用户多轮对话分析需求。

**输出文件:**
```
backend/app/services/
├── __init__.py
├── session_manager.py   # 用户会话状态管理
├── project_service.py   # 项目生命周期管理
└── message_handler.py   # 消息调度: 根据指令调用对应服务

backend/app/agents/
├── __init__.py
├── pm_agent.py          # PM Agent 核心逻辑
└── prompts/
    ├── __init__.py
    ├── system_prompt.py       # PM AI 系统提示词
    ├── requirement_analysis.py # 需求分析引导 prompt
    └── prd_generation.py      # PRD 生成 prompt
```

**session_manager.py:**
- 根据 `wechat_user_id` 获取/创建会话
- 跟踪用户当前活跃项目 (`active_project_id`)
- 管理会话状态切换 (idle → chatting → confirming → scoring)

**message_handler.py (核心调度):**
```python
async def handle_message(msg: VWorkMessage):
    command = parse_command(msg.content)
    session = await session_manager.get_or_create(msg.user_id)

    match command.type:
        case "new_project":
            # 创建项目 → 切换会话到 chatting → PM Agent 开始对话
        case "chat":
            # 转发给 PM Agent 继续对话
        case "confirm":
            # PM Agent 生成最终 PRD → 项目状态改为 reviewing
        case "modify":
            # PM Agent 根据反馈修改文档
        case "score":
            # 记录评分 → 项目状态改为 completed
        case "status":
            # 查询当前项目进度 → 回复
        case "list":
            # 查询用户所有项目 → 回复列表
        case "help":
            # 回复指令帮助文档
```

**pm_agent.py:**
```python
class PMAgent:
    def __init__(self, llm: BaseLLM):
        self.llm = llm

    async def chat(self, project: Project, user_message: str) -> str:
        """与用户对话，分析需求"""
        # 1. 加载对话历史 (messages 表)
        # 2. 构建 prompt (系统提示 + 仓库上下文 + 对话历史 + 用户消息)
        # 3. 调用 LLM
        # 4. 保存消息记录
        # 5. 返回 AI 回复

    async def generate_prd(self, project: Project) -> str:
        """根据对话历史生成 PRD 文档"""

    async def modify_prd(self, project: Project, feedback: str) -> str:
        """根据用户反馈修改 PRD"""
```

---

## Task 6: GitHub 集成服务

**目标:** 封装 GitHub API 调用，处理 Webhook 回调。

**输出文件:**
```
backend/app/services/
├── github_service.py    # GitHub API 封装

backend/app/api/
├── webhooks.py          # GitHub Webhook 路由
```

**github_service.py:**
```python
class GitHubService:
    async def create_issue(self, repo: Repo, title: str, body: str, labels: list[str]) -> int:
        """创建 Issue，返回 issue_number"""

    async def get_issue(self, repo: Repo, issue_number: int) -> dict:
        """获取 Issue 详情"""

    async def get_repo_structure(self, repo: Repo) -> str:
        """获取仓库文件结构（供 PM Agent 分析用）"""

    async def get_readme(self, repo: Repo) -> str:
        """获取 README 内容"""
```

**webhooks.py:**
```python
@router.post("/webhooks/github")
async def github_webhook(request: Request):
    """
    处理 GitHub Webhook:
    - pull_request.closed (merged) → 更新项目状态
    - workflow_run.completed → 部署完成，通知用户验收
    """
```

---

## Task 7: 管理后台 (Admin Panel)

**目标:** 轻量级 Web 管理界面，供管理层审核需求。

**输出文件:**
```
backend/app/api/
├── admin.py             # 管理后台 API 路由
├── auth.py              # JWT 登录认证

backend/templates/       # Jinja2 HTML 模板
├── base.html            # 基础布局 (Tailwind CDN)
├── login.html           # 登录页
├── dashboard.html       # 仪表盘
├── reviews.html         # 待审核列表
├── review_detail.html   # 需求详情 + 审批按钮
├── projects.html        # 项目列表
├── project_detail.html  # 项目详情
├── repos.html           # 仓库管理
└── settings.html        # 系统设置
```

**审核流程:**
- 管理员在 review_detail 页面查看 PRD + 对话记录
- 点击「批准」→ 后端创建 GitHub Issue → 项目状态 → approved
- 点击「驳回」→ 项目状态 → drafting，通过企业微信通知用户修改

---

## Task 8: Dev Agent 基础版

**目标:** 独立服务，监听 GitHub Issue，自动编写代码，提交 PR。

**输出文件:**
```
dev-agent/app/
├── main.py              # Agent 入口
├── config.py            # 配置
├── worker.py            # 任务监听 (轮询 GitHub API / 接收后端通知)
├── coder.py             # 代码生成核心
├── repo_analyzer.py     # 分析仓库结构、技术栈
├── git_ops.py           # Git clone/branch/commit/push/PR 操作
├── test_runner.py       # 运行测试
└── llm/                 # 复用 LLM 适配层
```

**worker.py:**
```python
async def poll_tasks():
    """定期轮询后端 API 获取待开发任务"""
    # 或者接收后端推送的通知
```

**coder.py:**
```python
class Coder:
    async def develop(self, issue_body: str, repo_path: str) -> list[FileChange]:
        """
        1. 分析 issue 中的开发文档
        2. 分析 repo 现有代码
        3. 规划修改方案
        4. 逐步生成代码
        5. 返回文件变更列表
        """
```

---

## Task 9: GitHub Actions 部署模板 + Docker Compose

**目标:** 提供 CI/CD 模板和本地开发编排。

**输出文件:**
```
github-actions/
└── deploy.yml           # GitHub Actions 模板 (build + SSH deploy)

docker/
└── docker-compose.yml   # 本地: postgres + redis + backend

backend/Dockerfile
dev-agent/Dockerfile
```

---

## Task 10: 集成测试 + 端到端验证

**目标:** 验证完整工作流。

**测试场景:**
1. 模拟 vworkApi 推送消息 → 网关接收 → 指令解析
2. PM Agent 多轮对话 → 生成 PRD
3. 管理审核通过 → 创建 GitHub Issue
4. Dev Agent 收到任务 → 生成代码 → 提交 PR
5. Webhook 回调 → 通知用户验收

---

## 执行顺序

```
Task 1 (骨架) → Task 2 (数据库) → Task 3 (LLM层)
                                       ↓
Task 4 (微信网关) → Task 5 (会话+PM Agent) → Task 6 (GitHub集成)
                                                      ↓
                                              Task 7 (管理后台)
                                                      ↓
                                              Task 8 (Dev Agent)
                                                      ↓
                                    Task 9 (Docker+Actions) → Task 10 (集成测试)
```

**Task 1-3 可以先行，后续 Task 按依赖顺序逐个交给 Codex 编写。**
