# Dev-Agent Worktree Mode Implementation Plan (Stage 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make dev-agent work inside a git worktree under the user's `local_path` instead of cloning to `/tmp/superuserai/workspace/`. Repos without a configured `local_path` keep the legacy sandbox behavior — opt-in per repo.

**Architecture:** Backend `/api/tasks/claim` starts returning `repo.local_path`. Dev-agent's `GitOps` gains a `prepare_workspace` dispatcher: if `local_path` is set and points to a valid git repo, create a worktree at `<local_path>-superuserai/feat-issue-N` and check out `feat/issue-N` from `origin/<default>`; otherwise fall back to the existing `clone_or_pull` + `create_branch`. Worker code calls the dispatcher and skips the post-task `checkout_main` in worktree mode (worktree owns its own HEAD). Push + PR creation are unchanged.

**Tech Stack:** SQLAlchemy 2 async (read-only adds), httpx (worker), Python `subprocess` via `GitOps._run_git`, git worktree native commands.

**Spec:** `docs/superpowers/specs/2026-05-09-dev-agent-worktree-mode-design.md`

---

## File Map

**Modify:**
- `backend/app/api/tasks.py` — `/claim` response includes `repo_id` + `local_path`
- `dev-agent/app/git_ops.py` — Add `_detect_default_branch`, `_prepare_worktree`, `prepare_workspace`
- `dev-agent/app/worker.py` — Use `prepare_workspace`; skip `checkout_main` for worktree

**Create:**
- `dev-agent/tests/__init__.py` — Empty package marker
- `dev-agent/tests/e2e_git_ops_worktree.py` — Stand-alone tests using a tmp git repo

---

## Pre-flight

- [ ] **Step 0: Confirm migration head + clean tree**

```bash
cd /Users/gujiwei/python/superUserAI/backend && /Users/gujiwei/python/superUserAI/.venv/bin/alembic current
```
Expected: `i3c4d5e6f7a8 (head)`

```bash
cd /Users/gujiwei/python/superUserAI && git status
```
Expected: `On branch feat/dev-agent-worktree-mode`, working tree clean.

If anything diverges, stop and reconcile.

---

## Task 1: `/api/tasks/claim` response — add `repo_id` + `local_path`

**Files:**
- Modify: `backend/app/api/tasks.py`

- [ ] **Step 1: Update claim handler return**

Edit `backend/app/api/tasks.py`. Find the `claim_task` function. Replace the final `return` block with:

```python
    await db.commit()
    logger.info(
        "claim success project_id=%s dev_task_id=%s worker=%s",
        project.id, new_task.id, payload.worker_id,
    )
    return {
        "claimed": True,
        "dev_task_id": new_task.id,
        "project_id": project.id,
        "repo_id": project.repo_id,
        "github_owner": repo.github_owner,
        "github_repo": repo.github_repo,
        "github_issue_number": project.github_issue_number,
        "title": project.title,
        "local_path": repo.local_path,
    }
```

- [ ] **Step 2: Smoke test endpoint registration + payload shape**

```bash
/Users/gujiwei/python/superUserAI/.venv/bin/python -c "
import inspect
from app.api.tasks import claim_task
src = inspect.getsource(claim_task)
assert 'local_path' in src and 'repo_id' in src
print('claim payload includes local_path + repo_id')
"
```
Expected: `claim payload includes local_path + repo_id`

- [ ] **Step 3: Run existing claim e2e tests still pass**

```bash
/Users/gujiwei/python/superUserAI/.venv/bin/python /Users/gujiwei/python/superUserAI/backend/tests/e2e_task_claim_lock.py 2>&1 | tail -3
```
Expected: `all e2e_task_claim_lock checks passed`

- [ ] **Step 4: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add backend/app/api/tasks.py && git commit -m "feat(api): /tasks/claim response includes repo_id + local_path"
```

---

## Task 2: `GitOps._detect_default_branch` helper

**Files:**
- Modify: `dev-agent/app/git_ops.py`

- [ ] **Step 1: Add the helper**

Edit `dev-agent/app/git_ops.py`. Add this method to `GitOps` (place it near other private helpers, e.g. after `_run_git`):

```python
    def _detect_default_branch(self, repo_dir: Path) -> str:
        """Return the remote's default branch name (origin/HEAD target).

        Falls back to 'main' if the symbolic ref can't be resolved (rare:
        repo never had origin/HEAD set, e.g. fresh init).
        """
        try:
            result = self._run_git(
                ["symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
                cwd=repo_dir,
            )
        except Exception:
            logger.warning(
                "could not detect default branch for %s; defaulting to 'main'",
                repo_dir,
            )
            return "main"
        # Output looks like 'origin/main' — strip the 'origin/' prefix.
        ref = result.stdout.strip()
        if ref.startswith("origin/"):
            return ref[len("origin/"):]
        return ref or "main"
```

This depends on `self._run_git` returning a `subprocess.CompletedProcess`-like object with `.stdout`. Verify the existing `_run_git` signature (in the same file):

```bash
grep -A 10 "def _run_git" /Users/gujiwei/python/superUserAI/dev-agent/app/git_ops.py | head -15
```

If `_run_git` already does `subprocess.run(..., capture_output=True, text=True, check=True)` and returns the result, we're good. If not, this step's code reads slightly different — but assume the standard pattern; we'll fix in step 2 if smoke test fails.

- [ ] **Step 2: Smoke test against a real repo**

```bash
/Users/gujiwei/python/superUserAI/.venv/bin/python -c "
import sys
sys.path.insert(0, '/Users/gujiwei/python/superUserAI/dev-agent')
from pathlib import Path
from app.git_ops import GitOps
g = GitOps()
# Use this repo as a quick check
default = g._detect_default_branch(Path('/Users/gujiwei/python/superUserAI'))
print('default branch:', default)
assert default in ('main', 'master'), default
"
```
Expected: `default branch: main`

If smoke fails because `_run_git` doesn't return a result with `.stdout`, adjust `_detect_default_branch` to call git directly via `subprocess.run` with the same env.

- [ ] **Step 3: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add dev-agent/app/git_ops.py && git commit -m "feat(dev-agent/git_ops): add _detect_default_branch helper"
```

---

## Task 3: `GitOps._prepare_worktree` private method

**Files:**
- Modify: `dev-agent/app/git_ops.py`

- [ ] **Step 1: Add the worktree creator**

In `dev-agent/app/git_ops.py`, add this method to `GitOps` (place it after `_detect_default_branch`):

```python
    def _prepare_worktree(
        self,
        local_dir: Path,
        branch_name: str,
    ) -> tuple[Path, str]:
        """Create or reuse a worktree at <local_dir>-superuserai/<safe-branch>.

        Returns (worktree_path, base_branch).
        """
        parent_name = local_dir.name + "-superuserai"
        worktree_root = local_dir.parent / parent_name
        worktree_root.mkdir(parents=True, exist_ok=True)

        # Sanitize branch name into a directory-friendly form.
        # `feat/issue-3` → `feat-issue-3`
        safe_name = branch_name.replace("/", "-")
        worktree_path = worktree_root / safe_name

        # Refresh remote refs from the main repo first.
        self._run_git(["fetch", "origin"], cwd=local_dir)
        # Prune any stale worktree metadata pointing at deleted directories.
        self._run_git(["worktree", "prune"], cwd=local_dir)

        base_branch = self._detect_default_branch(local_dir)

        if worktree_path.exists():
            logger.info(
                "prepare_workspace: reusing existing worktree at %s "
                "(reset to origin/%s, recreate %s)",
                worktree_path, base_branch, branch_name,
            )
            self._run_git(["fetch", "origin"], cwd=worktree_path)
            # Force the worktree onto a fresh branch from origin/<base>.
            self._run_git(
                ["checkout", "-B", branch_name, f"origin/{base_branch}"],
                cwd=worktree_path,
            )
            # Drop any leftover untracked files / changes.
            self._run_git(["reset", "--hard", f"origin/{base_branch}"], cwd=worktree_path)
            self._run_git(["clean", "-fd"], cwd=worktree_path)
        else:
            logger.info(
                "prepare_workspace: creating worktree at %s (branch=%s base=origin/%s)",
                worktree_path, branch_name, base_branch,
            )
            self._run_git(
                ["worktree", "add", "-B", branch_name, str(worktree_path),
                 f"origin/{base_branch}"],
                cwd=local_dir,
            )

        return worktree_path, base_branch
```

- [ ] **Step 2: Smoke test against a tmp repo**

```bash
/Users/gujiwei/python/superUserAI/.venv/bin/python -c "
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, '/Users/gujiwei/python/superUserAI/dev-agent')
from app.git_ops import GitOps

with tempfile.TemporaryDirectory() as td:
    base = Path(td)
    # Create a bare 'remote' and a working clone with a main branch + commit
    remote = base / 'remote.git'
    subprocess.run(['git', 'init', '--bare', str(remote)], check=True, capture_output=True)
    work = base / 'worktree-smoke'
    subprocess.run(['git', 'clone', str(remote), str(work)], check=True, capture_output=True)
    (work / 'README.md').write_text('hello')
    subprocess.run(['git', 'add', '-A'], cwd=work, check=True, capture_output=True)
    subprocess.run(['git', '-c', 'user.email=t@t', '-c', 'user.name=t',
                    'commit', '-m', 'init'], cwd=work, check=True, capture_output=True)
    subprocess.run(['git', 'push', '-u', 'origin', 'main'], cwd=work, check=True, capture_output=True)
    subprocess.run(['git', 'remote', 'set-head', 'origin', 'main'], cwd=work, check=True, capture_output=True)

    g = GitOps()
    wt_path, base_branch = g._prepare_worktree(work, 'feat/issue-99')
    assert wt_path == work.parent / (work.name + '-superuserai') / 'feat-issue-99'
    assert wt_path.is_dir(), wt_path
    assert (wt_path / 'README.md').read_text() == 'hello'
    assert base_branch == 'main'
    # Verify we can call again — should reuse, not crash
    wt_path2, base2 = g._prepare_worktree(work, 'feat/issue-99')
    assert wt_path2 == wt_path
    print('worktree smoke ok')
"
```
Expected: `worktree smoke ok`

- [ ] **Step 3: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add dev-agent/app/git_ops.py && git commit -m "feat(dev-agent/git_ops): _prepare_worktree creates/reuses git worktree"
```

---

## Task 4: `GitOps.prepare_workspace` dispatcher (worktree vs sandbox)

**Files:**
- Modify: `dev-agent/app/git_ops.py`

- [ ] **Step 1: Add the public dispatcher**

In `dev-agent/app/git_ops.py`, add the `prepare_workspace` method to `GitOps`. Place it near `clone_or_pull` so the two are obvious siblings:

```python
    def prepare_workspace(
        self,
        *,
        github_owner: str,
        github_repo: str,
        local_path: str | None,
        branch_name: str,
    ) -> tuple[Path, str]:
        """Pick worktree mode if local_path is set and valid; else sandbox.

        Returns (working_path, base_branch).
        """
        if local_path:
            local_dir = Path(local_path).expanduser().resolve()
            if local_dir.is_dir() and (local_dir / ".git").exists():
                logger.info(
                    "prepare_workspace mode=worktree local_path=%s repo=%s/%s",
                    local_dir, github_owner, github_repo,
                )
                return self._prepare_worktree(local_dir, branch_name)
            logger.warning(
                "prepare_workspace local_path=%s is not a git repo, "
                "falling back to sandbox clone for %s/%s",
                local_path, github_owner, github_repo,
            )

        logger.info(
            "prepare_workspace mode=sandbox repo=%s/%s",
            github_owner, github_repo,
        )
        repo_path = Path(self.clone_or_pull(github_owner, github_repo))
        base_branch = self.create_branch(repo_path, branch_name)
        return repo_path, base_branch
```

- [ ] **Step 2: Smoke test fallback paths (no real network)**

```bash
/Users/gujiwei/python/superUserAI/.venv/bin/python -c "
import sys
sys.path.insert(0, '/Users/gujiwei/python/superUserAI/dev-agent')
import inspect
from app.git_ops import GitOps
sig = inspect.signature(GitOps.prepare_workspace)
assert {'github_owner','github_repo','local_path','branch_name'} <= set(sig.parameters)
print('prepare_workspace signature ok')
"
```
Expected: `prepare_workspace signature ok`

- [ ] **Step 3: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add dev-agent/app/git_ops.py && git commit -m "feat(dev-agent/git_ops): prepare_workspace dispatcher (worktree vs sandbox)"
```

---

## Task 5: `worker.py` — use `prepare_workspace` and skip `checkout_main` in worktree

**Files:**
- Modify: `dev-agent/app/worker.py`

- [ ] **Step 1: Replace clone_or_pull + create_branch call**

Edit `dev-agent/app/worker.py`. In `process_task`, find the block that does `clone_or_pull` then `create_branch` (around the `repo_path = ... await asyncio.to_thread(self.git_ops.clone_or_pull, ...)` line) and replace **both** that line and the subsequent `base_branch = await asyncio.to_thread(self.git_ops.create_branch, ...)` line with:

```python
        repo_path_obj, base_branch = await asyncio.to_thread(
            self.git_ops.prepare_workspace,
            github_owner=github_owner,
            github_repo=github_repo,
            local_path=task.get("local_path"),
            branch_name=branch_name,
        )
        repo_path = str(repo_path_obj)
```

The variable `repo_path` is already used downstream (for `claude_coder.develop(... repo_path=repo_path)` and `git_ops.add_commit_push`); keeping it as a string preserves all that.

Move this assignment to **before** the `try:` block (it was inside the existing structure where `clone_or_pull` was first; do the same arrangement). Then remove the old `base_branch = await asyncio.to_thread(self.git_ops.create_branch, repo_path, branch_name)` line which is now redundant.

- [ ] **Step 2: Update the `finally` block to skip checkout_main in worktree mode**

Find the `finally:` block at the end of `process_task` that calls `git_ops.checkout_main(repo_path)`. Replace it with:

```python
        finally:
            # In worktree mode the path stays on feat/issue-N (worktree owns its
            # HEAD; the main repo's main branch is unaffected). In sandbox mode
            # we still checkout main so the next task starts from a clean state.
            is_sandbox = "/superuserai/workspace/" in str(repo_path)
            if is_sandbox:
                try:
                    await asyncio.to_thread(self.git_ops.checkout_main, repo_path)
                except Exception:
                    logger.exception("Failed to restore default branch for %s", repo_path)
```

- [ ] **Step 3: Smoke test imports + signature**

```bash
cd /Users/gujiwei/python/superUserAI/dev-agent && /Users/gujiwei/python/superUserAI/.venv/bin/python -c "
import inspect
from app.worker import Worker
src = inspect.getsource(Worker.process_task)
assert 'prepare_workspace' in src, 'process_task should call prepare_workspace'
assert 'is_sandbox' in src, 'process_task finally should branch on is_sandbox'
print('worker process_task uses prepare_workspace + sandbox-aware cleanup')
"
```
Expected: `worker process_task uses prepare_workspace + sandbox-aware cleanup`

- [ ] **Step 4: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add dev-agent/app/worker.py && git commit -m "feat(dev-agent/worker): use prepare_workspace + skip checkout_main in worktree mode"
```

---

## Task 6: dev-agent unit tests for worktree path

**Files:**
- Create: `dev-agent/tests/__init__.py`
- Create: `dev-agent/tests/e2e_git_ops_worktree.py`

- [ ] **Step 1: Empty test package marker**

```bash
mkdir -p /Users/gujiwei/python/superUserAI/dev-agent/tests && touch /Users/gujiwei/python/superUserAI/dev-agent/tests/__init__.py
```

- [ ] **Step 2: Write the test**

Create `/Users/gujiwei/python/superUserAI/dev-agent/tests/e2e_git_ops_worktree.py`:

```python
"""End-to-end smoke for GitOps.prepare_workspace.

Builds a tiny bare-repo + worktree clone in a TemporaryDirectory and exercises
both branches of prepare_workspace: worktree (when local_path is a real git
repo) and sandbox (when local_path is None or invalid).
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.git_ops import GitOps  # noqa: E402


def _bootstrap_repo(base: Path) -> Path:
    """Create a bare 'origin' + a clone with one commit pushed to main."""
    remote = base / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)],
                   check=True, capture_output=True)
    work = base / "main-checkout"
    subprocess.run(["git", "clone", str(remote), str(work)],
                   check=True, capture_output=True)
    (work / "README.md").write_text("hello")
    env_args = ["-c", "user.email=t@t.com", "-c", "user.name=t"]
    subprocess.run(["git", "add", "-A"], cwd=work, check=True, capture_output=True)
    subprocess.run(["git", *env_args, "commit", "-m", "init"],
                   cwd=work, check=True, capture_output=True)
    subprocess.run(["git", "push", "-u", "origin", "main"],
                   cwd=work, check=True, capture_output=True)
    subprocess.run(["git", "remote", "set-head", "origin", "main"],
                   cwd=work, check=True, capture_output=True)
    return work


def test_worktree_creates_under_local_path_dash_superuserai() -> None:
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        work = _bootstrap_repo(base)
        g = GitOps()

        wt_path, base_branch = g.prepare_workspace(
            github_owner="ignored",
            github_repo="ignored",
            local_path=str(work),
            branch_name="feat/issue-99",
        )
        assert base_branch == "main", base_branch
        expected = work.parent / (work.name + "-superuserai") / "feat-issue-99"
        assert wt_path == expected, (wt_path, expected)
        assert (wt_path / "README.md").read_text() == "hello"

        # Idempotent: calling again should reuse and not crash.
        wt_path2, base2 = g.prepare_workspace(
            github_owner="ignored",
            github_repo="ignored",
            local_path=str(work),
            branch_name="feat/issue-99",
        )
        assert wt_path2 == wt_path
        assert base2 == "main"
    print("worktree creation + reuse ok")


def test_none_local_path_falls_back_to_sandbox() -> None:
    g = GitOps()
    fake_calls: list[tuple] = []

    def fake_clone(owner: str, repo: str) -> Path:
        fake_calls.append(("clone", owner, repo))
        # Return a path that won't be touched further in this test
        return Path("/tmp/superuserai/workspace/fake-fake")

    def fake_create_branch(repo_path, branch):
        fake_calls.append(("create_branch", str(repo_path), branch))
        return "main"

    with patch.object(GitOps, "clone_or_pull", fake_clone), \
         patch.object(GitOps, "create_branch", fake_create_branch):
        path, base = g.prepare_workspace(
            github_owner="foo",
            github_repo="bar",
            local_path=None,
            branch_name="feat/issue-1",
        )

    assert base == "main"
    assert fake_calls == [
        ("clone", "foo", "bar"),
        ("create_branch", "/tmp/superuserai/workspace/fake-fake", "feat/issue-1"),
    ], fake_calls
    print("none local_path falls back to sandbox ok")


def test_invalid_local_path_falls_back_to_sandbox() -> None:
    g = GitOps()
    fake_calls: list[tuple] = []

    def fake_clone(owner: str, repo: str) -> Path:
        fake_calls.append(("clone", owner, repo))
        return Path("/tmp/superuserai/workspace/fake-fake")

    def fake_create_branch(repo_path, branch):
        fake_calls.append(("create_branch", str(repo_path), branch))
        return "main"

    with tempfile.TemporaryDirectory() as td:
        with patch.object(GitOps, "clone_or_pull", fake_clone), \
             patch.object(GitOps, "create_branch", fake_create_branch):
            # td is a directory but not a git repo
            path, base = g.prepare_workspace(
                github_owner="foo",
                github_repo="bar",
                local_path=td,
                branch_name="feat/issue-1",
            )

    assert fake_calls and fake_calls[0][0] == "clone"
    print("invalid (non-git) local_path falls back to sandbox ok")


def main() -> None:
    test_worktree_creates_under_local_path_dash_superuserai()
    test_none_local_path_falls_back_to_sandbox()
    test_invalid_local_path_falls_back_to_sandbox()
    print("\nall e2e_git_ops_worktree checks passed")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the test**

```bash
cd /Users/gujiwei/python/superUserAI/dev-agent && /Users/gujiwei/python/superUserAI/.venv/bin/python tests/e2e_git_ops_worktree.py
```
Expected: 3 "ok" lines + `all e2e_git_ops_worktree checks passed`

- [ ] **Step 4: Commit**

```bash
cd /Users/gujiwei/python/superUserAI && git add dev-agent/tests/__init__.py dev-agent/tests/e2e_git_ops_worktree.py && git commit -m "test(dev-agent/git_ops): worktree creation + sandbox fallback paths"
```

---

## Task 7: Full regression + manual restart

- [ ] **Step 1: Backend e2e all pass**

```bash
cd /Users/gujiwei/python/superUserAI/backend && for f in tests/e2e_*.py; do echo "=== $f ==="; /Users/gujiwei/python/superUserAI/.venv/bin/python "$f" 2>&1 | tail -3; done
```
Expected: every script ends with its own "passed" line; no `Traceback`.

- [ ] **Step 2: Bridge tests still pass**

```bash
cd /Users/gujiwei/python/superUserAI/vworkapi-bridge && /Users/gujiwei/python/superUserAI/.venv/bin/python tests/e2e_bridge.py 2>&1 | tail -3
```
Expected: `all e2e_bridge checks passed`

- [ ] **Step 3: New dev-agent e2e passes**

```bash
cd /Users/gujiwei/python/superUserAI/dev-agent && /Users/gujiwei/python/superUserAI/.venv/bin/python tests/e2e_git_ops_worktree.py 2>&1 | tail -3
```
Expected: `all e2e_git_ops_worktree checks passed`

- [ ] **Step 4: Restart backend (TaskStop existing + new uvicorn)**

User-driven: kill the running uvicorn and start a new one so the new `/claim` payload is served.

- [ ] **Step 5: Reset project #10 state for re-test**

```bash
/Users/gujiwei/python/superUserAI/.venv/bin/python -c "
import asyncio
from app.database import AsyncSessionLocal
from sqlalchemy import text
async def go():
    async with AsyncSessionLocal() as db:
        await db.execute(text(\"UPDATE projects SET status='approved', github_pr_number=NULL WHERE id=10\"))
        await db.commit()
        rows = (await db.execute(text(\"SELECT id, status FROM projects WHERE id=10\"))).all()
        print(rows)
asyncio.run(go())
"
```
Expected: `[(10, 'approved')]`

- [ ] **Step 6: Verify `local_path` is set on the repo**

```bash
/Users/gujiwei/python/superUserAI/.venv/bin/python -c "
import asyncio
from app.database import AsyncSessionLocal
from sqlalchemy import text
async def go():
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(text(
            'SELECT r.id, r.name, r.local_path FROM repos r '
            'JOIN projects p ON p.repo_id=r.id WHERE p.id=10'
        ))).all()
        print(rows)
asyncio.run(go())
"
```

If `local_path` is None, you'll need to set it (via the admin UI at `/admin/projects/{repo_id}` or via SQL). Until then dev-agent will fall back to sandbox mode.

- [ ] **Step 7: Probe `/claim` to confirm payload**

```bash
curl -s -X POST http://127.0.0.1:2888/api/tasks/claim \
  -H "Content-Type: application/json" \
  -d '{"worker_id":"manual-verify"}' | head -1
```
Expected: response includes both `repo_id` and `local_path` fields.

If you see `"local_path":"/Users/gujiwei/python/oaSys"`, the upstream wiring is correct. **Release the manual claim** before running real dev-agent:

```bash
/Users/gujiwei/python/superUserAI/.venv/bin/python -c "
import asyncio
from app.database import AsyncSessionLocal
from sqlalchemy import text
async def go():
    async with AsyncSessionLocal() as db:
        await db.execute(text(
            \"DELETE FROM dev_tasks WHERE worker_id='manual-verify' AND status='claimed'\"
        ))
        await db.commit()
asyncio.run(go())
"
```

- [ ] **Step 8: Start dev-agent + watch worktree appear**

In a separate terminal (or via the Bash tool with run_in_background):
```bash
cd /Users/gujiwei/python/superUserAI/dev-agent
/Users/gujiwei/python/superUserAI/.venv/bin/python -m app.main
```

Within ~30 seconds you should see `claim success project_id=10` in the worker log. Then check:
```bash
ls -la /Users/gujiwei/python/oaSys-superuserai/feat-issue-3/ 2>&1 | head -10
```
Expected: directory exists with the repo contents on `feat/issue-3` branch.

```bash
git -C /Users/gujiwei/python/oaSys-superuserai/feat-issue-3 branch --show-current
```
Expected: `feat/issue-3`

```bash
git -C /Users/gujiwei/python/oaSys status --short
```
Expected: empty (your main checkout untouched).

---

## Self-Review Notes

**Spec coverage:**
- §3.1 `/api/tasks/claim` payload + repo_id + local_path → Task 1 ✓
- §3.2 `prepare_workspace` dispatcher → Task 4 ✓
- §3.2 `_prepare_worktree` → Task 3 ✓
- §3.2 `_detect_default_branch` → Task 2 ✓
- §3.3 worker uses `prepare_workspace` → Task 5 ✓
- §3.4 worker skips `checkout_main` in worktree mode → Task 5 ✓
- §4 error handling: invalid local_path fallback (Task 4 + 6), worktree reuse (Task 3 + 6), prune stale metadata (Task 3 step 1) ✓
- §5.1 unit tests → Task 6 ✓

**Placeholder check:** No `TBD` / `implement later` / `similar to Task N`. Each step contains the actual code.

**Type/name consistency:**
- `prepare_workspace(github_owner, github_repo, local_path, branch_name)` — declared in Task 4 step 1, called from Task 5 with the same kwargs.
- `_prepare_worktree(local_dir: Path, branch_name: str) -> tuple[Path, str]` — declared Task 3, called from Task 4. Same return shape `(Path, str)` matches the dispatcher signature.
- `_detect_default_branch(repo_dir: Path) -> str` — declared Task 2, called from Task 3.
- `repo_path` (string) used in `worker.process_task` downstream is preserved (Task 5 step 1 stores `str(repo_path_obj)`).
- `is_sandbox` magic substring `"/superuserai/workspace/"` consistent with `git_ops.clone_or_pull` (which puts repos under `/tmp/superuserai/workspace/...` per the existing implementation).

No drift detected.
