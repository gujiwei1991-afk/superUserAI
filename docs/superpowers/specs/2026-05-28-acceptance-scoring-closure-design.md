# 验收 / 评分闭环 — 设计方案

**日期：** 2026-05-28
**作者：** Claude (Opus) + 用户协同 brainstorming
**状态：** 已与用户对齐（单项目仅允许一次评分）

---

## 1. 背景与目标

### 1.1 现状

`feat/production-auto-deploy` 落地后，PR 合并到 main 会自动部署到生产，`project.status` 翻 `DEPLOYED`，企微通知中已经包含「#评分 X Y」的入口提示。但「评分」这条命令链路只完成了一半：

- `_handle_score` 写入 `Project.score / feedback` + 在 `feedbacks` 表插一行 + 翻 `COMPLETED` ✅
- 但状态机里的 `ACCEPTANCE`（待验收）从来没人翻进去 — dashboard 的「待验收」计数永远 0
- session 状态部署后不会主动切到 `SCORING`，导致 `session.active_project_id` 仍指向用户最后一次 `#新需求` 创建的项目，可能完全不是刚部署的项目
- `_handle_score` 只拒绝 DRAFTING / REVIEWING，没有：
  - 分数 1-10 范围校验
  - 已完成状态的重复评分保护
  - STAGED（还没合并）状态的拒绝提示
- 后台没有评分反馈的列表视图，管理员无法快速看历史评分

### 1.2 目标

打通「部署成功 → 用户评分 → 反馈入库」的语义完整闭环，让 `ACCEPTANCE` 状态真正成为流水线中的一环。

### 1.3 核心设计决策（已与用户对齐）

| 决策点 | 选择 | 理由 |
|---|---|---|
| 单项目能否多次评分 | **只能评一次** | 评分覆盖会让数据分析迷惑；用户要补充意见 → 走「反馈回路」task #3 |
| Prod deploy 后翻什么状态 | **直接到 `ACCEPTANCE`** | 跳过 `DEPLOYED` 中间态，让「待验收」语义真正进入流水线 |
| Staging deploy 后翻什么状态 | **保持 `STAGED`，不切 session** | staging 只是中间环境，评分必须在 prod 后做 |
| 评分范围 | **1-10 整数** | 非整数 / 越界给清晰提示 |

---

## 2. 改动一览

### 2.1 状态机变更

| 触发 | 旧状态翻转 | 新状态翻转 |
|---|---|---|
| Staging deploy success | `STAGED` | `STAGED`（不变） |
| Prod deploy success | `DEPLOYED` | `ACCEPTANCE` + 切 creator session 为 `SCORING` + active_project_id |
| `#评分 X Y` 命中 ACCEPTANCE/DEPLOYED | `COMPLETED` | `COMPLETED`（不变） |

### 2.2 `_handle_score` 校验加固

```python
1) score = int(args.get("score", 0))  # 非整数 → 「评分必须是 1-10 之间的整数」
2) 1 ≤ score ≤ 10                      # 越界 → 同上提示
3) comment 非空                         # 不变
4) 拿到 project：
   - COMPLETED → 「该项目已完成评分，不能重复评分」
   - STAGED    → 「PR 还在 staging 环境，等合并到 main 部署上线后再评分」
   - 不在 {DEPLOYED, ACCEPTANCE} → 「当前项目状态为 X，暂时不能评分」
5) 写 score/feedback、Feedback 行、翻 COMPLETED、复位 session
```

### 2.3 `ProductionDeployService` 成功路径

```python
project.status = ProjectStatus.ACCEPTANCE.value
await self._activate_creator_scoring(db, project)
await db.commit()
```

`_activate_creator_scoring`：
- 用 `project.creator_id` 找该用户的 session（with_for_update 加锁，避免并发覆盖）
- 找不到 → 新建一行 `(user_id, state=SCORING, active_project_id=project.id)`
- 找到了 → 翻 state=SCORING、active_project_id=project.id
- 失败仅 log，不抛 — 部署成功路径不能被 session bookkeeping 卡住

### 2.4 后台 `/admin/feedback`

- 路由：`GET /admin/feedback`
- 模板：`templates/feedback.html`
  - 顶部 3 个统计卡片：总评分数 / 平均分 / 低分（≤5）
  - 表格列：时间 / 项目 / 仓库 / 提交人 / 分数 / 反馈
  - 分数按段位染色：≥9 绿 / ≥7 青 / ≥5 黄 / <5 红
- 主导航 `base.html` 增「评分反馈」入口

Feedback 模型增加两条 `relationship("Project", lazy="raise")` / `("User", lazy="raise")`，配合 `selectinload` 一次 fetch。

---

## 3. 故意不做的事

| 项 | 不做的理由 |
|---|---|
| 多次评分覆盖 | 用户拍板：只能评一次 |
| 评分编辑/删除 | YAGNI；如有错评，走管理员手工 DB 干预 |
| 评分时强制要求附图 | 增加摩擦，没有清晰收益 |
| 评分前自动催评（定时任务） | 留到 task #3「反馈回路」一起设计 |

---

## 4. 验收标准

- [ ] Prod deploy 成功后 `project.status == ACCEPTANCE` 且 creator session 切到 SCORING
- [ ] `#评分 0 ok` / `#评分 11 ok` / `#评分 abc ok` 全部被 1-10 提示拒绝
- [ ] `#评分 8`（无 comment）→ 提示要求附反馈
- [ ] STAGED 状态下 `#评分 8 ok` → 提示等合并
- [ ] COMPLETED 状态下 `#评分 8 ok` → 拒绝重复评分
- [ ] ACCEPTANCE / DEPLOYED 状态下 `#评分 8 ok` → 成功记录、翻 COMPLETED
- [ ] `/admin/feedback` 能正确列出所有 Feedback、统计卡片数据准确
- [ ] 单元测试：8 个 score validation case + 重写 1 个 prod-deploy 成功路径 case
