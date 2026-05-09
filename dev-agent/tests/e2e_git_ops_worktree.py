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
        # Resolve both — temp dirs on macOS are sometimes symlinks (/var → /private/var).
        assert wt_path.resolve() == expected.resolve(), (wt_path, expected)
        assert (wt_path / "README.md").read_text() == "hello"

        # Idempotent: calling again should reuse and not crash.
        wt_path2, base2 = g.prepare_workspace(
            github_owner="ignored",
            github_repo="ignored",
            local_path=str(work),
            branch_name="feat/issue-99",
        )
        assert wt_path2.resolve() == wt_path.resolve()
        assert base2 == "main"
    print("worktree creation + reuse ok")


def test_none_local_path_falls_back_to_sandbox() -> None:
    g = GitOps()
    fake_calls: list[tuple] = []

    def fake_clone(self, owner: str, repo: str) -> Path:
        fake_calls.append(("clone", owner, repo))
        return Path("/tmp/superuserai/workspace/fake-fake")

    def fake_create_branch(self, repo_path, branch):
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

    def fake_clone(self, owner: str, repo: str) -> Path:
        fake_calls.append(("clone", owner, repo))
        return Path("/tmp/superuserai/workspace/fake-fake")

    def fake_create_branch(self, repo_path, branch):
        fake_calls.append(("create_branch", str(repo_path), branch))
        return "main"

    with tempfile.TemporaryDirectory() as td:
        with patch.object(GitOps, "clone_or_pull", fake_clone), \
             patch.object(GitOps, "create_branch", fake_create_branch):
            path, base = g.prepare_workspace(
                github_owner="foo",
                github_repo="bar",
                local_path=td,
                branch_name="feat/issue-1",
            )

    assert fake_calls and fake_calls[0][0] == "clone", fake_calls
    print("invalid (non-git) local_path falls back to sandbox ok")


def main() -> None:
    test_worktree_creates_under_local_path_dash_superuserai()
    test_none_local_path_falls_back_to_sandbox()
    test_invalid_local_path_falls_back_to_sandbox()
    print("\nall e2e_git_ops_worktree checks passed")


if __name__ == "__main__":
    main()
