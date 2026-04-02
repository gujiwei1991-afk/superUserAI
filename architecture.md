# SuperUserAI - 企业微信 + GitHub 驱动的 AI 协作开发框架

## 1. 系统总览

用户通过**企业微信**与 PM AI 对话提需求，管理层在**管理后台**审核，审核通过后推送到 **GitHub Issue**，Dev AI 自动编码提 PR，**GitHub Actions** 自动部署，最终通过企业微信通知用户验收。

```
┌──────────────────────────────────────────────────────────────────────┐
│                        SuperUserAI Platform                         │
│                                                                      │
│   企业微信(用户)                  管理后台(Web)                       │
│   ┌──────────┐                   ┌──────────┐                       │
│   │ 用户发消息 │                   │ 审核/配置  │                       │
│   │ 需求对话   │                   │ 进度监控   │                       │
│   │ 验收反馈   │                   │ 数据看板   │                       │
│   └─────┬────┘                   └─────┬────┘                       │
│         │                              │                             │
│         ▼                              ▼                             │
│   ┌─────────────────────────────────────────┐                       │
│   │         Backend (FastAPI)                │                       │
│   │                                          │                       │
│   │  ┌──────────┐  ┌──────────┐  ┌────────┐│                       │
│   │  │ WeChat   │  │ PM Agent │  │ GitHub ││                       │
│   │  │ Gateway  │──│  (AI)    │  │ Service││                       │
│   │  │ (vwork)  │  └──────────┘  └───┬────┘│                       │
│   │  └──────────┘                    │      │                       │
│   └──────────────────────────────────┼──────┘                       │
│                                      │                               │
│                            ┌─────────▼─────────┐                    │
│                            │     GitHub          │                    │
│                            │  Issue → PR → Actions│                   │
│                            └─────────┬─────────┘                    │
│                                      │ Webhook                      │
│                            ┌─────────▼─────────┐                    │
│                            │    Dev AI Agent     │                    │
│                            │  (独立服务/机器)     │                    │
│                            └─────────┬─────────┘                    │
│                                      │ PR merge                     │
│                            ┌─────────▼─────────┐                    │
│                            │  GitHub Actions     │                    │
│                            │  SSH → 生产服务器    │                    │
│                            └────────────────────┘                    │
└──────────────────────────────────────────────────────────────────────┘
```

## 2. 核心工作流

```
用户在企业微信发消息 "我需要一个用户登录功能"
         │
    vworkApi 推送到后端 (:9000/msg)
         │
         ▼
    PM AI 分析需求，通过企业微信回复提问
    用户继续回复补充细节（多轮对话）
         │
         ▼
    PM AI 生成需求文档(PRD)
    通过企业微信发送摘要给用户确认
         │
    用户回复 "确认" / "修改xxx"
         │
         ▼
    管理后台显示待审核需求
    管理员审核通过 / 驳回
         │
    审核通过 ▼
         │
    后端调用 GitHub API 创建 Issue
    (包含结构化需求文档)
         │
    Webhook 通知 ▼
         │
    Dev AI 认领 Issue
    → clone 仓库 → 分析代码 → 编写代码
    → 创建 PR (关联 Issue)
         │
    PR 合并 ▼ (自动/手动)
         │
    GitHub Actions 触发
    → Docker build → SSH 部署到服务器
         │
    部署完成回调 ▼
         │
    通过企业微信通知用户：
    "您提的需求已部署完成，请验收：[链接]"
    用户回复评分: "8分，登录按钮位置不太好"
         │
         ▼
    反馈记录入库 → 优化闭环
```

## 3. 四大核心模块

### 模块 1: 企业微信网关 (WeChat Gateway)

基于 vworkApi，实现消息收发的桥梁层。

**架构:**
```
企业微信客户端 ◀──▶ vworkApi DLL (:8989)
                         │
                    POST /msg (:9000)
                         │
                         ▼
              WeChat Gateway (FastAPI)
                    │         │
              路由消息      发送回复
              到 PM Agent   POST :8989/api
```

**核心职责:**
- 接收 vworkApi 推送的消息 (`POST /msg`)
- 过滤自己发的消息 (`is_self_msg=1` 跳过)
- 根据 user_id 关联到对应的项目会话
- 将用户消息路由给 PM Agent 处理
- 将 PM Agent 回复通过 vworkApi 发回给用户
- 处理特殊指令（如 `#新需求`、`#确认`、`#评分:8`）

**消息指令设计:**
| 用户输入 | 系统动作 |
|----------|----------|
| `#新需求 [仓库名]` 或 `#new [仓库名]` | 创建新项目，开始需求对话 |
| (普通文本) | 在当前活跃会话中与 PM AI 对话 |
| `#确认` | 确认 PM AI 生成的需求文档 |
| `#修改 [内容]` | 要求 PM AI 修改文档 |
| `#状态` | 查看当前项目进度 |
| `#评分 [分数] [评语]` | 验收打分 |
| `#列表` | 查看我的项目列表 |
| `#帮助` | 显示指令帮助 |

**群聊模式 (可选):**
- 在指定群中 @机器人 提需求
- 支持 `at_list` 检测是否被 @
- 群聊可用于团队协作讨论需求

### 模块 2: PM Agent（产品经理 AI）

作为后端服务的一部分运行，通过企业微信与用户对话。

**工作流程:**
```
用户: "#新需求 web-app 我需要一个用户登录系统"
  │
  ▼
PM AI: "好的，我来帮你分析这个需求。请问：
  1. 需要支持哪些登录方式？（密码/手机验证码/企业微信扫码）
  2. 是否需要角色权限管理？
  3. 预期用户量大概多少？"
  │
  (多轮对话...)
  │
  ▼
PM AI 分析目标仓库(web-app)的:
  - 现有代码结构和技术栈
  - README / 已有文档
  - 数据库模型
  │
  ▼
PM AI 生成需求文档，通过企业微信发送摘要:
  "📋 需求文档已生成:
   - 功能: 用户登录(密码+手机号)
   - 技术方案: JWT + Redis Session
   - API: 3个新接口
   - 数据库: 新增 users 表

   回复 #确认 提交审核，或 #修改 [内容] 调整"
  │
  ▼
用户: "#确认"
  │
  ▼
系统: "需求已提交管理层审核，审核通过后将自动进入开发。"
```

### 模块 3: 管理后台 (Admin Web Panel)

轻量级 Web 管理界面，供管理层审核和监控。

**页面:**
- `/login` — 管理员登录
- `/dashboard` — 总览（待审核数、开发中、已完成）
- `/reviews` — 待审核需求列表
- `/reviews/:id` — 需求详情（查看 PRD、对话记录、审批）
- `/projects` — 全部项目列表及状态
- `/projects/:id` — 项目详情（Issue、PR、部署、评分）
- `/repos` — 仓库管理（添加/配置 GitHub 仓库）
- `/settings` — 系统设置（AI 模型、vworkApi 配置）

**技术选择:** 可用轻量前端框架，也可以用 Next.js，视复杂度而定。因为管理后台功能较简单，也可以先用 Python 的 FastAPI + Jinja2 模板或 Streamlit 快速搭建。

### 模块 4: Dev Agent（程序员 AI）

独立服务，监听 GitHub 事件，自动编写代码。

**工作流程:**
```
收到通知: 新 Issue（带 superuserai 标签）
     │
     ▼
1. Clone/Pull 目标仓库
2. 读取 Issue 中的开发文档
3. 分析现有代码库结构
     │
     ▼
4. 制定开发计划
5. 创建 feature 分支: feat/issue-{number}
     │
     ▼
6. 编写代码（调用 LLM 逐步生成）
7. 编写测试
8. 本地运行测试
     │
     ▼
9. Git commit + push
10. 创建 PR（关联 Issue, body 中写 "Closes #{number}"）
11. 通过后端 API 更新项目状态
     │
     ▼
PR 通过 CI → 合并 → GitHub Actions 自动部署
     │
     ▼
部署完成 → 后端收到回调 → 企业微信通知用户验收
```

## 4. 项目目录结构

```
superUserAI/
├── backend/                       # Python FastAPI 后端
│   ├── app/
│   │   ├── main.py               # 服务入口
│   │   ├── config.py             # 配置（vworkApi、GitHub、LLM 等）
│   │   ├── api/                  # API 路由
│   │   │   ├── wechat.py         # vworkApi 消息接收 (POST /msg)
│   │   │   ├── admin.py          # 管理后台 API
│   │   │   ├── projects.py       # 项目管理 API
│   │   │   ├── repos.py          # 仓库管理 API
│   │   │   └── webhooks.py       # GitHub Webhook 回调
│   │   ├── gateway/
│   │   │   ├── wechat_gateway.py # 企业微信消息网关
│   │   │   ├── command_parser.py # 指令解析 (#新需求, #确认, #评分 等)
│   │   │   └── wechat_client.py  # vworkApi HTTP 客户端（发送消息）
│   │   ├── agents/
│   │   │   ├── pm_agent.py       # 产品经理 AI
│   │   │   └── prompts/          # Prompt 模板
│   │   │       ├── requirement_analysis.py
│   │   │       ├── prd_generation.py
│   │   │       └── tech_doc_generation.py
│   │   ├── services/
│   │   │   ├── github_service.py # GitHub API 封装
│   │   │   ├── project_service.py# 项目生命周期管理
│   │   │   └── session_manager.py# 用户会话管理
│   │   ├── models/               # SQLAlchemy 数据模型
│   │   │   ├── user.py
│   │   │   ├── project.py
│   │   │   ├── repo.py
│   │   │   ├── message.py
│   │   │   └── feedback.py
│   │   └── llm/                  # 多模型适配层
│   │       ├── base.py           # 抽象接口
│   │       ├── claude_adapter.py
│   │       ├── openai_adapter.py
│   │       └── ollama_adapter.py
│   ├── templates/                # Jinja2 管理后台页面 (或 static/)
│   ├── alembic/                  # 数据库迁移
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
│
├── dev-agent/                     # Dev Agent (独立部署)
│   ├── app/
│   │   ├── main.py               # Agent 入口
│   │   ├── config.py
│   │   ├── worker.py             # 任务监听 (轮询/Webhook)
│   │   ├── coder.py              # 代码生成核心
│   │   ├── repo_analyzer.py      # 代码库分析
│   │   ├── git_ops.py            # Git 操作封装
│   │   ├── test_runner.py        # 测试运行
│   │   └── llm/                  # 多模型适配层(复用)
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
│
├── shared/                        # 共享模块
│   ├── schemas.py                # Pydantic 数据结构
│   └── constants.py              # 共享常量
│
├── github-actions/                # GitHub Actions 模板
│   └── deploy.yml                # 自动部署工作流
│
├── docker/
│   └── docker-compose.yml        # 本地开发编排
│
├── task_plan.md
├── findings.md
├── progress.md
└── architecture.md
```

## 5. 数据库设计 (PostgreSQL)

```sql
-- 企业微信用户（从消息中自动创建）
users (
  id SERIAL PRIMARY KEY,
  wechat_user_id VARCHAR UNIQUE,    -- 企业微信 user_id
  nickname VARCHAR,                  -- 昵称
  role VARCHAR DEFAULT 'user',       -- user / admin
  created_at TIMESTAMP
)

-- 已管理的 GitHub 仓库
repos (
  id SERIAL PRIMARY KEY,
  name VARCHAR,                      -- 仓库别名（用户指令中使用）
  github_owner VARCHAR,
  github_repo VARCHAR,
  github_token_encrypted TEXT,       -- 加密存储
  deploy_server VARCHAR,             -- 部署目标服务器
  deploy_config JSONB,               -- 部署配置
  created_at TIMESTAMP
)

-- 项目（一个需求 = 一个项目）
projects (
  id SERIAL PRIMARY KEY,
  repo_id INTEGER REFERENCES repos(id),
  title VARCHAR,
  status VARCHAR,                    -- drafting/reviewing/approved/
                                     -- developing/deployed/acceptance/completed
  creator_id INTEGER REFERENCES users(id),
  approver_id INTEGER REFERENCES users(id),
  github_issue_number INTEGER,
  github_pr_number INTEGER,
  prd_content TEXT,                  -- PM AI 生成的需求文档
  tech_doc TEXT,                     -- 技术文档
  score DECIMAL,                     -- 用户评分
  feedback TEXT,                     -- 用户反馈
  created_at TIMESTAMP,
  updated_at TIMESTAMP
)

-- 对话消息（用户与 PM AI 的对话历史）
messages (
  id SERIAL PRIMARY KEY,
  project_id INTEGER REFERENCES projects(id),
  wechat_user_id VARCHAR,            -- 企业微信 user_id
  role VARCHAR,                      -- user / assistant
  content TEXT,
  msg_type INTEGER,                  -- vworkApi msg_type
  created_at TIMESTAMP
)

-- 用户会话状态（跟踪用户当前活跃的项目）
sessions (
  id SERIAL PRIMARY KEY,
  wechat_user_id VARCHAR UNIQUE,
  active_project_id INTEGER REFERENCES projects(id),
  state VARCHAR,                     -- idle / chatting / confirming / scoring
  updated_at TIMESTAMP
)
```

**项目状态流转:**
```
drafting → reviewing → approved → developing → deployed → acceptance → completed
    ↑          │                                                 │
    └──────────┘ (驳回)                                          │
    ↑                                                            │
    └────────────────────────────────────────────────────────────┘
                         (不合格,重新迭代)
```

## 6. 部署架构

```
┌──────────────────────────────┐
│  Windows 机器 (企业微信)      │
│                               │
│  ┌────────────────────────┐  │
│  │ 企业微信客户端           │  │
│  │ + vworkApi DLL          │  │
│  │ :8989 (接收指令)         │  │
│  │ 推送消息→Backend :9000  │  │
│  └────────────────────────┘  │
└──────────────┬───────────────┘
               │ HTTP (双向)
               ▼
┌──────────────────────────────────────────────────┐
│  Linux 服务器 A (Backend)                          │
│                                                    │
│  ┌───────────────────────────────────────────┐    │
│  │ FastAPI Backend :8000                      │    │
│  │ + WeChat Gateway (收消息 :9000)            │    │
│  │ + PM Agent (AI)                            │    │
│  │ + Admin Web Panel                          │    │
│  └───────────────────┬───────────────────────┘    │
│                      │                             │
│  ┌───────────┐  ┌────┴──────┐                     │
│  │ PostgreSQL│  │ Redis     │                     │
│  │ :5432     │  │ :6379     │                     │
│  └───────────┘  └───────────┘                     │
└──────────────────────┬───────────────────────────┘
                       │ GitHub API / Webhook
                       ▼
                ┌────────────┐
                │   GitHub    │
                │ Issue/PR    │
                │ Actions     │
                └──────┬─────┘
                       │ Webhook
                       ▼
┌──────────────────────────────────────────────────┐
│  机器 B (Dev Agent)                                │
│                                                    │
│  ┌───────────────┐  ┌──────────────────────────┐ │
│  │ Dev Agent     │  │ 工作空间                  │ │
│  │ Worker        │  │ - Git repos clone         │ │
│  │               │  │ - Docker (测试)           │ │
│  └───────────────┘  └──────────────────────────┘ │
└──────────────────────────────────────────────────┘
                       │ PR merge → Actions
                       ▼
┌──────────────────────────────────────────────────┐
│  机器 C (生产服务器)                                │
│  ┌──────────────────────────────────────────┐    │
│  │ Docker 容器（用户项目运行环境）             │    │
│  └──────────────────────────────────────────┘    │
└──────────────────────────────────────────────────┘
```

**网络拓扑:** vworkApi DLL 运行在 Windows 机器上，后端服务可部署在任意 Linux 服务器上，通过 HTTP 远程调用即可。
- 发送消息: 后端 → `http://<windows_ip>:8989/api`
- 接收消息: DLL 推送 → `http://<backend_ip>:9000/msg`（启动 DLL 时配置回调地址）

## 7. 技术栈汇总

| 层次 | 技术 | 用途 |
|------|------|------|
| 用户交互 | **企业微信 + vworkApi** | 用户对话/通知/验收 |
| 管理后台 | FastAPI + Jinja2 (或 Vue) | 审核/配置/监控 |
| 后端 | Python FastAPI + SQLAlchemy | 核心服务 |
| Dev Agent | Python (独立服务) | 代码生成 + Git |
| AI 模型 | Claude / GPT / Gemini / Ollama | Agent 核心 |
| 代码托管 | GitHub (Issue / PR / Actions) | 需求→代码→部署枢纽 |
| CI/CD | GitHub Actions + SSH | 自动构建部署 |
| 数据库 | PostgreSQL | 持久化存储 |
| 缓存 | Redis | 会话状态 + 队列 |
| 容器化 | Docker | 部署 |

## 8. 开发路线图

### Phase 1: MVP — 跑通核心流程
1. [ ] 后端框架搭建 (FastAPI + DB + 配置)
2. [ ] vworkApi 消息网关 (收发消息)
3. [ ] 指令解析器 (#新需求 #确认 #评分 等)
4. [ ] LLM 多模型适配层
5. [ ] PM Agent (需求对话 + PRD 生成)
6. [ ] 用户会话管理
7. [ ] GitHub 集成 (创建 Issue)
8. [ ] Dev Agent 基础版 (监听 Issue → 编码 → PR)
9. [ ] GitHub Actions 部署模板
10. [ ] Docker Compose 编排

### Phase 2: 管理与审核
1. [ ] 管理后台 (审核页面 + 项目列表)
2. [ ] 审批流程完善
3. [ ] 多仓库管理配置页
4. [ ] 企业微信通知 (部署完成/验收提醒)
5. [ ] 验收打分机制

### Phase 3: 完善与自我优化
1. [ ] Dev Agent 代码质量提升 (代码库分析、测试)
2. [ ] 反馈闭环 (评分→优化 Prompt)
3. [ ] 项目历史知识积累
4. [ ] 群聊模式支持

## 9. 安全考虑

- GitHub Token 加密存储 (Fernet / AES)
- 管理后台登录认证 (JWT)
- vworkApi 端口仅监听 127.0.0.1，不暴露外网
- 代码执行在 Docker 沙箱中隔离
- SSH 部署使用密钥认证
- Webhook 验证 GitHub 签名 (X-Hub-Signature-256)
- 企业微信指令需验证 user_id 权限
