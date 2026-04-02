# Task Plan: 多 AI Agent 协作软件开发框架 (SuperUserAI)

## Goal
构建企业微信 + GitHub 驱动的 AI 协作开发框架：用户在企业微信与 PM AI 对话确定需求 → 管理后台审核 → 推送 GitHub Issue → Dev AI 自动编码提 PR → GitHub Actions 自动部署 → 企业微信通知验收打分 → 反馈闭环。

## Current Phase
Phase 1

## Phases

### Phase 1: 需求分析与架构设计
- [ ] 明确系统核心角色和职责边界
- [ ] 确定技术选型（AI 模型、通信协议、前后端框架）
- [ ] 设计整体系统架构（分布式 Agent 通信拓扑）
- [ ] 设计数据流和工作流引擎
- [ ] 与用户确认方案
- **Status:** in_progress

### Phase 2: 基础设施层开发
- [ ] Agent 通信框架（消息队列 / API 网关）
- [ ] Agent 注册与发现服务
- [ ] 统一配置中心
- [ ] 任务调度引擎
- [ ] 日志与监控系统
- **Status:** pending

### Phase 3: AI Agent 核心开发
- [ ] Agent 基类与插件系统
- [ ] Product Manager Agent（需求分析、文档生成）
- [ ] Developer Agent（代码生成、测试编写）
- [ ] DevOps Agent（构建、部署、通知）
- [ ] 上下文管理与记忆系统
- **Status:** pending

### Phase 4: 前端与 API 层开发
- [ ] 需求提交前端（用户界面）
- [ ] 需求对话界面（用户与 PM Agent 交互）
- [ ] 项目仪表盘（进度跟踪、验收打分）
- [ ] RESTful / WebSocket API
- **Status:** pending

### Phase 5: 工作流与自动化
- [ ] 需求→分析→开发→部署 Pipeline
- [ ] 自动部署流水线（CI/CD 集成）
- [ ] 用户验收通知与打分机制
- [ ] 反馈闭环（评分→优化→迭代）
- **Status:** pending

### Phase 6: 测试与部署
- [ ] 单元测试与集成测试
- [ ] 端到端工作流测试
- [ ] 多机部署方案与文档
- [ ] 性能与安全测试
- **Status:** pending

## Key Questions (待确认)
1. **AI 模型选择**: 使用 Claude API / OpenAI API / 本地模型（如 Ollama）？还是支持多种？
2. **部署环境**: 目标部署环境是什么？Docker + K8s？还是裸机部署？
3. **Agent 间通信**: 偏好 REST API + 消息队列（如 Redis/RabbitMQ）？还是 WebSocket 实时通信？
4. **前端框架**: React / Vue / Next.js？或其他偏好？
5. **后端语言**: 纯 Python？还是需要混合技术栈？
6. **代码生成目标**: Programmer AI 生成什么类型的项目？Web 应用？API？还是通用？
7. **自动部署目标**: 部署到哪里？Docker？云服务？本地服务器？
8. **规模预期**: 多少人/多少 Agent 同时协作？
9. **安全要求**: 是否需要身份认证、权限控制、代码审查机制？
10. **现有基础**: 是否已有可复用的组件或代码？

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| **企业微信 (vworkApi) 作为用户入口** | 用户直接在企业微信里和 PM AI 对话，无需额外前端 |
| **GitHub 作为开发枢纽** | Issue=需求，PR=代码交付，Actions=CI/CD |
| **管理后台仅做审核/配置** | 轻量 Web 面板，FastAPI + Jinja2 即可 |
| **管理层审核环节** | 需求确认后需管理层批准才进入开发 |
| GitHub Actions + SSH 部署 | PR 合并后自动部署到服务器 |
| 多模型适配层 | 灵活切换 Claude/GPT/Gemini/Ollama |
| 一开始就支持多仓库 | 不同项目对应不同 GitHub 仓库 |
| 后端部署在 Linux，远程调用 vworkApi | vworkApi DLL 在 Windows，后端通过 HTTP 远程访问 |
| Dev Agent 独立部署 | 可在单独机器运行，监听 GitHub 事件自动编码 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| (暂无) | - | - |

## Notes
- 这是一个大型系统，需要分阶段逐步实现
- 先确认架构方案，再开始编码
- 每个 Agent 应设计为可独立部署的微服务
