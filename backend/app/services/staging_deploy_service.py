"""Staging auto-deploy service.

Handles SSH-driven docker compose deploys to user's self-managed staging
server, triggered by GitHub PR webhooks.

Spec: docs/superpowers/specs/2026-05-10-staging-auto-deploy-design.md
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.gateway.wechat_client import WeChatClient
    from app.models import DevTask, Project, Repo


logger = logging.getLogger(__name__)


def _parse_ssh_target(
    target: str,
    *,
    default_user: str,
) -> tuple[str, str, int | None]:
    """Parse `[user@]host[:port]` into (user, host, port).

    Raises ValueError on malformed input (empty, non-numeric port, etc.).
    """
    if not target or not target.strip():
        raise ValueError("ssh target is empty")
    target = target.strip()

    if "@" in target:
        user, _, hostport = target.partition("@")
        if not user:
            raise ValueError(f"empty user in ssh target: {target!r}")
    else:
        user = default_user
        hostport = target

    if ":" in hostport:
        host, _, port_str = hostport.partition(":")
        if not host:
            raise ValueError(f"empty host in ssh target: {target!r}")
        try:
            port = int(port_str)
        except ValueError:
            raise ValueError(f"invalid port in ssh target: {target!r}") from None
    else:
        host = hostport
        port = None

    if not host:
        raise ValueError(f"empty host in ssh target: {target!r}")

    return user, host, port


_STAGING_REQUIRED_FIELDS = (
    "staging_url",
    "staging_ssh_target",
    "staging_deploy_path",
    "staging_compose_file",
)


class StagingDeployService:
    """Drives PR-triggered staging deploys via SSH + docker compose.

    On each invocation of `deploy_pr`, validates that the repo has all
    required staging configuration; if so, will SSH to the configured
    target and run `docker compose up -d --build` (full implementation
    in subsequent tasks). Skipped silently when staging config is incomplete.

    Per-repo asyncio.Lock serializes concurrent deploys for the same repo;
    `_pending` coalesces multiple in-flight requests so we deploy the
    latest head_sha rather than every intermediate one.
    """

    def __init__(
        self,
        wechat_client: "WeChatClient",
        ssh_key_path: str,
        ssh_user_default: str = "deploy",
        deploy_timeout_sec: int = 600,
        log_tail_lines: int = 200,
    ) -> None:
        self.wechat_client = wechat_client
        self.ssh_key_path = ssh_key_path
        self.ssh_user_default = ssh_user_default
        self.deploy_timeout_sec = deploy_timeout_sec
        self.log_tail_lines = log_tail_lines
        # per-repo lock 串行
        self._locks: dict[int, asyncio.Lock] = {}
        # per-repo "下一次要部署的 head_sha"，用于合并并发请求
        self._pending: dict[int, tuple[int, str]] = {}  # repo_id -> (pr_number, head_sha)

    def _missing_staging_fields(self, repo: "Repo") -> list[str]:
        return [f for f in _STAGING_REQUIRED_FIELDS if not getattr(repo, f, None)]

    async def deploy_pr(
        self,
        db: "AsyncSession",
        repo: "Repo",
        project: "Project",
        dev_task: "DevTask",
        pr_number: int,
        head_sha: str,
    ) -> None:
        missing = self._missing_staging_fields(repo)
        if missing:
            logger.info(
                "staging deploy skipped repo_id=%s missing=%s",
                repo.id, missing,
            )
            dev_task.staging_deploy_status = "skipped"
            dev_task.staging_deploy_log = (
                f"skipped: missing staging fields: {', '.join(missing)}"
            )
            await db.commit()
            return
        # 后续步骤会在 Task 7+ 实现
        raise NotImplementedError("happy path not implemented yet")
