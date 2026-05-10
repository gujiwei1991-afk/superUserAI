"""Staging auto-deploy service.

Handles SSH-driven docker compose deploys to user's self-managed staging
server, triggered by GitHub PR webhooks.

Spec: docs/superpowers/specs/2026-05-10-staging-auto-deploy-design.md
"""
from __future__ import annotations

import asyncio
import logging
import shlex
from datetime import datetime
from typing import TYPE_CHECKING

from shared.constants import ProjectStatus
from app.services.project_review import notify_creator_targeted

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

    On `deploy_pr`, validates that the repo has the required staging fields,
    parses the SSH target, then SSH'es to it and runs the deploy script
    (git fetch + checkout + docker compose up -d --build). Updates the
    dev_task state to deploying → success/failed and notifies the project
    creator on completion. Skipped silently when staging config is incomplete.

    Per-repo asyncio.Lock serializes concurrent deploys for the same repo;
    `_pending` coalesces multiple in-flight requests so we deploy the
    latest head_sha rather than every intermediate one. (Lock + pending
    behavior is fully wired in Task 9; the dicts are pre-allocated here.)
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
        # repo_id -> (pr_number, head_sha, dev_task_id) — store the ID not the ORM
        # instance because the ORM instance may be from a session that closed
        # before our replay runs (each webhook event has its own request session).
        self._pending: dict[int, tuple[int, str, int]] = {}

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
        # skipped 路径不进锁（廉价、立刻返回）
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

        lock = self._locks.setdefault(repo.id, asyncio.Lock())
        if lock.locked():
            # 有部署在跑：把"最新 head_sha"记下来，让当前部署完后接力一次
            self._pending[repo.id] = (pr_number, head_sha, dev_task.id)
            logger.info(
                "staging deploy queued (coalesce) repo_id=%s pr=%s sha=%s",
                repo.id, pr_number, head_sha,
            )
            return

        async with lock:
            await self._deploy_pr_inner(db, repo, project, dev_task, pr_number, head_sha)

            # 部署完看看有没有 pending 的，有就接力一次（用最新的 sha）
            pending = self._pending.pop(repo.id, None)
            if pending is not None:
                p_pr, p_sha, p_dt_id = pending
                logger.info(
                    "staging deploy coalesced replay repo_id=%s pr=%s sha=%s dt_id=%s",
                    repo.id, p_pr, p_sha, p_dt_id,
                )
                # Re-fetch via the LIVE session — the original ORM instance was
                # bound to the now-closed session of the webhook request that
                # got coalesced.
                from app.models import DevTask  # local to avoid circular import
                fresh_dt = await db.get(DevTask, p_dt_id)
                if fresh_dt is None:
                    logger.warning(
                        "staging deploy coalesce: dev_task %s not found, skipping replay",
                        p_dt_id,
                    )
                else:
                    await self._deploy_pr_inner(db, repo, project, fresh_dt, p_pr, p_sha)

    async def _deploy_pr_inner(
        self,
        db: "AsyncSession",
        repo: "Repo",
        project: "Project",
        dev_task: "DevTask",
        pr_number: int,
        head_sha: str,
    ) -> None:
        # 不再有 skipped 检查；调用方已经过滤
        try:
            user, host, port = _parse_ssh_target(
                repo.staging_ssh_target,
                default_user=self.ssh_user_default,
            )
        except ValueError as e:
            logger.warning("staging deploy bad ssh target repo_id=%s: %s", repo.id, e)
            dev_task.staging_deploy_status = "failed"
            dev_task.staging_deploy_log = f"ssh target parse error: {e}"
            await db.commit()
            await self._notify_failure(db, project, dev_task, pr_number)
            return

        # 标记 deploying，同步 commit
        dev_task.staging_deploy_status = "deploying"
        dev_task.staging_deploy_log = None
        await db.commit()

        ssh_args = [
            "ssh",
            "-i", self.ssh_key_path,
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=15",
        ]
        if port is not None:
            ssh_args += ["-p", str(port)]
        ssh_args += [f"{user}@{host}", "bash", "-s"]

        remote_script = (
            "set -euo pipefail\n"
            f"cd {shlex.quote(repo.staging_deploy_path)}\n"
            f"git fetch origin pull/{int(pr_number)}/head:pr-{int(pr_number)}\n"
            f"git checkout -f pr-{int(pr_number)}\n"
            f"git reset --hard {shlex.quote(head_sha)}\n"
            f"docker compose -f {shlex.quote(repo.staging_compose_file)} up -d --build\n"
            f"docker compose -f {shlex.quote(repo.staging_compose_file)} ps\n"
        )

        proc = await asyncio.create_subprocess_exec(
            *ssh_args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        try:
            stdout, _ = await asyncio.wait_for(
                proc.communicate(remote_script.encode()),
                timeout=self.deploy_timeout_sec,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            dev_task.staging_deploy_status = "failed"
            dev_task.staging_deploy_log = f"deploy timeout after {self.deploy_timeout_sec}s"
            await db.commit()
            await self._notify_failure(db, project, dev_task, pr_number)
            return

        log_text = (stdout or b"").decode("utf-8", errors="replace")
        lines = log_text.splitlines()
        if len(lines) > self.log_tail_lines:
            lines = lines[-self.log_tail_lines:]
        dev_task.staging_deploy_log = "\n".join(lines)

        if proc.returncode != 0:
            dev_task.staging_deploy_status = "failed"
            await db.commit()
            await self._notify_failure(db, project, dev_task, pr_number)
            return

        # 成功
        dev_task.staging_deploy_status = "success"
        dev_task.staging_deployed_at = datetime.utcnow()
        project.status = ProjectStatus.STAGED.value
        await db.commit()
        await self._notify_success(db, project, repo, pr_number)

    async def _notify_success(
        self,
        db: "AsyncSession",
        project: "Project",
        repo: "Repo",
        pr_number: int,
    ) -> None:
        body = (
            f"🎉 需求《{project.title}》已部署到测试环境\n\n"
            f"PR #{pr_number}\n"
            f"👉 {repo.staging_url}\n\n"
            "满意请回复  #评分 <1-10> <意见>\n"
            "需要修改请回复  #修改 <说明>"
        )
        try:
            await notify_creator_targeted(db, self.wechat_client, project, body)
        except Exception:
            logger.exception("staging notify success failed project=%s", project.id)

    async def recover_stale_deploys(self, stale_after_sec: int = 900) -> int:
        """Mark any dev_task stuck in 'deploying' for > stale_after_sec as failed.

        Called once on backend startup; returns the number of rows updated.
        """
        from app.database import AsyncSessionLocal
        from sqlalchemy import text

        async with AsyncSessionLocal() as db:
            result = await db.execute(text("""
                UPDATE dev_tasks
                SET staging_deploy_status = 'failed',
                    staging_deploy_log = 'marker: backend restart while deploying'
                WHERE staging_deploy_status = 'deploying'
                  AND staging_deployed_at IS NULL
                  AND started_at < NOW() - make_interval(secs => :stale_after)
                RETURNING id
            """), {"stale_after": stale_after_sec})
            updated = list(result.scalars())
            await db.commit()
            if updated:
                logger.warning(
                    "staging_deploy: recovered %d stale 'deploying' tasks: %s",
                    len(updated), updated,
                )
            return len(updated)

    async def _notify_failure(
        self,
        db: "AsyncSession",
        project: "Project",
        dev_task: "DevTask",
        pr_number: int,
    ) -> None:
        log = (dev_task.staging_deploy_log or "").strip()
        # 取最后 200 字符当摘要
        summary = log[-200:] if log else "(no log)"
        body = (
            f"❌ PR #{pr_number} 部署到测试环境失败\n\n"
            f"错误摘要：\n{summary}\n\n"
            f"详情见管理后台 project_id={project.id}"
        )
        try:
            await notify_creator_targeted(db, self.wechat_client, project, body)
        except Exception:
            logger.exception("staging notify failure failed project=%s", project.id)
