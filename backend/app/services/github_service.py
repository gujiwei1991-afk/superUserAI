from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx

from app.config import get_settings

if TYPE_CHECKING:
    from app.models import Repo


class GitHubService:
    def __init__(self, token: str | None = None) -> None:
        self.token = token if token is not None else get_settings().github_token
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self.base_url = "https://api.github.com"
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=30.0,
        )

    @classmethod
    def for_repo(cls, repo: "Repo") -> "GitHubService":
        token = (
            repo.github_token_encrypted
            if repo.has_custom_github_token
            else get_settings().github_token
        )
        return cls(token=token)

    async def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        response = await self._client.post(
            f"/repos/{owner}/{repo}/issues",
            json={
                "title": title,
                "body": body,
                "labels": labels or [],
            },
        )
        response.raise_for_status()
        return response.json()

    async def get_issue(self, owner: str, repo: str, issue_number: int) -> dict[str, Any]:
        response = await self._client.get(f"/repos/{owner}/{repo}/issues/{issue_number}")
        response.raise_for_status()
        return response.json()

    async def get_repo_tree(self, owner: str, repo: str, branch: str) -> list[dict[str, Any]]:
        response = await self._client.get(f"/repos/{owner}/{repo}/git/trees/{branch}")
        response.raise_for_status()
        data = response.json()
        return list(data.get("tree", []))

    async def get_file_content(self, owner: str, repo: str, path: str, branch: str) -> str:
        import base64

        response = await self._client.get(
            f"/repos/{owner}/{repo}/contents/{path}",
            params={"ref": branch},
        )
        response.raise_for_status()
        data = response.json()
        content = data.get("content", "")
        return base64.b64decode(content).decode("utf-8")

    async def get_readme(self, owner: str, repo: str) -> str:
        import base64

        response = await self._client.get(f"/repos/{owner}/{repo}/readme")
        if response.status_code == 404:
            return ""
        response.raise_for_status()
        data = response.json()
        content = data.get("content", "")
        return base64.b64decode(content).decode("utf-8")

    async def create_webhook(
        self,
        owner: str,
        repo: str,
        callback_url: str,
        secret: str,
        events: list[str] | None = None,
    ) -> dict[str, Any]:
        response = await self._client.post(
            f"/repos/{owner}/{repo}/hooks",
            json={
                "name": "web",
                "active": True,
                "events": events or ["pull_request", "workflow_run"],
                "config": {
                    "url": callback_url,
                    "content_type": "json",
                    "secret": secret,
                    "insecure_ssl": "0",
                },
            },
        )
        response.raise_for_status()
        return response.json()

    async def list_webhooks(self, owner: str, repo: str) -> list[dict[str, Any]]:
        response = await self._client.get(f"/repos/{owner}/{repo}/hooks")
        if response.status_code == 404:
            return []
        response.raise_for_status()
        data = response.json()
        return list(data) if isinstance(data, list) else []

    async def close(self) -> None:
        await self._client.aclose()
