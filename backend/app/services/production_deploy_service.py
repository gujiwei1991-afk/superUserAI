"""Production auto-deploy service.

Handles SSH-driven docker compose deploys to the project's production server,
triggered by GitHub `pull_request closed + merged` webhooks (i.e. PR merged
into main).

Mirror of StagingDeployService with three deliberate differences:
  - We fetch & reset to the merge_commit_sha on main, not the PR head.
  - After `docker compose up -d --build`, we optionally run
    `alembic upgrade head` inside the backend container
    (controlled by `repo.prod_run_migrations`).
  - On success we flip `project.status -> DEPLOYED` and record
    `dev_task.prod_deployed_sha`.
"""
from __future__ import annotations

import asyncio
import logging
import shlex
from datetime import datetime
from typing import TYPE_CHECKING

from shared.constants import ProjectStatus
from app.services.project_review import notify_admins, notify_creator_targeted

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


_PROD_REQUIRED_FIELDS = (
    "prod_url",
    "prod_ssh_target",
    "prod_deploy_path",
    "prod_compose_file",
)


class ProductionDeployService:
    """Drives merge-triggered production deploys via SSH + docker compose."""

    def __init__(
        self,
        wechat_client: "WeChatClient",
        ssh_key_path: str,
        ssh_user_default: str = "deploy",
        deploy_timeout_sec: int = 1200,
        log_tail_lines: int = 200,
    ) -> None:
        self.wechat_client = wechat_client
        self.ssh_key_path = ssh_key_path
        self.ssh_user_default = ssh_user_default
        self.deploy_timeout_sec = deploy_timeout_sec
        self.log_tail_lines = log_tail_lines
        self._locks: dict[int, asyncio.Lock] = {}
        # repo_id -> (merge_sha, dev_task_id) — IDs only, see staging service notes
        self._pending: dict[int, tuple[str, int]] = {}

    def _missing_prod_fields(self, repo: "Repo") -> list[str]:
        return [f for f in _PROD_REQUIRED_FIELDS if not getattr(repo, f, None)]

    async def deploy_merge(
        self,
        db: "AsyncSession",
        repo: "Repo",
        project: "Project",
        dev_task: "DevTask",
        merge_sha: str,
        pr_number: int,
    ) -> None:
        """Entry point: PR merged → deploy main@merge_sha to prod."""
        missing = self._missing_prod_fields(repo)
        if missing:
            logger.info(
                "prod deploy skipped repo_id=%s missing=%s",
                repo.id, missing,
            )
            dev_task.prod_deploy_status = "skipped"
            dev_task.prod_deploy_log = (
                f"skipped: missing prod fields: {', '.join(missing)}"
            )
            await db.commit()
            return

        lock = self._locks.setdefault(repo.id, asyncio.Lock())
        if lock.locked():
            self._pending[repo.id] = (merge_sha, dev_task.id)
            logger.info(
                "prod deploy queued (coalesce) repo_id=%s sha=%s",
                repo.id, merge_sha,
            )
            return

        async with lock:
            await self._deploy_inner(db, repo, project, dev_task, merge_sha, pr_number)

            pending = self._pending.pop(repo.id, None)
            if pending is not None:
                p_sha, p_dt_id = pending
                logger.info(
                    "prod deploy coalesced replay repo_id=%s sha=%s dt_id=%s",
                    repo.id, p_sha, p_dt_id,
                )
                from app.models import DevTask  # local to avoid circular import
                fresh_dt = await db.get(DevTask, p_dt_id)
                if fresh_dt is None:
                    logger.warning(
                        "prod deploy coalesce: dev_task %s not found, skipping replay",
                        p_dt_id,
                    )
                else:
                    # For replayed deploy we don't have a fresh PR number; reuse the
                    # one stored on the dev_task itself.
                    replay_pr = fresh_dt.pr_number or pr_number
                    await self._deploy_inner(db, repo, project, fresh_dt, p_sha, replay_pr)

    async def _deploy_inner(
        self,
        db: "AsyncSession",
        repo: "Repo",
        project: "Project",
        dev_task: "DevTask",
        merge_sha: str,
        pr_number: int,
    ) -> None:
        try:
            user, host, port = _parse_ssh_target(
                repo.prod_ssh_target,
                default_user=self.ssh_user_default,
            )
        except ValueError as e:
            logger.warning("prod deploy bad ssh target repo_id=%s: %s", repo.id, e)
            dev_task.prod_deploy_status = "failed"
            dev_task.prod_deploy_log = f"ssh target parse error: {e}"
            await db.commit()
            await self._notify_failure(db, project, dev_task, pr_number)
            return

        dev_task.prod_deploy_status = "deploying"
        dev_task.prod_deploy_log = None
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

        compose_file = shlex.quote(repo.prod_compose_file)
        # 显式项目名（-p）。线上既有 stack 若用 -p/COMPOSE_PROJECT_NAME 起的，
        # 必须填 prod_compose_project，否则项目名会按工作目录名解析，起出平行容器。
        project_name = (repo.prod_compose_project or "").strip()
        compose = "docker compose"
        if project_name:
            compose += f" -p {shlex.quote(project_name)}"
        compose += f" -f {compose_file}"
        script_lines = [
            "set -euo pipefail",
            f"cd {shlex.quote(repo.prod_deploy_path)}",
            "git fetch origin main",
            "git checkout -f main",
            f"git reset --hard {shlex.quote(merge_sha)}",
            f"{compose} up -d --build",
        ]
        if repo.prod_run_migrations:
            # Migration container: assume `backend` service exists in compose;
            # if not, repo owners can set prod_run_migrations=false.
            script_lines.append(
                f"{compose} run --rm backend alembic upgrade head"
            )
        script_lines.append(f"{compose} ps")
        remote_script = "\n".join(script_lines) + "\n"

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
            dev_task.prod_deploy_status = "failed"
            dev_task.prod_deploy_log = f"deploy timeout after {self.deploy_timeout_sec}s"
            await db.commit()
            await self._notify_failure(db, project, dev_task, pr_number)
            return

        log_text = (stdout or b"").decode("utf-8", errors="replace")
        lines = log_text.splitlines()
        if len(lines) > self.log_tail_lines:
            lines = lines[-self.log_tail_lines:]
        dev_task.prod_deploy_log = "\n".join(lines)

        if proc.returncode != 0:
            dev_task.prod_deploy_status = "failed"
            await db.commit()
            await self._notify_failure(db, project, dev_task, pr_number)
            return

        dev_task.prod_deploy_status = "success"
        dev_task.prod_deployed_at = datetime.utcnow()
        dev_task.prod_deployed_sha = merge_sha
        # 直接进入 ACCEPTANCE（待验收），跳过 DEPLOYED 中间态。
        # 同时把 creator 的 session 切到 SCORING + 激活本项目，
        # 这样用户在企微收到通知后 #评分 命令能正确命中本项目。
        project.status = ProjectStatus.ACCEPTANCE.value
        await self._activate_creator_scoring(db, project)
        await db.commit()
        await self._notify_success(db, project, repo, pr_number)

    async def _activate_creator_scoring(
        self,
        db: "AsyncSession",
        project: "Project",
    ) -> None:
        """Switch the project creator's session into SCORING with this project active.

        Best-effort: if the creator has no session yet, we create one. Failures
        are logged but never raised — deploy success path must not break on
        session bookkeeping.
        """
        try:
            from sqlalchemy import select
            from app.models import Session as UserSession
            from shared.constants import SessionState

            stmt = (
                select(UserSession)
                .where(UserSession.user_id == project.creator_id)
                .with_for_update()
            )
            sess = (await db.execute(stmt)).scalar_one_or_none()
            if sess is None:
                sess = UserSession(
                    user_id=project.creator_id,
                    state=SessionState.SCORING.value,
                    active_project_id=project.id,
                )
                db.add(sess)
                await db.flush()
                return
            sess.state = SessionState.SCORING.value
            sess.active_project_id = project.id
            await db.flush()
        except Exception:
            logger.exception(
                "prod deploy: failed to activate creator scoring for project=%s",
                project.id,
            )

    async def _notify_success(
        self,
        db: "AsyncSession",
        project: "Project",
        repo: "Repo",
        pr_number: int,
    ) -> None:
        body = (
            f"🚀 需求《{project.title}》已部署到生产环境\n\n"
            f"PR #{pr_number} 已合并\n"
            f"👉 {repo.prod_url}\n\n"
            "请验证一下功能：\n"
            "• 验收通过：#评分 <1-10> <意见>\n"
            "• 还有问题：#修改 <说明>"
        )
        try:
            await notify_creator_targeted(db, self.wechat_client, project, body)
        except Exception:
            logger.exception("prod notify success failed project=%s", project.id)

    async def _notify_failure(
        self,
        db: "AsyncSession",
        project: "Project",
        dev_task: "DevTask",
        pr_number: int,
    ) -> None:
        log = (dev_task.prod_deploy_log or "").strip()
        summary = log[-200:] if log else "(no log)"
        body = (
            f"❌ PR #{pr_number} 部署到生产环境失败\n\n"
            f"错误摘要：\n{summary}\n\n"
            f"详情见管理后台 project_id={project.id}"
        )
        try:
            await notify_creator_targeted(db, self.wechat_client, project, body)
        except Exception:
            logger.exception("prod notify failure failed project=%s", project.id)
        # 运维告警：生产部署失败一律私聊管理员，便于及时介入。
        try:
            admin_body = (
                f"🚨 生产部署失败 project_id={project.id}《{project.title}》\n"
                f"PR #{pr_number}\n\n"
                f"错误摘要：\n{summary}"
            )
            await notify_admins(db, self.wechat_client, admin_body)
        except Exception:
            logger.exception("prod notify admins failed project=%s", project.id)

    async def recover_stale_deploys(self, stale_after_sec: int = 1800) -> int:
        """Mark any dev_task stuck in prod 'deploying' for > stale_after_sec as failed."""
        from app.database import AsyncSessionLocal
        from sqlalchemy import text

        async with AsyncSessionLocal() as db:
            result = await db.execute(text("""
                UPDATE dev_tasks
                SET prod_deploy_status = 'failed',
                    prod_deploy_log = 'marker: backend restart while deploying'
                WHERE prod_deploy_status = 'deploying'
                  AND prod_deployed_at IS NULL
                  AND started_at < NOW() - make_interval(secs => :stale_after)
                RETURNING id
            """), {"stale_after": stale_after_sec})
            updated = list(result.scalars())
            await db.commit()
            if updated:
                logger.warning(
                    "prod_deploy: recovered %d stale 'deploying' tasks: %s",
                    len(updated), updated,
                )
            return len(updated)
