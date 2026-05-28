# 反馈回路 / 自我完善 — 设计方案

**日期：** 2026-05-28
**作者：** Claude (Opus) + 用户协同 brainstorming
**状态：** 已对齐两项关键决策（"派活给 dev-agent 改代码" + 不引入低分自动触发）

---

## 1. 背景与目标

### 1.1 现状

`feat/acceptance-scoring-closure` 落地后，部署成功 → `ACCEPTANCE` → 用户 `#评分` → `COMPLETED` 已经完整。但「用户在 ACCEPTANCE 阶段说『这个按钮坏了』时怎么办」这个核心问题还没有解决：

- `#修改` 当前只会调 `PMAgent.modify_prd` 改 PRD，对 ACCEPTANCE 阶段毫无意义
- 项目验收之后用户**只有两条路**：要么评分关单（`COMPLETED`），要么完全推倒发起 `#新需求`
- 没有自动驱动 dev-agent 修复代码的闭环 — 整个"AI 自我完善"环节断在用户和 dev-agent 之间

### 1.2 目标

让 `#修改 <说明>` 在 ACCEPTANCE / DEPLOYED 阶段自动派 dev-agent 改代码：

- 同一个 project 多轮迭代，不创建新 Project 行
- 每轮迭代新建一个 GitHub Issue，dev-agent 通过现有的 `/tasks/claim` 自然接走
- 项目状态翻回 `APPROVED`，进入完整的 DEVELOPING → STAGED → ACCEPTANCE 子循环
- 用户能在企微上看到"已派 AI 修复"反馈

### 1.3 核心设计决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 低分（≤N）是否自动触发 | **否，仅 `#修改` 手动触发** | 避免误启动开发；用户拍板 |
| 派活路径 | **复用现有 `/tasks/claim` poll** | dev-agent 不需要改；后端只需把 project flip 回 APPROVED + 挂新 issue_number |
| 每轮是否新建 Project | **否，同一 Project 多轮 DevTask** | 保留评分历史与上下文；issue 号迭代会被 `project_dev_logs` 记下 |
| 旧 Issue 处理 | **不动**（GitHub 上仍可访问） | 不引入复杂的"关闭旧 issue"逻辑；如需手工清理交给运维 |

---

## 2. 架构

### 2.1 共用 helper：`request_fix_iteration`

新增到 `app/services/project_review.py`（与 `create_issue_for_project` 并列）。

```python
async def request_fix_iteration(db, *, project, repo, fix_description) -> int:
    # 1. 数当前是第几轮 fix（看 project_dev_logs 里 "fix iteration #" 前缀的行数）
    # 2. 拼新 issue body：
    #    ## 修复需求（第 N 轮）
    #    <fix_description>
    #    ## 原 PRD
    #    <project.prd_content>
    #    --- meta footer
    # 3. github.create_issue → 拿到 new issue_number
    # 4. project.github_issue_number = new_issue_number
    # 5. project.status = APPROVED
    # 6. 写一行 project_dev_log: "fix iteration #N: issue #X — <desc[:200]>"
    return new_issue_number
```

**为什么能让 dev-agent 自然接走**：claim_task 的查询条件就是 `Project.status == APPROVED AND github_issue_number IS NOT NULL AND 无活跃 dev_task`。我们恰好满足这三条。

### 2.2 `_handle_modify` 分流

```python
if project.status == COMPLETED:
    return "已完成，请发起 #新需求"

if project.status in {ACCEPTANCE, DEPLOYED}:
    # 新增分支：派 dev-agent 改代码
    return await self._dispatch_fix_iteration(project, repo, feedback, wechat_user_id)

# 原有分支：REVIEWING/REJECTED → 改 PRD
```

`_dispatch_fix_iteration`：
- 调 `request_fix_iteration`
- 失败 → log + 用户友好提示「派发修复任务失败，请稍后重试」
- 成功 → 在 messages 表落两条记录（user + assistant），返回「已派 AI 开始修复（issue #N），完成后再次通知验收」

### 2.3 用户视角的完整循环

```
#新需求 → 沟通 → #确认 → 审核通过 → DEVELOPING → 提 PR → STAGED → 合并 → ACCEPTANCE
                                                                              ↓
                                                    #评分 X Y ←─────────────┤
                                                       ↓                     ↓ #修改 <说明>
                                                  COMPLETED              APPROVED
                                                  （终止）                  ↓
                                                                     dev-agent claim
                                                                          ↓
                                                                    (回到 DEVELOPING)
```

---

## 3. 故意不做的事

| 项 | 不做的理由 |
|---|---|
| 低分自动触发 | 用户拍板；避免误启动 |
| 关闭旧 Issue | YAGNI；GitHub 上仍可见，不引入二次 API 调用 |
| 每轮迭代独立 Project | 评分历史 / 上下文应该归属同一 Project |
| dev-agent 端区分"新需求 vs 修复"prompt | Issue body 已经说明「修复需求（第 N 轮）」+ 原 PRD，dev-agent 现有 prompt 可以处理；如果效果差再迭代 |
| 设上限（最多 N 轮 fix） | 不必要，靠人工监控 dashboard |

---

## 4. 验收标准

- [ ] `#修改` 在 REVIEWING/REJECTED → 调 `pm_agent.modify_prd`（不变）
- [ ] `#修改` 在 ACCEPTANCE/DEPLOYED → 调 `request_fix_iteration`，不调 PM Agent
- [ ] `#修改` 在 COMPLETED → 拒绝 + 提示 `#新需求`
- [ ] `request_fix_iteration` 调用：新 issue 标题含「[修复 #N]」，body 含原 PRD + fix_description
- [ ] 第 N 轮的 `iteration` 计数从 `project_dev_logs` 推导，复跑能递增
- [ ] dispatch 失败时给用户友好提示，且 log 记录
- [ ] 单元测试：2 helper + 6 _handle_modify 分流 = 8 个 case 全绿
