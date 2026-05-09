from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from urllib.parse import quote

from app.config import get_settings

logger = logging.getLogger(__name__)


class GitOps:
    def __init__(self) -> None:
        settings = get_settings()
        self.github_token = settings.github_token
        self.workspace_dir = Path(settings.workspace_dir).expanduser()
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

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
        self._run_git(["worktree", "prune"], cwd=local_dir, check=False)

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
            self._run_git(["clean", "-fd"], cwd=worktree_path, check=False)
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

    def _detect_default_branch(self, repo_dir: Path) -> str:
        """Return the remote's default branch name (origin/HEAD target).

        Falls back to 'main' if the symbolic ref can't be resolved.
        """
        try:
            result = self._run_git(
                ["symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
                cwd=repo_dir,
                check=False,
            )
            if result.returncode != 0:
                logger.warning(
                    "could not detect default branch for %s; defaulting to 'main'",
                    repo_dir,
                )
                return "main"
            ref = result.stdout.strip()
            if ref.startswith("origin/"):
                return ref[len("origin/"):]
            return ref or "main"
        except Exception:
            logger.exception(
                "default branch detection failed for %s; defaulting to 'main'",
                repo_dir,
            )
            return "main"

    def clone_or_pull(self, github_owner: str, github_repo: str) -> Path:
        repo_path = self.workspace_dir / f"{github_owner}-{github_repo}"
        repo_url = self._build_repo_url(github_owner, github_repo)

        if not repo_path.exists():
            self._run_git(["clone", repo_url, str(repo_path)])
            return repo_path

        if not (repo_path / ".git").is_dir():
            raise RuntimeError(f"{repo_path} exists but is not a git repository")

        self._run_git(["remote", "set-url", "origin", repo_url], cwd=repo_path)
        self._run_git(["fetch", "origin"], cwd=repo_path)
        self._reset_dirty_sandbox(repo_path)
        self.checkout_main(repo_path)
        return repo_path

    def _reset_dirty_sandbox(self, repo_dir: Path) -> None:
        status = self._run_git(["status", "--porcelain"], cwd=repo_dir, check=False)
        if not status.stdout.strip():
            return
        # sandbox 目录里的脏改动是上一次失败任务留下来的，没人在乎，强制清掉。
        self._run_git(["reset", "--hard", "HEAD"], cwd=repo_dir, check=False)
        self._run_git(["clean", "-fd"], cwd=repo_dir, check=False)

    def create_branch(self, repo_path: str | Path, branch_name: str) -> str:
        repo_dir = Path(repo_path)
        base_branch = self.checkout_main(repo_dir)
        self._run_git(["checkout", "-B", branch_name, base_branch], cwd=repo_dir)
        return base_branch

    def add_commit_push(
        self,
        repo_path: str | Path,
        commit_message: str,
        branch_name: str,
    ) -> bool:
        repo_dir = Path(repo_path)
        self._run_git(["checkout", branch_name], cwd=repo_dir)
        self._run_git(["config", "user.name", "SuperUserAI Dev Agent"], cwd=repo_dir)
        self._run_git(["config", "user.email", "dev-agent@superuserai.local"], cwd=repo_dir)

        self._ensure_gitignore(repo_dir)
        self._run_git(["add", "-A"], cwd=repo_dir)
        # Drop build artefacts / dependency caches even if Claude already added them.
        self._run_git(
            [
                "rm", "-rf", "--cached", "--ignore-unmatch", "--quiet",
                "node_modules", "dist", "build", ".next", ".vite", "coverage",
                ".cache", ".turbo", ".parcel-cache", "venv", ".venv", "__pycache__",
            ],
            cwd=repo_dir,
            check=False,
        )

        status = self._run_git(["status", "--short"], cwd=repo_dir)
        if not status.stdout.strip():
            return False

        self._run_git(["commit", "-m", commit_message], cwd=repo_dir)
        self._run_git(["push", "-u", "origin", branch_name], cwd=repo_dir)
        return True

    @staticmethod
    def _ensure_gitignore(repo_dir: Path) -> None:
        required_patterns = [
            "node_modules/", "dist/", "build/", ".next/", ".vite/",
            "coverage/", ".cache/", ".turbo/", ".parcel-cache/",
            "venv/", ".venv/", "__pycache__/", "*.pyc",
            ".env", ".env.local", ".DS_Store",
        ]
        gitignore = repo_dir / ".gitignore"
        existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
        existing_lines = {line.strip() for line in existing.splitlines() if line.strip()}
        missing = [p for p in required_patterns if p not in existing_lines]
        if not missing:
            return
        prefix = existing.rstrip() + ("\n\n" if existing.strip() else "")
        body = "# auto-added by SuperUserAI dev-agent\n" + "\n".join(missing) + "\n"
        gitignore.write_text(prefix + body, encoding="utf-8")

    def checkout_main(self, repo_path: str | Path) -> str:
        repo_dir = Path(repo_path)
        default_branch = self._detect_default_branch(repo_dir)
        self._run_git(["checkout", default_branch], cwd=repo_dir)
        self._run_git(["pull", "--ff-only", "origin", default_branch], cwd=repo_dir)
        return default_branch

    def _build_repo_url(self, github_owner: str, github_repo: str) -> str:
        if not self.github_token:
            return f"https://github.com/{github_owner}/{github_repo}.git"

        token = quote(self.github_token, safe="")
        return f"https://x-access-token:{token}@github.com/{github_owner}/{github_repo}.git"

    def _detect_default_branch(self, repo_path: Path) -> str:
        symbolic_ref = self._run_git(
            ["symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
            cwd=repo_path,
            check=False,
        )
        if symbolic_ref.returncode == 0:
            ref = symbolic_ref.stdout.strip()
            if ref.startswith("origin/"):
                return ref.split("/", 1)[1]

        for candidate in ("main", "master"):
            result = self._run_git(
                ["show-ref", "--verify", f"refs/remotes/origin/{candidate}"],
                cwd=repo_path,
                check=False,
            )
            if result.returncode == 0:
                return candidate

        return "main"

    def _run_git(
        self,
        args: list[str],
        cwd: Path | None = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if check and result.returncode != 0:
            command = " ".join(["git", *args])
            raise RuntimeError(
                f"Git command failed: {command}\nstdout: {result.stdout}\nstderr: {result.stderr}"
            )
        return result
