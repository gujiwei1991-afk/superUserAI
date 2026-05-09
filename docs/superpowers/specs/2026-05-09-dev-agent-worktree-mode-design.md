# Dev-Agent Worktree 模式（阶段 1）— 设计方案

**日期：** 2026-05-09
**作者：** Claude (Opus) + 用户协同 brainstorming
**状态：** 待用户最终审阅
**总目标（3 阶段路线图）：**
- **阶段 1（本 spec）**：用 git worktree 替换 sandbox clone，让 dev-agent 在用户本机 `local_path` 旁工作，**仍走 PR 流程**
- 阶段 2：跳过 PR，本地 commit + 状态切 `acceptance`，群里通知"在本机改好了"
- 阶段 3：自动跳起 dev server + URL 通知，用户群里点链接看效果

## 1. 背景与目标

### 1.1 现状

`dev-agent/app/git_ops.py` 的 `clone_or_pull` 把仓库 clone 到 `/private/tmp/superuserai/workspace/<owner>-<repo>`。这是从 0 拉一个独立工作树。代价：
- 每次执行至少一次完整 clone（哪怕本机已有同一仓库）
- 用户**本机仓库**完全不受影响——好处是干净，坏处是用户看不到 dev-agent 在做什么、跑完看效果还得自己单独拉 PR 分支

`repos` 表已经有 **`local_path`** 字段，admin 后台 UI 也允许用户填，但当前 dev-agent **不读它**。

### 1.2 目标

- **`local_path` 配置过的 repo**：dev-agent 在 `<local_path>-superuserai/feat-issue-N` 创建 git worktree，在那里跑 claude → commit → push → 创建 PR
- **未配 `local_path` 的 repo**：保持旧的 sandbox clone 行为不变（向后兼容、可逐仓库切换）
- 用户随时本地 `git worktree list` 能看到 dev-agent 在改的分支
- worktree 在任务完成/失败后**保留**——为阶段 3（跑 dev server）打基础
- **不动 PR 流程**——push + 创建 PR + Actions 部署仍正常
- **不污染用户主工作树**——worktree 是独立目录，跟用户在 `local_path` 主目录的工作互不干扰

### 1.3 核心设计决策（已与用户对齐）

| 决策点 | 选择 |
|---|---|
| worktree 路径模板 | `<local_path>-superuserai/feat-issue-{issue_number}` |
| 未配 `local_path` | fallback 到旧 sandbox clone 模式 |
| worktree 生命周期 | 任务完成/失败后保留，用户手动清理 |
| `local_path` 不存在或不是 git 仓库 | fallback 到 sandbox 模式 + 记 warning |
| 数据模型 | 不加新字段（`repos.local_path` 已存在）|
| GitHub 流程 | 阶段 1 不改，仍 push + 创建 PR |

## 2. 架构改动

```
用户本机:
  /Users/gujiwei/python/oaSys/                ← 你日常开发的主仓库（不动）
  /Users/gujiwei/python/oaSys-superuserai/    ← dev-agent 用的 worktree 父目录（自动创建）
    └── feat-issue-3/                          ← 一个 active dev_task 一个目录
        ├── .git → ../../oaSys/.git/worktrees/feat-issue-3  ← git 内部跳转
        ├── (源代码 - 跟 main 分支同步起来的副本)
        └── (claude 改的文件)

dev-agent worker:
  cd /Users/gujiwei/python/oaSys-superuserai/feat-issue-3
  git checkout -B feat/issue-3 main          ← 用 worktree 提供的内置 add 行为
  claude -p ... --add-dir .                  ← 在这里改文件
  git add -A && git commit && git push -u origin feat/issue-3
  gh pr create
```

git worktree 是 git 原生的多检出机制——多个目录共享同一个 `.git` 元数据，但各自有独立的工作树和 HEAD。完美贴合"我要在 main 之外另起一个分支干活，不影响主目录"。

## 3. 文件改动

### 3.1 backend：`/api/tasks/claim` 响应增加 `local_path`

`backend/app/api/tasks.py` 的 claim endpoint 当前返回：
```python
return {
    "claimed": True,
    "dev_task_id": ...,
    "project_id": ...,
    "github_owner": ...,
    "github_repo": ...,
    "github_issue_number": ...,
    "title": ...,
}
```

新增两个字段：
```python
    "repo_id": ...,
    "local_path": repo.local_path,   # str | None
```

为什么加 `repo_id`：worker 后续可能需要按 repo_id 查询其他属性（虽然阶段 1 不用，留口子）。

### 3.2 dev-agent：`git_ops.py` 新增 `prepare_workspace` 方法

`GitOps.clone_or_pull` 保留不变（兼容性 + fallback 路径）。新增 `prepare_workspace`：

```python
def prepare_workspace(
    self,
    *,
    github_owner: str,
    github_repo: str,
    local_path: str | None,
    branch_name: str,
) -> tuple[Path, str]:
    """Pick worktree mode if local_path is set & valid; else sandbox.
    Returns (working_path, base_branch).
    """
    if local_path:
        local_dir = Path(local_path).expanduser().resolve()
        if local_dir.is_dir() and (local_dir / ".git").exists():
            return self._prepare_worktree(local_dir, branch_name)
        logger.warning(
            "prepare_workspace: local_path=%s is not a git repo, "
            "falling back to sandbox clone for %s/%s",
            local_path, github_owner, github_repo,
        )
    # Fallback: existing sandbox clone path
    repo_path = Path(self.clone_or_pull(github_owner, github_repo))
    base_branch = self.create_branch(repo_path, branch_name)
    return repo_path, base_branch


def _prepare_worktree(
    self,
    local_dir: Path,
    branch_name: str,
) -> tuple[Path, str]:
    parent_name = local_dir.name + "-superuserai"
    worktree_root = local_dir.parent / parent_name
    worktree_root.mkdir(parents=True, exist_ok=True)

    # Sanitize branch name into a directory-friendly form for the worktree path.
    # `feat/issue-3` → `feat-issue-3`
    safe_name = branch_name.replace("/", "-")
    worktree_path = worktree_root / safe_name

    # Determine base branch from main repo (fetch first to refresh)
    self._run_git(["fetch", "origin"], cwd=local_dir)
    base_branch = self._detect_default_branch(local_dir)

    if worktree_path.exists():
        # Reuse: bring the worktree up to date with origin/<base_branch>
        # and force-reset its branch onto base.
        logger.info("worktree exists, resetting: %s", worktree_path)
        self._run_git(["fetch", "origin"], cwd=worktree_path)
        self._run_git(["reset", "--hard", f"origin/{base_branch}"], cwd=worktree_path)
        # Re-create branch in case it diverged from base
        self._run_git(
            ["checkout", "-B", branch_name, f"origin/{base_branch}"],
            cwd=worktree_path,
        )
    else:
        # Fresh: create the worktree on a fresh branch from origin/<base>
        # `git worktree add -B <branch> <path> <base>` creates branch + checkout
        self._run_git(
            ["worktree", "add", "-B", branch_name, str(worktree_path),
             f"origin/{base_branch}"],
            cwd=local_dir,
        )

    return worktree_path, base_branch
```

新增 helper `_detect_default_branch(local_dir)`：用 `git symbolic-ref refs/remotes/origin/HEAD` 拿到 `origin/main` 或 `origin/master`，剥前缀返回。

### 3.3 dev-agent：`worker.py` 用新 API

`worker.py:process_task` 当前：
```python
repo_path = await asyncio.to_thread(self.git_ops.clone_or_pull, github_owner, github_repo)
try:
    issue = await self._get_issue(...)
    base_branch = await asyncio.to_thread(self.git_ops.create_branch, repo_path, branch_name)
    ...
```

改为：
```python
repo_path, base_branch = await asyncio.to_thread(
    self.git_ops.prepare_workspace,
    github_owner=github_owner,
    github_repo=github_repo,
    local_path=task.get("local_path"),
    branch_name=branch_name,
)
try:
    issue = await self._get_issue(...)
    ...
```

`add_commit_push` / `_create_pull_request` / `_notify_backend_completed` 都不变——只是 `repo_path` 现在指向 worktree 目录而不是 sandbox。

### 3.4 dev-agent：`process_task` 末尾不再 `checkout_main`

worktree 模式下 finally 里的 `checkout_main(repo_path)` 会试图把 worktree 切回 main——但 worktree 的 HEAD 应该停在 feat 分支上让用户看，而且 worktree 的 main 分支已经被主仓库占用，强制切会报错。

新逻辑：
```python
finally:
    # In worktree mode the path stays on feat/issue-N (worktree owns its HEAD,
    # the main repo's main branch is unaffected). In sandbox mode we still
    # checkout main so the next task can re-clone over a clean state.
    is_sandbox = "/superuserai/workspace/" in str(repo_path)
    if is_sandbox:
        try:
            await asyncio.to_thread(self.git_ops.checkout_main, repo_path)
        except Exception:
            logger.exception("Failed to restore default branch for %s", repo_path)
```

## 4. 错误处理与边界

| 场景 | 策略 |
|---|---|
| `local_path` 不存在 | warning + fallback sandbox |
| `local_path` 存在但不是 git 仓库（缺 `.git`）| warning + fallback sandbox |
| `local_path` 是 git 仓库但 origin remote 不是 GitHub 上配的同一个 repo | 不检测——用户责任。如果 push 时报错，worker 走失败路径，admin 后台能看到原因 |
| worktree 父目录无法创建（权限问题）| 异常向上抛，process_task 失败处理 |
| 上一个任务的 worktree 还在（同 issue_number 重跑）| 重置：`fetch origin` + `reset --hard origin/<base>` + `checkout -B branch_name`（覆盖之前的改动）|
| 用户在 worktree 主目录里有未提交改动 | `reset --hard` 会清掉——这是**预期的**，因为 worktree 本来就是 dev-agent 专用，用户不该手改它 |
| `local_path` 主目录有未提交改动 | **完全不影响**——worktree 是独立工作树 |
| 主仓库已有同名分支 `feat/issue-3`（用户上次手动建过）| `git worktree add -B` 会强制重置该分支到 base——这是 git 行为，不是 bug。如果用户在那个分支有过自己的 commit，会丢——但合理预期是 dev-agent 拥有 `feat/issue-N` 名字空间 |
| `git worktree add` 报"already exists"（残留 worktree 元数据但目录被人删掉了）| 先 `git worktree prune` 清理，再 add |
| `_detect_default_branch` 失败（仓库是新 init 的）| 默认 `main`，warning |
| 分支名含特殊字符（如 `/`）| `_prepare_worktree` 把 `/` 替换成 `-`，但分支名本身保留原样（git 允许 `feat/issue-3`）|

### 4.1 日志可见性

新增日志点：
```
INFO app.git_ops — prepare_workspace mode=worktree path=/Users/gujiwei/python/oaSys-superuserai/feat-issue-3 base=main
INFO app.git_ops — prepare_workspace mode=sandbox repo=foo/bar
WARNING app.git_ops — local_path=... is not a git repo, falling back to sandbox
INFO app.git_ops — worktree exists, resetting: ...
```

## 5. 测试策略

### 5.1 单元测试（无需真实 git）

`dev-agent/tests/e2e_git_ops_worktree.py` （新）—— stand-alone 风格，可在临时目录里建 git repo 跑：

| 测试 | 覆盖 |
|---|---|
| `test_prepare_workspace_no_local_path_falls_back` | local_path=None → 调 sandbox 路径（mock clone_or_pull 检查它被调用）|
| `test_prepare_workspace_invalid_local_path_falls_back` | local_path 是个普通目录无 `.git` → fallback + warning |
| `test_prepare_workspace_creates_fresh_worktree` | 在临时目录 `git init` + 远端 mock，验证 worktree 在 `<parent>-superuserai/feat-issue-3` 创建成功 |
| `test_prepare_workspace_reuses_existing_worktree` | 第一次 add，第二次再调（同 branch_name）→ 应 reset 而非崩溃 |
| `test_detect_default_branch_main` | `git symbolic-ref` 返回 `refs/remotes/origin/main` → 返回 `main` |

### 5.2 集成测试

`dev-agent/tests/e2e_worker_worktree_smoke.py` （新）：
- 起个临时 fake remote（裸仓库 `git init --bare`）+ 临时 local_path
- mock backend `/api/tasks/claim` 返回带 `local_path` 的 payload
- mock claude（用 `subprocess.PIPE` 直接输出预设 stream-json）
- 验证 worker.process_task 跑完后 `<local_path>-superuserai/feat-issue-X` 存在 + 有 PR push

### 5.3 真机验证（人工）

1. 把 project #10 状态从 `rejected` 改回 `approved`
2. 启动 dev-agent
3. 检查 `/Users/gujiwei/python/oaSys-superuserai/feat-issue-3/` 目录被创建
4. 主目录 `/Users/gujiwei/python/oaSys` 不被动
5. PR 正常 push 到 GitHub

## 6. 范围（YAGNI）

### 6.1 阶段 1 包含

- `/api/tasks/claim` 响应增 `local_path` + `repo_id`
- `git_ops.prepare_workspace` + `_prepare_worktree` + `_detect_default_branch`
- `git_ops.clone_or_pull` 保持原样（fallback 路径）
- `worker.py` 改用 `prepare_workspace` + 在 sandbox 模式才 checkout_main
- 单元 + 集成测试
- 兼容性：未配 `local_path` 的 repo 自动 fallback，**不强制要求所有 repo 都填 local_path**

### 6.2 阶段 1 不做

- worktree 自动清理（留待用户手动 `git worktree remove`）
- 自动 push（默认就 push，跟现有一致）
- 跨 worker 协调（partial unique index 已经保证一个 repo 只有一个 active dev_task，自然就一个 worktree active）
- 与阶段 2 / 阶段 3 相关的 acceptance 状态、dev server、群里 URL 通知等
- worker.py 检查 `local_path` 远端跟 GitHub repo 是否匹配（成本高，留给用户负责）
- admin 后台显示 worktree 路径（可后续加，不挡阶段 1 上线）

## 7. 风险评估

| 风险 | 影响 | 缓解 |
|---|---|---|
| 用户在主仓库 `local_path` 上有同名 `feat/issue-N` 分支正在改 | 中 | `git worktree add -B` 会强制重置该分支——dev-agent 拥有 `feat/issue-N` 命名空间是约定。文档 README 会标注。 |
| 主仓库 git GC / 维护时 worktree 状态被破坏 | 低 | git worktree 设计就是这种共享场景；不在我们控制范围 |
| 用户误删 worktree 目录但留下 `.git/worktrees/` 元数据 | 低 | `_prepare_worktree` 在创建前 `git worktree prune` 兜底（实现里已有处理）|
| local_path 是符号链接 / NFS / 跨盘符 | 低 | git worktree 应该都能处理，但不专门测试。如果用户报问题再修。 |
| 多个 worker 同时在同一 local_path 创建 worktree | 极低 | partial unique index 已经保证 active dev_task 单一；同一 worker 两次 invoke 会 reuse worktree（reset 路径）|
