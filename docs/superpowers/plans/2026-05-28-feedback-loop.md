# 反馈回路 — 实施计划

**对应设计：** `../specs/2026-05-28-feedback-loop-design.md`

---

## Task 1 — `request_fix_iteration` helper

**文件**：`backend/app/services/project_review.py`

**改动**
- 加 `select`, `func` 到 imports；加 `ProjectDevLog` 到 models import
- 新增异步函数 `request_fix_iteration(db, *, project, repo, fix_description) -> int`
  - 用 SQL COUNT 数 `project_dev_logs` 中 `message LIKE 'fix iteration #%'` 的行数 → +1 = 当前轮次
  - 构造 issue body：标题 `[SuperUserAI][修复 #N] <project.title>`，body 由「修复需求」+ 原 PRD + meta footer 组成；labels=["superuserai","auto-dev","fix"]
  - 翻 `project.github_issue_number` 到新 issue 号；翻 `project.status = APPROVED`
  - `db.add(ProjectDevLog(..., message=f"fix iteration #{N}: issue #{X} — <desc[:200]>"))`
  - 不调 `db.commit()`，留给 caller

---

## Task 2 — `_handle_modify` 按状态分流

**文件**：`backend/app/services/message_handler.py`

**改动**
- 把原本 `COMPLETED → "不能再修改方案"` 文案改成 `"已经完成，如需新调整请发送 #新需求 重新开始"`
- COMPLETED 校验之后，新增条件：
  ```python
  if project.status in {ACCEPTANCE, DEPLOYED}:
      return await self._dispatch_fix_iteration(project, repo, feedback, wechat_user_id)
  ```
- 新增 `_dispatch_fix_iteration` 方法：
  - try / except 调 `request_fix_iteration`；失败 → `logger.exception` + 返回友好提示
  - 成功 → 在 messages 表落两条（user `#修改 ...` / assistant 「已派 AI 开始修复...」）
  - 返回中文文本含 `issue #{number}`

---

## Task 3 — 单元测试

**新文件**：`backend/tests/test_fix_iteration.py`

8 个 case：
- `request_fix_iteration_creates_issue_and_flips_status`：success path，断言 status→APPROVED、github_issue_number 更新、create_issue 调用一次、dev_log add 一次
- `request_fix_iteration_increments_round_counter`：mock COUNT 返回 2 → 标题含 `[修复 #3]`
- `modify_in_reviewing_calls_pm_agent_not_fix`：mock fix 函数 → 验证被跳过、pm_agent.modify_prd 被调
- `modify_in_acceptance_dispatches_fix_not_pm`：mock request_fix_iteration 返回 999 → reply 含 `issue #999`、pm_agent 不被调
- `modify_in_deployed_dispatches_fix`：同上但状态 DEPLOYED
- `modify_in_completed_rejects`：fix 函数不被调；reply 含 `#新需求`
- `modify_empty_feedback_rejects`：空 feedback 直接拒
- `modify_dispatch_failure_friendly_error`：mock fix 抛 RuntimeError → reply 含「失败」

---

## 完成定义

- 8/8 新测试全绿；既有 26 个测试不回归
- spec + plan 文档落地
- `py_compile` 通过
