# Findings & Decisions

## Requirements
- 分布式多 AI Agent 协作系统
- 三种核心角色：需求提出者（人类）、产品经理 AI、程序员 AI
- **用户通过企业微信与 PM AI 对话**（使用 vworkApi）
- 需求确定后经管理层审核，推送到 GitHub Issue
- Dev AI 根据 Issue 编写代码，提交 PR
- GitHub Actions 自动部署到服务器
- 通知用户验收并打分
- 系统具备自我完善能力（反馈闭环）
- 一开始就支持多仓库

## 已确认技术选型
| 类别 | 选择 | 说明 |
|------|------|------|
| 用户交互 | **企业微信 (vworkApi)** | 用户在企业微信里直接和 PM AI 对话 |
| AI 模型 | 多模型适配 | 统一 LLM 接口，支持 Claude/GPT/Gemini/Ollama |
| 代码托管 | GitHub (Issue/PR/Actions) | 核心枢纽 |
| 部署方式 | GitHub Actions + SSH | PR 合并后自动部署 |
| 后端框架 | Python FastAPI | 高性能异步框架 |
| 部署方案 | Docker 容器化 | 每个项目打包 Docker 镜像 |
| 使用规模 | 个人/小团队 (1-5人) | 先原型验证 |

## vworkApi 技术摘要

### 概述
- 基于 PC 端企业微信封装的 REST 风格接口
- 通过 DLL 注入企业微信客户端实现
- 运行在 Windows 上（注入工具为 .exe）

### 通信模型
```
[你的后端服务 :9000]  ◀──POST /msg──  [vworkApi DLL]  ──▶  [企业微信客户端]
[你的后端服务]  ──POST /api──▶  [vworkApi DLL :8989]  ──▶  [企业微信客户端]
```

### 发送消息 (POST http://127.0.0.1:8989/api)
| type 值 | 功能 |
|---------|------|
| 3000 | 发送文本消息 |
| (其他) | 图片、GIF、文件、视频、名片、小程序、卡片链接、位置、语音等 |

**发送文本示例:**
```json
{ "type": 3000, "user_id": "788xxx", "msg": "你好" }
```

### 接收消息 (DLL 推送到你的 HTTP 服务 POST http://127.0.0.1:9000/msg)
**推送数据结构:**
```json
{
  "type": 100,              // 推送类型固定100
  "msg_type": 2,            // 消息类型: 2=文本, 14=图片, 15=文件...
  "msg_id": "10018000",
  "user_id": "7881300000",  // 聊天用户ID/群ID
  "waiter_id": "2580800000",// 客服ID
  "at_list": [],            // 群消息@列表
  "content": "消息内容",     // 根据msg_type不同格式不同
  "sender": "7881300003",   // 群消息发送者ID
  "time_stamp": 1682944354,
  "is_self_msg": 0,         // 0=别人发的 1=自己发的
  "self_user_id": "168888888888",
  "port": 8989              // DLL端口号
}
```

**msg_type 类型:**
| 值 | 类型 |
|----|------|
| 2 | 文本消息 |
| 14 | 图片消息 |
| 29 | GIF消息 |
| 15 | 文件消息 |
| 23 | 视频消息 |
| 41 | 名片消息 |
| 78 | 小程序消息 |
| 141 | 视频号消息 |
| 13 | 卡片链接消息 |
| 6 | 位置消息 |
| 16 | 语音消息 |

### 其他能力
- 好友/群/成员/公司/部门列表查询
- 好友操作（添加、删除等）
- 群操作（创建群、邀请、踢人等）
- 标签操作
- 多开支持（不同端口号）
- CDN 文件上传下载

### 关键约束
- **必须运行在 Windows 上**（DLL 注入）
- 需安装指定版本的企业微信客户端
- vworkApi DLL 运行在本地 127.0.0.1
- 如果后端服务不在同一台 Windows 机器上，需要做端口转发或网络桥接

## Resources
- 项目目录: /Users/gujiwei/python/superUserAI
- vworkApi 文档: https://www.showdoc.com.cn/mrsanshui/9693807382610096

---
*Update this file after every 2 view/browser/search operations*
