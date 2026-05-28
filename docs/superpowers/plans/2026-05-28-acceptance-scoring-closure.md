# 验收 / 评分闭环 — 实施计划

**对应设计：** `../specs/2026-05-28-acceptance-scoring-closure-design.md`

---

## Task 1 — Prod deploy 成功 → ACCEPTANCE + session SCORING

**文件**：`backend/app/services/production_deploy_service.py`

**改动**
- 成功路径：`project.status = ProjectStatus.ACCEPTANCE.value`（旧值 DEPLOYED）
- 新增 `_activate_creator_scoring(db, project)`：
  - `select(UserSession).where(user_id = project.creator_id).with_for_update()`
  - 找不到 → 新建一行
  - 找到 → 改 state=SCORING + active_project_id=project.id
  - 失败 log + 吞掉

**注意**：故意不引入对 `SessionManager` 的依赖，避免循环 import / 跨层污染；直接 import `app.models.Session` 是最小入侵。

---

## Task 2 — `_handle_score` 状态白名单 + 范围校验

**文件**：`backend/app/services/message_handler.py`

**改动**
- 把 `int(command.args.get("score", 0))` 包 try/except，越界 / 非整数 → "评分必须是 1-10 之间的整数"
- 拿到 project 后按顺序判：
  - `COMPLETED` → 拒绝重复评分
  - `STAGED` → 提示等合并
  - 不在 {DEPLOYED, ACCEPTANCE} → 通用拒绝（带状态标签）
- 其余逻辑不变（写 score/feedback、Feedback 行、翻 COMPLETED、复位 session）

---

## Task 3 — 后台 /admin/feedback 列表页 + 导航

**文件**
- `backend/app/api/admin.py`：新增 `GET /admin/feedback` 路由，selectinload Project + User
- `backend/templates/feedback.html`（新增）：统计卡片 + 主表格
- `backend/templates/base.html`：导航加「评分反馈」入口
- `backend/app/models/feedback.py`：加 `project` / `user` relationship（`lazy="raise"`，必须显式 selectinload，避免意外 lazy load）

---

## Task 4 — 单元测试

**新文件**：`backend/tests/test_score_validation.py`
- 8 个 case：score 0 / 11 / 非整数 / 无 comment / STAGED 拒绝 / COMPLETED 拒绝 / ACCEPTANCE 成功 / DEPLOYED 成功
- mock `_get_active_project_context`、`project_service.add_message/update_status`、`session_manager.update_session_state`

**修改**：`backend/tests/test_production_deploy_service.py`
- 把 `test_deploy_merge_success_flips_to_deployed_and_records_sha` 改名为 `..._flips_to_acceptance_...`，断言 `project.status == "acceptance"`
- `_make_db` 加 `db.execute` 默认 stub（返回 no-session 的 scalar_one_or_none）以兼容新增 session 写入路径

---

## 完成定义

- 18/18 测试全绿（10 prod_deploy + 8 score_validation）
- `py_compile` 通过
- 手动启动 admin 后台看 `/admin/feedback` 渲染正常
- spec / plan 文档落地
