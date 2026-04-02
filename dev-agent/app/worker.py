from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.coder import Coder
from app.config import get_settings
from app.git_ops import GitOps

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self) -> None:
        settings = get_settings()
        self.backend_client = httpx.AsyncClient(
            base_url=settings.backend_url.rstrip("/"),
            timeout=30.0,
        )
        github_headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if settings.github_token:
            github_headers["Authorization"] = f"Bearer {settings.github_token}"

        self.github_client = httpx.AsyncClient(
            base_url="https://api.github.com",
            headers=github_headers,
            timeout=30.0,
        )
        self.git_ops = GitOps()
        self.coder = Coder()

    async def poll_tasks(self) -> list[dict[str, Any]]:
        response = await self.backend_client.get("/api/tasks/pending")
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, list) else []

    async def process_task(self, task: dict[str, Any]) -> None:
        project_id = int(task["project_id"])
        github_owner = str(task["github_owner"])
        github_repo = str(task["github_repo"])
        issue_number = int(task["github_issue_number"])
        title = str(task.get("title") or f"Issue #{issue_number}")
        branch_name = f"feat/issue-{issue_number}"

        logger.info(
            "Processing project_id=%s repo=%s/%s issue=%s",
            project_id,
            github_owner,
            github_repo,
            issue_number,
        )

        repo_path = await asyncio.to_thread(self.git_ops.clone_or_pull, github_owner, github_repo)
        try:
            issue = await self._get_issue(github_owner, github_repo, issue_number)
            base_branch = await asyncio.to_thread(self.git_ops.create_branch, repo_path, branch_name)

            develop_result = await self.coder.develop(issue.get("body") or "", str(repo_path))
            if not develop_result.files:
                raise RuntimeError("LLM returned no file changes")

            self.coder.apply_changes(repo_path, develop_result.files)

            commit_message = develop_result.commit_message or f"feat: implement issue #{issue_number}"
            pushed = await asyncio.to_thread(
                self.git_ops.add_commit_push,
                repo_path,
                commit_message,
                branch_name,
            )
            if not pushed:
                raise RuntimeError("Repository has no staged changes after applying generated files")

            pull_request = await self._create_pull_request(
                github_owner=github_owner,
                github_repo=github_repo,
                title=title,
                issue_number=issue_number,
                head_branch=branch_name,
                base_branch=base_branch,
            )
            await self._notify_backend_completed(project_id, int(pull_request["number"]))
        finally:
            try:
                await asyncio.to_thread(self.git_ops.checkout_main, repo_path)
            except Exception:
                logger.exception("Failed to restore default branch for %s", repo_path)

    async def run(self, interval: int = 30) -> None:
        try:
            while True:
                try:
                    tasks = await self.poll_tasks()
                    if tasks:
                        logger.info("Fetched %s pending task(s)", len(tasks))
                    for task in tasks:
                        try:
                            await self.process_task(task)
                        except Exception:
                            logger.exception("Failed to process task: %s", task)
                except Exception:
                    logger.exception("Failed to poll pending tasks")

                await asyncio.sleep(interval)
        finally:
            await self.aclose()

    async def aclose(self) -> None:
        await self.backend_client.aclose()
        await self.github_client.aclose()
        await self.coder.llm_client.aclose()

    async def _get_issue(self, github_owner: str, github_repo: str, issue_number: int) -> dict[str, Any]:
        response = await self.github_client.get(f"/repos/{github_owner}/{github_repo}/issues/{issue_number}")
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}

    async def _create_pull_request(
        self,
        github_owner: str,
        github_repo: str,
        title: str,
        issue_number: int,
        head_branch: str,
        base_branch: str,
    ) -> dict[str, Any]:
        response = await self.github_client.post(
            f"/repos/{github_owner}/{github_repo}/pulls",
            json={
                "title": title,
                "body": f"Closes #{issue_number}",
                "head": head_branch,
                "base": base_branch,
            },
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("GitHub create PR response is not a JSON object")
        return data

    async def _notify_backend_completed(self, project_id: int, pr_number: int) -> None:
        response = await self.backend_client.post(
            f"/api/tasks/{project_id}/completed",
            json={"pr_number": pr_number},
        )
        response.raise_for_status()
