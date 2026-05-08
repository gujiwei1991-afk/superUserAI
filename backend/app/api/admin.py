from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import (
    ACCESS_TOKEN_COOKIE,
    create_access_token,
    require_admin,
    verify_admin_password,
    verify_token,
)
from app.config import get_settings
from app.database import get_db
from app.gateway.wechat_client import WeChatClient
from app.models import DevTask, Project, ProjectDevLog, Repo, SystemConfig, User, UserRepo
from app.services.config_service import ConfigService
from app.services.github_service import GitHubService
from app.services.project_review import (
    create_issue_for_project,
    notify_creator_approved,
    notify_creator_rejected,
)
from app.services.project_service import ProjectService
from shared.constants import ProjectStatus

BASE_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])
wechat = WeChatClient()

STATUS_LABELS = {
    ProjectStatus.DRAFTING.value: "需求沟通中",
    ProjectStatus.REVIEWING.value: "待审核",
    ProjectStatus.APPROVED.value: "已批准",
    ProjectStatus.DEVELOPING.value: "开发中",
    ProjectStatus.DEPLOYED.value: "已部署",
    ProjectStatus.ACCEPTANCE.value: "待验收",
    ProjectStatus.COMPLETED.value: "已完成",
    ProjectStatus.REJECTED.value: "已驳回",
}

STATUS_BADGE_CLASSES = {
    ProjectStatus.DRAFTING.value: "bg-slate-100 text-slate-700 ring-slate-200",
    ProjectStatus.REVIEWING.value: "bg-amber-100 text-amber-700 ring-amber-200",
    ProjectStatus.APPROVED.value: "bg-blue-100 text-blue-700 ring-blue-200",
    ProjectStatus.DEVELOPING.value: "bg-violet-100 text-violet-700 ring-violet-200",
    ProjectStatus.DEPLOYED.value: "bg-emerald-100 text-emerald-700 ring-emerald-200",
    ProjectStatus.ACCEPTANCE.value: "bg-cyan-100 text-cyan-700 ring-cyan-200",
    ProjectStatus.COMPLETED.value: "bg-emerald-100 text-emerald-700 ring-emerald-200",
    ProjectStatus.REJECTED.value: "bg-rose-100 text-rose-700 ring-rose-200",
}

SOURCE_BADGE_META = {
    "database": {
        "label": "🟢 数据库",
        "class": "bg-emerald-100 text-emerald-700 ring-emerald-200",
    },
    "env": {
        "label": "🟡 环境变量",
        "class": "bg-amber-100 text-amber-700 ring-amber-200",
    },
    "default": {
        "label": "⚪ 默认值",
        "class": "bg-slate-100 text-slate-600 ring-slate-200",
    },
}

DEV_TASK_STATUS_LABELS = {
    "pending": "排队中",
    "in_progress": "开发中",
    "pr_open": "PR 已提交",
    "merged": "已合并",
    "deployed": "已部署",
    "failed": "失败",
}

DEV_TASK_BADGE_CLASSES = {
    "pending": "bg-slate-100 text-slate-700 ring-slate-200",
    "in_progress": "bg-violet-100 text-violet-700 ring-violet-200",
    "pr_open": "bg-blue-100 text-blue-700 ring-blue-200",
    "merged": "bg-emerald-100 text-emerald-700 ring-emerald-200",
    "deployed": "bg-emerald-100 text-emerald-700 ring-emerald-200",
    "failed": "bg-rose-100 text-rose-700 ring-rose-200",
}

DEV_AGENT_WORKSPACE_DIR = "/tmp/superuserai/workspace"

SECRET_SETTING_KEYS = {"llm_api_key", "github_token"}
LLM_PROVIDER_OPTIONS = (
    "openai", "claude", "deepseek", "glm", "moonshot",
    "siliconflow", "qwen", "ollama",
)

SETTINGS_GROUPS = [
    {
        "title": "企业微信配置",
        "subtitle": "配置 vworkApi 所在 Windows 机器的连接信息。",
        "fields": [
            {
                "name": "vwork_api_host",
                "label": "vwork_api_host",
                "description": "vworkApi 所在 Windows 机器的 IP 地址",
                "kind": "input",
                "input_type": "text",
                "placeholder": "192.168.1.10",
            },
            {
                "name": "vwork_api_port",
                "label": "vwork_api_port",
                "description": "vworkApi 端口，默认 8989",
                "kind": "input",
                "input_type": "number",
                "placeholder": "8989",
                "default": "8989",
                "step": "1",
            },
        ],
    },
    {
        "title": "LLM 模型配置",
        "subtitle": "统一管理系统默认的大模型提供商与调用参数。",
        "fields": [
            {
                "name": "llm_provider",
                "label": "llm_provider",
                "description": "LLM 提供商",
                "kind": "select",
                "options": LLM_PROVIDER_OPTIONS,
                "default": "openai",
            },
            {
                "name": "llm_api_key",
                "label": "llm_api_key",
                "description": "API Key",
                "kind": "input",
                "input_type": "password",
                "placeholder": "输入新的 API Key",
            },
            {
                "name": "llm_base_url",
                "label": "llm_base_url",
                "description": "Base URL，可选",
                "kind": "input",
                "input_type": "text",
                "placeholder": "https://api.openai.com/v1",
                "full_width": True,
            },
            {
                "name": "llm_model",
                "label": "llm_model",
                "description": "模型名称",
                "kind": "input",
                "input_type": "text",
                "placeholder": "gpt-4.1",
            },
        ],
    },
    {
        "title": "GitHub 配置",
        "subtitle": "配置系统默认的 GitHub 集成凭据与 Webhook 信息。",
        "fields": [
            {
                "name": "github_token",
                "label": "github_token",
                "description": "系统默认 GitHub Token",
                "kind": "input",
                "input_type": "password",
                "placeholder": "输入新的 GitHub Token",
            },
            {
                "name": "github_webhook_secret",
                "label": "github_webhook_secret",
                "description": "Webhook 签名密钥",
                "kind": "input",
                "input_type": "text",
                "placeholder": "superuserai-webhook-secret",
            },
            {
                "name": "webhook_callback_url",
                "label": "webhook_callback_url",
                "description": "Webhook 回调地址",
                "kind": "input",
                "input_type": "text",
                "placeholder": "https://example.com/api/github/webhook",
                "full_width": True,
                "default": "",
            },
        ],
    },
]

SETTINGS_FIELD_MAP = {
    field["name"]: field
    for group in SETTINGS_GROUPS
    for field in group["fields"]
}


def _render(
    request: Request,
    template_name: str,
    *,
    active_page: str,
    status_code: int = status.HTTP_200_OK,
    context: dict[str, Any] | None = None,
):
    template_context = {
        "request": request,
        "active_page": active_page,
        "status_labels": STATUS_LABELS,
        "status_badge_classes": STATUS_BADGE_CLASSES,
    }
    if context:
        template_context.update(context)

    return templates.TemplateResponse(
        request=request,
        name=template_name,
        context=template_context,
        status_code=status_code,
    )


async def _count_projects(db: AsyncSession, project_status: str | None = None) -> int:
    stmt = select(func.count(Project.id))
    if project_status is not None:
        stmt = stmt.where(Project.status == project_status)
    result = await db.execute(stmt)
    return int(result.scalar_one() or 0)


async def _list_repos(db: AsyncSession) -> list[Repo]:
    stmt = select(Repo).order_by(Repo.created_at.desc(), Repo.id.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _read_form_data(request: Request) -> dict[str, str]:
    body = await request.body()
    parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def _has_config_value(value: Any) -> bool:
    return value is not None and str(value).strip() != ""


def _mask_secret(value: str) -> str:
    return "********" if value.strip() else ""


async def _build_settings_groups(db: AsyncSession) -> list[dict[str, Any]]:
    config_service = ConfigService(db)
    settings = get_settings()
    env_keys = set(settings.model_fields_set)

    stmt = select(SystemConfig.key, SystemConfig.value)
    result = await db.execute(stmt)
    database_values = {key: value for key, value in result.all()}

    rendered_groups: list[dict[str, Any]] = []
    for group in SETTINGS_GROUPS:
        rendered_fields: list[dict[str, Any]] = []
        for field in group["fields"]:
            key = field["name"]
            default_value = field.get("default", "")
            current_value = str(await config_service.get(key, default_value))
            database_value = database_values.get(key)
            env_value = getattr(settings, key, None)

            if _has_config_value(database_value):
                source = "database"
            elif key in env_keys and _has_config_value(env_value):
                source = "env"
            else:
                source = "default"

            rendered_fields.append(
                {
                    **field,
                    "value": "" if key in SECRET_SETTING_KEYS else current_value,
                    "masked_value": (
                        _mask_secret(current_value) if key in SECRET_SETTING_KEYS else ""
                    ),
                    "source": source,
                    "source_label": SOURCE_BADGE_META[source]["label"],
                    "source_class": SOURCE_BADGE_META[source]["class"],
                }
            )

        rendered_groups.append({**group, "fields": rendered_fields})

    return rendered_groups


def _normalize_url(url: str) -> str:
    return url.strip().rstrip("/")


def _format_github_error(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            payload = exc.response.json()
        except ValueError:
            payload = {}
        message = str(payload.get("message") or exc.response.text or "").strip()
        if message:
            return message
    return str(exc).strip() or "GitHub API 调用失败。"


def _webhook_exists(hooks: list[dict[str, Any]], callback_url: str) -> bool:
    normalized_callback_url = _normalize_url(callback_url)
    for hook in hooks:
        config = hook.get("config") or {}
        hook_url = str(config.get("url") or "")
        if _normalize_url(hook_url) == normalized_callback_url and hook.get("active", True):
            return True
    return False


async def _build_webhook_callback_url(request: Request, db: AsyncSession) -> str:
    webhook_url = request.url_for("github_webhook")
    webhook_path = webhook_url.path
    config_service = ConfigService(db)

    explicit_callback_url = _normalize_url(await config_service.get("webhook_callback_url", ""))
    if explicit_callback_url:
        return explicit_callback_url

    configured_base_url = _normalize_url(await config_service.get("public_base_url", ""))
    if configured_base_url:
        return f"{configured_base_url}{webhook_path}"

    return str(webhook_url)


_WEBHOOK_STATUS_CACHE: dict[tuple[int, str], tuple[float, bool]] = {}
_WEBHOOK_STATUS_TTL_SECONDS = 300.0


def _invalidate_webhook_cache(repo_id: int) -> None:
    for key in list(_WEBHOOK_STATUS_CACHE):
        if key[0] == repo_id:
            _WEBHOOK_STATUS_CACHE.pop(key, None)


async def _check_one_webhook(repo: Repo, callback_url: str) -> tuple[int, bool]:
    import time as _time

    cache_key = (repo.id, callback_url)
    cached = _WEBHOOK_STATUS_CACHE.get(cache_key)
    if cached is not None and _time.monotonic() - cached[0] < _WEBHOOK_STATUS_TTL_SECONDS:
        return repo.id, cached[1]

    github = GitHubService.for_repo(repo)
    try:
        hooks = await asyncio.wait_for(
            github.list_webhooks(repo.github_owner, repo.github_repo),
            timeout=3.0,
        )
        result = _webhook_exists(hooks, callback_url)
        _WEBHOOK_STATUS_CACHE[cache_key] = (_time.monotonic(), result)
        return repo.id, result
    except Exception:
        logger.warning(
            "Failed to fetch webhook status for repo %s",
            repo.github_full_name,
            exc_info=False,
        )
        return repo.id, False
    finally:
        await github.close()


async def _get_repo_webhook_statuses(
    repos: list[Repo],
    callback_url: str,
) -> dict[int, bool]:
    if not repos:
        return {}
    results = await asyncio.gather(
        *(_check_one_webhook(repo, callback_url) for repo in repos),
        return_exceptions=False,
    )
    return dict(results)


async def _render_projects_page(
    request: Request,
    *,
    current_admin: dict[str, Any],
    db: AsyncSession,
    error: str | None = None,
    form_data: dict[str, str] | None = None,
    message: str | None = None,
    message_type: str = "success",
    status_code: int = status.HTTP_200_OK,
):
    repo_items = await _list_repos(db)

    req_count_subq = (
        select(Project.repo_id, func.count().label("req_count"))
        .group_by(Project.repo_id)
        .subquery()
    )
    dev_count_subq = (
        select(Project.repo_id, func.count().label("dev_count"))
        .where(
            Project.status.in_(
                [
                    ProjectStatus.DEVELOPING.value,
                    ProjectStatus.DEPLOYED.value,
                    ProjectStatus.ACCEPTANCE.value,
                ]
            )
        )
        .group_by(Project.repo_id)
        .subquery()
    )

    counts: dict[int, dict[str, int]] = {}
    if repo_items:
        repo_ids = [r.id for r in repo_items]
        for repo_id, c in (
            await db.execute(
                select(req_count_subq.c.repo_id, req_count_subq.c.req_count).where(
                    req_count_subq.c.repo_id.in_(repo_ids)
                )
            )
        ).all():
            counts.setdefault(repo_id, {})["requirements"] = int(c or 0)
        for repo_id, c in (
            await db.execute(
                select(dev_count_subq.c.repo_id, dev_count_subq.c.dev_count).where(
                    dev_count_subq.c.repo_id.in_(repo_ids)
                )
            )
        ).all():
            counts.setdefault(repo_id, {})["developing"] = int(c or 0)

    webhook_callback_url = await _build_webhook_callback_url(request, db)
    webhook_statuses = await _get_repo_webhook_statuses(repo_items, webhook_callback_url)

    items = [
        {
            "repo": r,
            "local_path": (r.local_path or None),
            "sandbox_path": _sandbox_workspace_path(r),
            "requirement_count": counts.get(r.id, {}).get("requirements", 0),
            "developing_count": counts.get(r.id, {}).get("developing", 0),
            "webhook_ok": bool(webhook_statuses.get(r.id, False)),
        }
        for r in repo_items
    ]

    return _render(
        request,
        "projects.html",
        active_page="projects",
        status_code=status_code,
        context={
            "current_admin": current_admin,
            "items": items,
            "error": error,
            "form_data": form_data or {},
            "message": message,
            "message_type": message_type,
            "webhook_callback_url": webhook_callback_url,
        },
    )


def _redirect_to_projects(
    request: Request,
    *,
    message: str,
    message_type: str,
) -> RedirectResponse:
    del request
    return RedirectResponse(
        url=f"/admin/projects?message={quote_plus(message)}&message_type={message_type}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


async def _configure_repo_webhook(
    request: Request,
    db: AsyncSession,
    repo: Repo,
) -> dict[str, str]:
    callback_url = await _build_webhook_callback_url(request, db)
    secret = await ConfigService(db).get("github_webhook_secret", "")
    github = GitHubService.for_repo(repo)

    try:
        hooks = await github.list_webhooks(repo.github_owner, repo.github_repo)
        if _webhook_exists(hooks, callback_url):
            _invalidate_webhook_cache(repo.id)
            return {
                "status": "already_exists",
                "callback_url": callback_url,
            }

        await github.create_webhook(
            owner=repo.github_owner,
            repo=repo.github_repo,
            callback_url=callback_url,
            secret=secret,
        )
        _invalidate_webhook_cache(repo.id)
        return {
            "status": "created",
            "callback_url": callback_url,
        }
    finally:
        await github.close()


async def _get_project_or_404(db: AsyncSession, project_id: int) -> Project:
    stmt = (
        select(Project)
        .options(
            selectinload(Project.repo),
            selectinload(Project.creator),
            selectinload(Project.approver),
        )
        .where(Project.id == project_id)
    )
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def _github_issue_url(project: Project) -> str | None:
    if project.repo is None or project.github_issue_number is None:
        return None
    return (
        f"https://github.com/{project.repo.github_owner}/"
        f"{project.repo.github_repo}/issues/{project.github_issue_number}"
    )


def _github_pr_url(project: Project) -> str | None:
    if project.repo is None or project.github_pr_number is None:
        return None
    return (
        f"https://github.com/{project.repo.github_owner}/"
        f"{project.repo.github_repo}/pull/{project.github_pr_number}"
    )


def _sandbox_workspace_path(repo: Repo) -> str:
    return f"{DEV_AGENT_WORKSPACE_DIR}/{repo.github_owner}-{repo.github_repo}"


def _dev_task_pr_url(task: DevTask, repo: Repo | None) -> str | None:
    if repo is None or task.pr_number is None:
        return None
    return f"https://github.com/{repo.github_owner}/{repo.github_repo}/pull/{task.pr_number}"


@router.get("/login", name="admin_login")
async def login_page(request: Request):
    access_token = request.cookies.get(ACCESS_TOKEN_COOKIE)
    payload = verify_token(access_token) if access_token else None
    if payload is not None and payload.get("role") == "admin":
        return RedirectResponse(
            url=request.url_for("admin_dashboard"),
            status_code=status.HTTP_302_FOUND,
        )

    return _render(
        request,
        "login.html",
        active_page="login",
        context={
            "error": None,
            "hide_nav": True,
        },
    )


@router.post("/login", name="admin_login_submit")
async def login_submit(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    form = await _read_form_data(request)
    username = form.get("username", "").strip()
    password = form.get("password", "")

    stmt = select(User).where(
        User.wechat_user_id == username,
        User.role == "admin",
    )
    result = await db.execute(stmt)
    admin_user = result.scalar_one_or_none()

    if admin_user is None or not verify_admin_password(password):
        return _render(
            request,
            "login.html",
            active_page="login",
            status_code=status.HTTP_401_UNAUTHORIZED,
            context={
                "error": "用户名或密码错误。",
                "hide_nav": True,
                "username": username,
            },
        )

    access_token = create_access_token(
        subject=admin_user.wechat_user_id,
        role=admin_user.role,
        extra_claims={
            "user_id": admin_user.id,
            "username": admin_user.wechat_user_id,
        },
    )
    settings = get_settings()

    response = RedirectResponse(
        url=request.url_for("admin_dashboard"),
        status_code=status.HTTP_303_SEE_OTHER,
    )
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=access_token,
        httponly=True,
        max_age=settings.jwt_expire_minutes * 60,
        samesite="lax",
        secure=False,
        path="/admin",
    )
    return response


@router.get("/dashboard", name="admin_dashboard")
async def dashboard(
    request: Request,
    current_admin: dict[str, Any] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    project_count = int(
        (await db.execute(select(func.count(Repo.id)))).scalar_one() or 0
    )

    status_rows = (
        await db.execute(
            select(Project.status, func.count()).group_by(Project.status)
        )
    ).all()
    by_status: dict[str, int] = {s: int(c or 0) for s, c in status_rows}

    drafting = by_status.get(ProjectStatus.DRAFTING.value, 0)
    reviewing = by_status.get(ProjectStatus.REVIEWING.value, 0)
    in_progress = (
        by_status.get(ProjectStatus.APPROVED.value, 0)
        + by_status.get(ProjectStatus.DEVELOPING.value, 0)
    )
    deployed = by_status.get(ProjectStatus.DEPLOYED.value, 0)
    acceptance = by_status.get(ProjectStatus.ACCEPTANCE.value, 0)
    completed = by_status.get(ProjectStatus.COMPLETED.value, 0)
    rejected = by_status.get(ProjectStatus.REJECTED.value, 0)

    stats = {
        "projects_total": project_count,
        "requirements_total": sum(by_status.values()),
        "drafting": drafting,
        "reviewing": reviewing,
        "in_progress": in_progress,
        "deployed_pending_review": deployed + acceptance,
        "completed": completed,
        "rejected": rejected,
    }
    return _render(
        request,
        "dashboard.html",
        active_page="dashboard",
        context={
            "current_admin": current_admin,
            "stats": stats,
        },
    )


@router.get("/reviews", name="admin_reviews")
async def reviews(
    request: Request,
    current_admin: dict[str, Any] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Project)
        .options(selectinload(Project.repo))
        .where(Project.status == ProjectStatus.REVIEWING.value)
        .order_by(Project.created_at.desc(), Project.id.desc())
    )
    result = await db.execute(stmt)
    projects = list(result.scalars().all())
    return _render(
        request,
        "reviews.html",
        active_page="reviews",
        context={
            "current_admin": current_admin,
            "projects": projects,
        },
    )


@router.get("/reviews/{project_id}", name="admin_review_detail")
async def review_detail(
    request: Request,
    project_id: int,
    current_admin: dict[str, Any] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_or_404(db, project_id)
    project_service = ProjectService(db)
    messages = await project_service.get_messages(project_id)
    return _render(
        request,
        "review_detail.html",
        active_page="reviews",
        context={
            "current_admin": current_admin,
            "project": project,
            "messages": messages,
            "error": None,
        },
    )


@router.post("/reviews/{project_id}/approve", name="admin_approve_review")
async def approve_review(
    request: Request,
    project_id: int,
    current_admin: dict[str, Any] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_or_404(db, project_id)
    if project.status != ProjectStatus.REVIEWING.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only reviewing projects can be approved",
        )
    if project.repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repo not found")

    project_service = ProjectService(db)
    try:
        await create_issue_for_project(
            db,
            project=project,
            repo=project.repo,
            approver_id=int(current_admin["user_id"]),
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        project = await _get_project_or_404(db, project_id)
        messages = await project_service.get_messages(project_id)
        error_message = _format_github_error(exc) or "请检查 GitHub 仓库配置和访问令牌。"
        return _render(
            request,
            "review_detail.html",
            active_page="reviews",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            context={
                "current_admin": current_admin,
                "project": project,
                "messages": messages,
                "error": f"批准失败：{error_message}",
            },
        )

    await db.refresh(project)
    await notify_creator_approved(db, wechat, project)
    return RedirectResponse(
        url=request.url_for("admin_requirement_detail", project_id=project_id),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/reviews/{project_id}/reject", name="admin_reject_review")
async def reject_review(
    request: Request,
    project_id: int,
    current_admin: dict[str, Any] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_or_404(db, project_id)
    if project.status != ProjectStatus.REVIEWING.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only reviewing projects can be rejected",
        )

    project.status = ProjectStatus.REJECTED.value
    await db.commit()
    await db.refresh(project)
    await notify_creator_rejected(db, wechat, project, reason="")

    return RedirectResponse(
        url=request.url_for("admin_requirement_detail", project_id=project_id),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/projects", name="admin_projects")
async def projects(
    request: Request,
    current_admin: dict[str, Any] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    repo_items = await _list_repos(db)

    req_count_subq = (
        select(Project.repo_id, func.count().label("req_count"))
        .group_by(Project.repo_id)
        .subquery()
    )
    dev_count_subq = (
        select(Project.repo_id, func.count().label("dev_count"))
        .where(
            Project.status.in_(
                [
                    ProjectStatus.DEVELOPING.value,
                    ProjectStatus.DEPLOYED.value,
                    ProjectStatus.ACCEPTANCE.value,
                ]
            )
        )
        .group_by(Project.repo_id)
        .subquery()
    )

    counts = {}
    if repo_items:
        repo_ids = [r.id for r in repo_items]
        req_rows = (
            await db.execute(
                select(req_count_subq.c.repo_id, req_count_subq.c.req_count).where(
                    req_count_subq.c.repo_id.in_(repo_ids)
                )
            )
        ).all()
        dev_rows = (
            await db.execute(
                select(dev_count_subq.c.repo_id, dev_count_subq.c.dev_count).where(
                    dev_count_subq.c.repo_id.in_(repo_ids)
                )
            )
        ).all()
        for repo_id, c in req_rows:
            counts.setdefault(repo_id, {})["requirements"] = int(c or 0)
        for repo_id, c in dev_rows:
            counts.setdefault(repo_id, {})["developing"] = int(c or 0)

    webhook_callback_url = await _build_webhook_callback_url(request, db)
    webhook_statuses = await _get_repo_webhook_statuses(repo_items, webhook_callback_url)

    items = [
        {
            "repo": r,
            "local_path": (r.local_path or None),
            "sandbox_path": _sandbox_workspace_path(r),
            "requirement_count": counts.get(r.id, {}).get("requirements", 0),
            "developing_count": counts.get(r.id, {}).get("developing", 0),
            "webhook_ok": bool(webhook_statuses.get(r.id, False)),
        }
        for r in repo_items
    ]

    message = request.query_params.get("message", "").strip() or None
    message_type = request.query_params.get("message_type", "success").strip() or "success"

    return _render(
        request,
        "projects.html",
        active_page="projects",
        context={
            "current_admin": current_admin,
            "items": items,
            "form_data": {},
            "error": None,
            "message": message,
            "message_type": message_type,
            "webhook_callback_url": webhook_callback_url,
        },
    )


@router.get("/projects/{repo_id}", name="admin_project_detail")
async def project_detail(
    request: Request,
    repo_id: int,
    current_admin: dict[str, Any] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    repo = await db.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    requirements_stmt = (
        select(Project)
        .options(selectinload(Project.creator))
        .where(Project.repo_id == repo_id)
        .order_by(Project.created_at.desc(), Project.id.desc())
    )
    requirements = list((await db.execute(requirements_stmt)).scalars().all())

    dev_tasks_stmt = (
        select(DevTask)
        .options(selectinload(DevTask.project))
        .where(DevTask.repo_id == repo_id)
        .order_by(DevTask.started_at.desc(), DevTask.id.desc())
    )
    dev_tasks = list((await db.execute(dev_tasks_stmt)).scalars().all())

    dev_task_views = [
        {
            "task": t,
            "pr_url": _dev_task_pr_url(t, repo),
            "project_title": t.project.title if t.project else "—",
        }
        for t in dev_tasks
    ]

    webhook_callback_url = await _build_webhook_callback_url(request, db)
    webhook_status = (await _get_repo_webhook_statuses([repo], webhook_callback_url)).get(repo_id, False)

    message = request.query_params.get("message", "").strip() or None
    message_type = request.query_params.get("message_type", "success").strip() or "success"

    return _render(
        request,
        "project_detail.html",
        active_page="projects",
        context={
            "current_admin": current_admin,
            "repo": repo,
            "local_path": (repo.local_path or None),
            "sandbox_path": _sandbox_workspace_path(repo),
            "requirements": requirements,
            "dev_tasks": dev_task_views,
            "dev_task_status_labels": DEV_TASK_STATUS_LABELS,
            "dev_task_badge_classes": DEV_TASK_BADGE_CLASSES,
            "webhook_status": webhook_status,
            "webhook_callback_url": webhook_callback_url,
            "message": message,
            "message_type": message_type,
        },
    )


@router.get("/requirements", name="admin_requirements")
async def requirements(
    request: Request,
    current_admin: dict[str, Any] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Project)
        .options(
            selectinload(Project.repo),
            selectinload(Project.creator),
            selectinload(Project.approver),
        )
        .order_by(Project.created_at.desc(), Project.id.desc())
        .limit(50)
    )
    result = await db.execute(stmt)
    items = list(result.scalars().all())
    return _render(
        request,
        "requirements.html",
        active_page="requirements",
        context={
            "current_admin": current_admin,
            "projects": items,
        },
    )


@router.get("/requirements/{project_id}", name="admin_requirement_detail")
async def requirement_detail(
    request: Request,
    project_id: int,
    current_admin: dict[str, Any] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    project = await _get_project_or_404(db, project_id)
    message = request.query_params.get("message", "").strip() or None
    message_type = request.query_params.get("message_type", "success").strip() or "success"
    return _render(
        request,
        "requirement_detail.html",
        active_page="requirements",
        context={
            "current_admin": current_admin,
            "project": project,
            "issue_url": _github_issue_url(project),
            "pr_url": _github_pr_url(project),
            "message": message,
            "message_type": message_type,
        },
    )


@router.post("/requirements/{project_id}/retry", name="admin_retry_requirement")
async def retry_requirement(
    project_id: int,
    request: Request,
    current_admin: dict[str, Any] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    del current_admin
    project = await _get_project_or_404(db, project_id)

    if project.github_issue_number is None:
        url = (
            f"/admin/requirements/{project_id}"
            f"?message={quote_plus('该需求还未生成 GitHub Issue，请先在「待审核」里批准。')}"
            "&message_type=error"
        )
        return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)

    if project.status not in {ProjectStatus.REJECTED.value, ProjectStatus.DEVELOPING.value}:
        url = (
            f"/admin/requirements/{project_id}"
            f"?message={quote_plus(f'当前状态为「{STATUS_LABELS.get(project.status, project.status)}」，无需重试。')}"
            "&message_type=warning"
        )
        return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)

    await db.execute(
        sa_delete(ProjectDevLog).where(ProjectDevLog.project_id == project.id)
    )
    project.status = ProjectStatus.APPROVED.value
    project.github_pr_number = None
    await db.commit()

    del request
    url = (
        f"/admin/requirements/{project_id}"
        f"?message={quote_plus('已重新派发给 dev-agent，30 秒内会再次尝试。')}"
        "&message_type=success"
    )
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/api/requirements/{project_id}/logs", name="admin_requirement_logs")
async def admin_requirement_logs(
    project_id: int,
    current_admin: dict[str, Any] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    del current_admin
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    stmt = (
        select(ProjectDevLog)
        .where(ProjectDevLog.project_id == project_id)
        .order_by(ProjectDevLog.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    return {
        "project_id": project_id,
        "status": project.status,
        "logs": [
            {
                "id": row.id,
                "message": row.message,
                "created_at": row.created_at.isoformat(),
            }
            for row in reversed(rows)
        ],
    }


@router.get("/repos", name="admin_repos")
async def repos_redirect(request: Request):
    del request
    return RedirectResponse(url="/admin/projects", status_code=status.HTTP_301_MOVED_PERMANENTLY)


@router.post("/projects", name="admin_create_repo")
async def create_repo(
    request: Request,
    current_admin: dict[str, Any] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    form = await _read_form_data(request)
    form_data = {
        "name": form.get("name", "").strip(),
        "github_owner": form.get("github_owner", "").strip(),
        "github_repo": form.get("github_repo", "").strip(),
        "github_token": form.get("github_token", "").strip(),
        "deploy_server": form.get("deploy_server", "").strip(),
        "deploy_config": form.get("deploy_config", "").strip(),
    }

    if not form_data["name"] or not form_data["github_owner"] or not form_data["github_repo"]:
        form_data["github_token"] = ""
        return await _render_projects_page(
            request,
            current_admin=current_admin,
            db=db,
            status_code=status.HTTP_400_BAD_REQUEST,
            error="仓库别名、GitHub Owner 和 GitHub Repo 为必填项。",
            form_data=form_data,
        )

    stmt = select(Repo).where(func.lower(Repo.name) == form_data["name"].casefold())
    existing = await db.execute(stmt)
    if existing.scalar_one_or_none() is not None:
        form_data["github_token"] = ""
        return await _render_projects_page(
            request,
            current_admin=current_admin,
            db=db,
            status_code=status.HTTP_400_BAD_REQUEST,
            error="仓库别名已存在，请使用其他名称。",
            form_data=form_data,
        )

    deploy_config: dict[str, Any] | None = None
    if form_data["deploy_config"]:
        try:
            parsed_config = json.loads(form_data["deploy_config"])
        except json.JSONDecodeError:
            form_data["github_token"] = ""
            return await _render_projects_page(
                request,
                current_admin=current_admin,
                db=db,
                status_code=status.HTTP_400_BAD_REQUEST,
                error="部署配置必须是合法 JSON。",
                form_data=form_data,
            )
        if not isinstance(parsed_config, dict):
            form_data["github_token"] = ""
            return await _render_projects_page(
                request,
                current_admin=current_admin,
                db=db,
                status_code=status.HTTP_400_BAD_REQUEST,
                error="部署配置必须是 JSON 对象。",
                form_data=form_data,
            )
        deploy_config = parsed_config

    repo = Repo(
        name=form_data["name"],
        github_owner=form_data["github_owner"],
        github_repo=form_data["github_repo"],
        github_token_encrypted=form_data["github_token"],
        deploy_server=form_data["deploy_server"] or None,
        deploy_config=deploy_config,
    )
    db.add(repo)
    await db.flush()
    repo_id = repo.id
    await db.commit()

    saved_repo = await db.get(Repo, repo_id)
    if saved_repo is None:
        return _redirect_to_projects(
            request,
            message="仓库已保存，但无法重新加载以配置 Webhook。",
            message_type="warning",
        )

    try:
        result = await _configure_repo_webhook(request, db, saved_repo)
    except Exception as exc:
        logger.warning(
            "Failed to auto-configure webhook for repo %s",
            saved_repo.github_full_name,
            exc_info=True,
        )
        return _redirect_to_projects(
            request,
            message=f"仓库已保存，但自动配置 Webhook 失败：{_format_github_error(exc)}",
            message_type="warning",
        )

    if result["status"] == "already_exists":
        return _redirect_to_projects(
            request,
            message="仓库已保存，Webhook 已存在。",
            message_type="success",
        )

    return _redirect_to_projects(
        request,
        message="仓库已保存，并已自动配置 Webhook。",
        message_type="success",
    )


@router.post("/projects/{repo_id}/webhook", name="admin_set_repo_webhook")
async def set_repo_webhook(
    request: Request,
    repo_id: int,
    current_admin: dict[str, Any] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    repo = await db.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repo not found")

    try:
        result = await _configure_repo_webhook(request, db, repo)
    except Exception as exc:
        logger.warning(
            "Failed to configure webhook for repo %s by admin %s",
            repo.github_full_name,
            current_admin.get("username") or current_admin.get("sub"),
            exc_info=True,
        )
        return _redirect_to_projects(
            request,
            message=f"Webhook 配置失败：{_format_github_error(exc)}",
            message_type="error",
        )

    if result["status"] == "already_exists":
        return _redirect_to_projects(
            request,
            message="Webhook 已配置，无需重复创建。",
            message_type="success",
        )

    return _redirect_to_projects(
        request,
        message="Webhook 配置成功。",
        message_type="success",
    )


@router.post("/projects/{repo_id}/description", name="admin_update_repo_description")
async def update_repo_description(
    request: Request,
    repo_id: int,
    current_admin: dict[str, Any] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    del current_admin
    repo = await db.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repo not found")
    form = await _read_form_data(request)
    repo.description = form.get("description", "").strip() or None
    repo.local_path = form.get("local_path", "").strip() or None
    await db.commit()
    return RedirectResponse(
        url=f"/admin/projects/{repo_id}?message={quote_plus('项目信息已更新。')}&message_type=success",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/settings", name="admin_settings")
async def settings_page(
    request: Request,
    current_admin: dict[str, Any] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    return _render(
        request,
        "settings.html",
        active_page="settings",
        context={
            "current_admin": current_admin,
            "saved": request.query_params.get("saved") == "1",
            "settings_groups": await _build_settings_groups(db),
        },
    )


@router.post("/settings", name="admin_save_settings")
async def save_settings(
    request: Request,
    current_admin: dict[str, Any] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    form = await _read_form_data(request)
    config_service = ConfigService(db)

    for key, field in SETTINGS_FIELD_MAP.items():
        value = form.get(key, "").strip()
        if not value:
            continue
        await config_service.set(key, value, description=field["description"])

    await db.commit()
    return RedirectResponse(
        url=f"{request.url_for('admin_settings')}?saved=1",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _redirect_to_user_detail(
    user_id: int,
    *,
    message: str | None = None,
    message_type: str = "success",
) -> RedirectResponse:
    url = f"/admin/users/{user_id}"
    if message:
        url = f"{url}?message={quote_plus(message)}&message_type={message_type}"
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/users", name="admin_users")
async def users_page(
    request: Request,
    current_admin: dict[str, Any] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    grant_count_subq = (
        select(UserRepo.user_id, func.count().label("grant_count"))
        .group_by(UserRepo.user_id)
        .subquery()
    )
    stmt = (
        select(User, func.coalesce(grant_count_subq.c.grant_count, 0).label("grant_count"))
        .outerjoin(grant_count_subq, grant_count_subq.c.user_id == User.id)
        .order_by(User.id.asc())
    )
    rows = (await db.execute(stmt)).all()
    users = []
    for u, grant_count in rows:
        users.append({
            "id": u.id,
            "wechat_user_id": u.wechat_user_id,
            "nickname": u.nickname,
            "role": u.role,
            "is_active": u.is_active,
            "created_at": u.created_at,
            "grant_count": int(grant_count or 0),
        })

    return _render(
        request,
        "users.html",
        active_page="users",
        context={
            "current_admin": current_admin,
            "users": users,
            "message": request.query_params.get("message") or None,
            "message_type": request.query_params.get("message_type", "success"),
        },
    )


@router.get("/users/{user_id}", name="admin_user_detail")
async def user_detail_page(
    user_id: int,
    request: Request,
    current_admin: dict[str, Any] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    granted_stmt = (
        select(Repo)
        .join(UserRepo, UserRepo.repo_id == Repo.id)
        .where(UserRepo.user_id == user_id)
        .order_by(Repo.name)
    )
    granted_repos = (await db.execute(granted_stmt)).scalars().all()
    granted_ids = {r.id for r in granted_repos}

    all_repos = (await db.execute(select(Repo).order_by(Repo.name))).scalars().all()
    available_repos = [r for r in all_repos if r.id not in granted_ids]

    return _render(
        request,
        "user_detail.html",
        active_page="users",
        context={
            "current_admin": current_admin,
            "user": user,
            "granted_repos": granted_repos,
            "available_repos": available_repos,
            "message": request.query_params.get("message") or None,
            "message_type": request.query_params.get("message_type", "success"),
        },
    )


@router.post("/users/{user_id}/grants", name="admin_grant_repo")
async def grant_repo(
    user_id: int,
    request: Request,
    current_admin: dict[str, Any] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.role == "admin":
        return _redirect_to_user_detail(
            user_id,
            message="管理员默认拥有所有仓库权限，无需单独授权。",
            message_type="warning",
        )

    form = await _read_form_data(request)
    repo_id_raw = form.get("repo_id", "").strip()
    if not repo_id_raw:
        return _redirect_to_user_detail(
            user_id, message="请选择要授权的仓库。", message_type="error"
        )
    try:
        repo_id = int(repo_id_raw)
    except ValueError:
        return _redirect_to_user_detail(
            user_id, message="无效的仓库 ID。", message_type="error"
        )

    repo = await db.get(Repo, repo_id)
    if repo is None:
        return _redirect_to_user_detail(
            user_id, message="仓库不存在。", message_type="error"
        )

    existing = await db.execute(
        select(UserRepo).where(
            UserRepo.user_id == user_id, UserRepo.repo_id == repo_id
        )
    )
    if existing.scalar_one_or_none() is not None:
        return _redirect_to_user_detail(
            user_id,
            message=f"用户已拥有仓库「{repo.name}」的权限。",
            message_type="warning",
        )

    granter_id_raw = current_admin.get("sub")
    granter_id: int | None
    try:
        granter_id = int(granter_id_raw) if granter_id_raw is not None else None
    except (TypeError, ValueError):
        granter_id = None

    db.add(UserRepo(user_id=user_id, repo_id=repo_id, granted_by=granter_id))
    await db.commit()

    return _redirect_to_user_detail(
        user_id, message=f"已授权用户访问仓库「{repo.name}」。"
    )


@router.post("/users/sync", name="admin_sync_users")
async def sync_users(
    request: Request,
    current_admin: dict[str, Any] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    del request, current_admin
    client = WeChatClient()
    try:
        items = await client.list_internal_friends()
    except Exception as exc:
        logger.exception("Failed to fetch internal friends from vworkApi")
        return RedirectResponse(
            url=f"/admin/users?message={quote_plus(f'同步失败：{exc}')}&message_type=error",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    created = 0
    nickname_updated = 0
    for item in items:
        wechat_id = str(item.get("user_id") or "").strip()
        if not wechat_id:
            continue
        nickname = (str(item.get("nick_name") or "")).strip() or None

        existing = (
            await db.execute(select(User).where(User.wechat_user_id == wechat_id))
        ).scalar_one_or_none()
        if existing is None:
            db.add(User(wechat_user_id=wechat_id, nickname=nickname, role="user"))
            created += 1
        elif nickname and existing.nickname != nickname:
            existing.nickname = nickname
            nickname_updated += 1

    await db.commit()
    msg = (
        f"同步完成：新增 {created} 个用户，更新昵称 {nickname_updated} 个，"
        f"共拉取 {len(items)} 条记录。"
    )
    return RedirectResponse(
        url=f"/admin/users?message={quote_plus(msg)}&message_type=success",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/users/{user_id}/whitelist", name="admin_toggle_whitelist")
async def toggle_whitelist(
    user_id: int,
    request: Request,
    current_admin: dict[str, Any] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    del current_admin
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.role == "admin":
        return _redirect_to_user_detail(
            user_id,
            message="管理员账号默认已在白名单内，无需切换。",
            message_type="warning",
        )

    form = await _read_form_data(request)
    redirect_target = form.get("redirect", "users").strip() or "users"

    user.is_active = not user.is_active
    await db.commit()

    label = "已加入白名单" if user.is_active else "已移出白名单"
    nickname = user.nickname or user.wechat_user_id
    msg = f"{nickname} {label}。"

    if redirect_target == "user_detail":
        return _redirect_to_user_detail(user_id, message=msg)
    return RedirectResponse(
        url=f"/admin/users?message={quote_plus(msg)}&message_type=success",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/users/{user_id}/grants/{repo_id}/revoke", name="admin_revoke_repo")
async def revoke_repo(
    user_id: int,
    repo_id: int,
    request: Request,
    current_admin: dict[str, Any] = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    del request, current_admin

    grant = await db.execute(
        select(UserRepo).where(
            UserRepo.user_id == user_id, UserRepo.repo_id == repo_id
        )
    )
    grant_obj = grant.scalar_one_or_none()
    if grant_obj is None:
        return _redirect_to_user_detail(
            user_id, message="该用户并未拥有此仓库的权限。", message_type="warning"
        )

    repo = await db.get(Repo, repo_id)
    repo_name = repo.name if repo is not None else f"#{repo_id}"

    await db.delete(grant_obj)
    await db.commit()

    return _redirect_to_user_detail(
        user_id, message=f"已撤销对仓库「{repo_name}」的授权。"
    )
