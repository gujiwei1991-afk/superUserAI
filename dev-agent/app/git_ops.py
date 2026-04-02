from __future__ import annotations

import os
import subprocess
from pathlib import Path
from urllib.parse import quote

from app.config import get_settings


class GitOps:
    def __init__(self) -> None:
        settings = get_settings()
        self.github_token = settings.github_token
        self.workspace_dir = Path(settings.workspace_dir).expanduser()
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

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
        self.checkout_main(repo_path)
        return repo_path

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
        self._run_git(["add", "-A"], cwd=repo_dir)

        status = self._run_git(["status", "--short"], cwd=repo_dir)
        if not status.stdout.strip():
            return False

        self._run_git(["commit", "-m", commit_message], cwd=repo_dir)
        self._run_git(["push", "-u", "origin", branch_name], cwd=repo_dir)
        return True

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
