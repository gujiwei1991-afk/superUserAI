# Group-Project Binding + Natural Language Requirements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind WeChat groups 1:1 to GitHub repos so any group member can express requirements in plain Chinese; AI guides clarification, summarizes a development plan, and only proceeds to admin review after the user explicitly confirms.

**Architecture:** Add three binding columns to `repos`. Intercept bound-group messages in `wechat_gateway` before `parse_command` and route them to a new `GroupMessageRouter` that uses a `GroupIntentClassifier` (heuristic first, LLM verifier only for confirm-candidate messages). Reuse existing `MessageHandler` logic by extracting `_handle_*_internal` private methods. PMAgent emits an in-band `[READY_TO_CONFIRM]` marker (stripped before send) that triggers a fixed summary-and-confirm prompt.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, asyncpg, Jinja2 templates, existing `BaseLLM` abstraction (Claude/OpenAI/Ollama), pydantic-settings.

**Spec:** `docs/superpowers/specs/2026-05-09-group-project-binding-design.md`

---

## File Map

**Create:**
- `backend/alembic/versions/g1a2b3c4d5e6_add_repo_wechat_group_binding.py` — DB migration
- `backend/app/services/repo_binding_service.py` — bind/unbind business logic + welcome/farewell helpers
- `backend/app/services/group_intent.py` — `Intent` enum + `GroupIntentClassifier`
- `backend/app/services/group_message_router.py` — Compose intent classification + handler dispatch + auto-activation for bound groups
- `backend/app/agents/prompts/intent_prompts.py` — `CONFIRM_VERIFY_PROMPT` + helpers
- `backend/tests/e2e_repo_binding.py` — Bind / unbind / re-bind flows (admin API + service)
- `backend/tests/e2e_group_intent.py` — Heuristic + LLM-stub coverage
- `backend/tests/e2e_group_router.py` — End-to-end natural-language flow in a bound group

**Modify:**
- `backend/app/models/repo.py` — Add `wechat_group_id`, `wechat_group_bound_at`, `wechat_group_bound_by`
- `backend/app/config.py` — Add four settings (`intent_llm_model`, `intent_llm_timeout_seconds`, `group_bound_auto_activate`, `pmagent_ready_hint_after_turns`)
- `backend/app/services/project_service.py` — Add `get_repo_by_wechat_group_id`
- `backend/app/services/session_manager.py` — Row-lock active_project_id writes
- `backend/app/services/message_handler.py` — Extract `_handle_*_internal` methods, strip `[READY_TO_CONFIRM]` marker before send
- `backend/app/agents/pm_agent.py` — Append summary-and-confirm step when output contains `[READY_TO_CONFIRM]`
- `backend/app/agents/prompts/pm_prompts.py` — Teach the LLM to emit `[READY_TO_CONFIRM]` when it has enough info
- `backend/app/api/admin.py` — Add bind / unbind endpoints
- `backend/templates/<repo-management-page>.html` — Bind UI (locate by Task 6)
- `backend/app/gateway/wechat_gateway.py` — Branch to bound-group path
- `backend/tests/e2e_group_chat.py` — Regression check after refactor

---

## Pre-flight

- [ ] **Step 0: Confirm migration head**

```bash
cd backend && alembic current
```
Expected: `f3a8c4b2e019 (head)`

If the head is not `f3a8c4b2e019`, **stop** and reconcile before proceeding — Task 1 builds on top of it.

---

## Task 1: Add `wechat_group_id` binding columns to `repos`

**Files:**
- Create: `backend/alembic/versions/g1a2b3c4d5e6_add_repo_wechat_group_binding.py`
- Modify: `backend/app/models/repo.py:1-32`

- [ ] **Step 1: Write the migration**

Create `backend/alembic/versions/g1a2b3c4d5e6_add_repo_wechat_group_binding.py`:

```python
"""add wechat_group binding to repos

Revision ID: g1a2b3c4d5e6
Revises: f3a8c4b2e019
Create Date: 2026-05-09 10:00:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'g1a2b3c4d5e6'
down_revision: str | Sequence[str] | None = 'f3a8c4b2e019'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'repos',
        sa.Column('wechat_group_id', sa.String(), nullable=True),
    )
    op.add_column(
        'repos',
        sa.Column('wechat_group_bound_at', sa.DateTime(timezone=False), nullable=True),
    )
    op.add_column(
        'repos',
        sa.Column(
            'wechat_group_bound_by',
            sa.Integer(),
            sa.ForeignKey('users.id'),
            nullable=True,
        ),
    )
    op.create_index(
        'ix_repos_wechat_group_id',
        'repos',
        ['wechat_group_id'],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('ix_repos_wechat_group_id', table_name='repos')
    op.drop_column('repos', 'wechat_group_bound_by')
    op.drop_column('repos', 'wechat_group_bound_at')
    op.drop_column('repos', 'wechat_group_id')
```

- [ ] **Step 2: Run migration up + down + up to verify symmetry**

```bash
cd backend && alembic upgrade head && alembic downgrade -1 && alembic upgrade head
```
Expected: three "Running upgrade/downgrade" lines, last line is `g1a2b3c4d5e6 (head)`.

- [ ] **Step 3: Update `Repo` model**

Edit `backend/app/models/repo.py`. After the existing import block, ensure these are present:

```python
from datetime import datetime
from sqlalchemy import ForeignKey, Text, func
```

Inside the `Repo` class, add three new fields immediately after `created_at`:

```python
    wechat_group_id: Mapped[str | None] = mapped_column(unique=True, index=True)
    wechat_group_bound_at: Mapped[datetime | None]
    wechat_group_bound_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
```

- [ ] **Step 4: Sanity check imports**

```bash
cd backend && python -c "from app.models.repo import Repo; print(Repo.__table__.columns.keys())"
```
Expected: list contains `wechat_group_id`, `wechat_group_bound_at`, `wechat_group_bound_by`.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/g1a2b3c4d5e6_*.py backend/app/models/repo.py
git commit -m "feat(db): add wechat_group binding fields to repos"
```

---

## Task 2: Add four settings to `config.py`

**Files:**
- Modify: `backend/app/config.py:7-29`

- [ ] **Step 1: Append four settings**

Edit `backend/app/config.py`. Add these fields **immediately before** `claude_cli_executable`:

```python
    intent_llm_model: str = ""  # empty = use llm_model
    intent_llm_timeout_seconds: float = 5.0
    group_bound_auto_activate: bool = True
    pmagent_ready_hint_after_turns: int = 3
```

- [ ] **Step 2: Verify settings load**

```bash
cd backend && python -c "from app.config import get_settings; s = get_settings(); print(s.intent_llm_model, s.intent_llm_timeout_seconds, s.group_bound_auto_activate, s.pmagent_ready_hint_after_turns)"
```
Expected output: ` 5.0 True 3`

- [ ] **Step 3: Commit**

```bash
git add backend/app/config.py
git commit -m "feat(config): add settings for group-bound natural language flow"
```

---

## Task 3: ProjectService — `get_repo_by_wechat_group_id` lookup

**Files:**
- Modify: `backend/app/services/project_service.py:11-22`
- Test: `backend/tests/e2e_repo_binding.py` (new, partial — full coverage in Task 5)

- [ ] **Step 1: Write the failing assertion**

Create `backend/tests/e2e_repo_binding.py` (new file, will grow in later tasks):

```python
"""End-to-end tests for repo↔WeChat-group binding.

Without args: only verifies pure helpers (no DB).
With BIND_GROUP_TEST_REPO_ID + BIND_GROUP_TEST_GROUP_ID: hits the real DB
to verify the full flow.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "shared"))

from app.database import AsyncSessionLocal  # noqa: E402
from app.services.project_service import ProjectService  # noqa: E402


async def test_get_repo_by_wechat_group_id_returns_none_for_unbound() -> None:
    async with AsyncSessionLocal() as db:
        svc = ProjectService(db)
        result = await svc.get_repo_by_wechat_group_id("R:DOES_NOT_EXIST")
        assert result is None, f"expected None, got {result!r}"
    print("get_repo_by_wechat_group_id none-case ok")


def main() -> None:
    asyncio.run(test_get_repo_by_wechat_group_id_returns_none_for_unbound())
    print("all e2e_repo_binding pre-checks passed")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python tests/e2e_repo_binding.py
```
Expected: `AttributeError: 'ProjectService' object has no attribute 'get_repo_by_wechat_group_id'`

- [ ] **Step 3: Implement the method**

Edit `backend/app/services/project_service.py`. Add this method between `get_repo_by_name_or_id` and `create_project`:

```python
    async def get_repo_by_wechat_group_id(self, wechat_group_id: str) -> Repo | None:
        normalized = wechat_group_id.strip()
        if not normalized:
            return None
        stmt = select(Repo).where(Repo.wechat_group_id == normalized)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
```

- [ ] **Step 4: Re-run test, verify it passes**

```bash
cd backend && python tests/e2e_repo_binding.py
```
Expected: `get_repo_by_wechat_group_id none-case ok` then `all e2e_repo_binding pre-checks passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/project_service.py backend/tests/e2e_repo_binding.py
git commit -m "feat(project_service): lookup repo by wechat_group_id"
```

---

## Task 4: SessionManager — row-lock `active_project_id` writes

**Files:**
- Modify: `backend/app/services/session_manager.py:39-48`

- [ ] **Step 1: Tighten the update path with a row lock**

Edit `update_session_state` in `backend/app/services/session_manager.py` to re-fetch the row `FOR UPDATE` before mutating, so concurrent group messages from the same user don't clobber each other:

```python
    async def update_session_state(
        self,
        session: UserSession,
        state: SessionState,
        project_id: int | None = None,
    ) -> UserSession:
        # Re-fetch with row lock so two concurrent in-flight group messages
        # for the same user can't overwrite each other's active_project_id.
        stmt = (
            select(UserSession)
            .where(UserSession.id == session.id)
            .with_for_update()
        )
        locked = (await self.db.execute(stmt)).scalar_one()
        locked.state = state.value
        locked.active_project_id = project_id
        await self.db.flush()
        return locked
```

- [ ] **Step 2: Smoke test (existing test must still pass)**

```bash
cd backend && python tests/e2e_pm_chat.py
```
Expected: regular flow runs to completion (this test never had concurrency, but should still finish without errors).

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/session_manager.py
git commit -m "fix(session_manager): row-lock active_project_id writes"
```

---

## Task 5: RepoBindingService — bind / unbind / welcome helpers

**Files:**
- Create: `backend/app/services/repo_binding_service.py`
- Modify: `backend/tests/e2e_repo_binding.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/e2e_repo_binding.py` (above `def main()`):

```python
from app.models import Repo, User  # noqa: E402
from app.services.repo_binding_service import (  # noqa: E402
    BindingConflictError,
    RepoBindingService,
)
from sqlalchemy import select  # noqa: E402


async def test_bind_unbind_round_trip() -> None:
    """Bind then unbind a real repo. Skips silently if env not set."""
    repo_id_env = os.environ.get("BIND_GROUP_TEST_REPO_ID")
    group_id_env = os.environ.get("BIND_GROUP_TEST_GROUP_ID")
    if not (repo_id_env and group_id_env):
        print("set BIND_GROUP_TEST_REPO_ID + BIND_GROUP_TEST_GROUP_ID to run db round trip")
        return

    repo_id = int(repo_id_env)
    group_id = group_id_env

    async with AsyncSessionLocal() as db:
        admin = (
            await db.execute(
                select(User).where(User.role == "admin").order_by(User.id).limit(1)
            )
        ).scalar_one_or_none()
        assert admin is not None, "need an admin user in the DB"

        svc = RepoBindingService(db)
        await svc.bind(repo_id=repo_id, wechat_group_id=group_id, bound_by=admin.id)
        await db.commit()

        repo = await db.get(Repo, repo_id)
        assert repo is not None
        assert repo.wechat_group_id == group_id
        assert repo.wechat_group_bound_at is not None
        assert repo.wechat_group_bound_by == admin.id

        # Re-bind to same pair -> idempotent (no error)
        await svc.bind(repo_id=repo_id, wechat_group_id=group_id, bound_by=admin.id)
        await db.commit()

        await svc.unbind(repo_id=repo_id)
        await db.commit()
        repo = await db.get(Repo, repo_id)
        assert repo is not None
        assert repo.wechat_group_id is None
        assert repo.wechat_group_bound_at is None
        assert repo.wechat_group_bound_by is None
    print("bind/unbind round trip ok")


async def test_bind_conflict_raises() -> None:
    """Two repos cannot share a group_id."""
    repo_id_env = os.environ.get("BIND_GROUP_TEST_REPO_ID")
    repo2_id_env = os.environ.get("BIND_GROUP_TEST_REPO2_ID")
    group_id_env = os.environ.get("BIND_GROUP_TEST_GROUP_ID")
    if not (repo_id_env and repo2_id_env and group_id_env):
        print("set BIND_GROUP_TEST_REPO2_ID to run conflict test")
        return

    async with AsyncSessionLocal() as db:
        admin = (
            await db.execute(
                select(User).where(User.role == "admin").order_by(User.id).limit(1)
            )
        ).scalar_one_or_none()
        assert admin is not None
        svc = RepoBindingService(db)
        await svc.bind(
            repo_id=int(repo_id_env), wechat_group_id=group_id_env, bound_by=admin.id
        )
        await db.commit()

        try:
            await svc.bind(
                repo_id=int(repo2_id_env),
                wechat_group_id=group_id_env,
                bound_by=admin.id,
            )
        except BindingConflictError:
            print("bind conflict raises ok")
        else:
            raise AssertionError("expected BindingConflictError")
        finally:
            await db.rollback()
            # cleanup
            svc2 = RepoBindingService(db)
            await svc2.unbind(repo_id=int(repo_id_env))
            await db.commit()
```

Then update `main()`:

```python
def main() -> None:
    asyncio.run(test_get_repo_by_wechat_group_id_returns_none_for_unbound())
    asyncio.run(test_bind_unbind_round_trip())
    asyncio.run(test_bind_conflict_raises())
    print("all e2e_repo_binding checks passed")
```

- [ ] **Step 2: Run test, expect ImportError**

```bash
cd backend && python tests/e2e_repo_binding.py
```
Expected: `ModuleNotFoundError: No module named 'app.services.repo_binding_service'`

- [ ] **Step 3: Implement the service**

Create `backend/app/services/repo_binding_service.py`:

```python
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.gateway.wechat_client import WeChatClient
from app.models import Repo

logger = logging.getLogger(__name__)


class BindingConflictError(Exception):
    """Raised when wechat_group_id is already taken by another repo."""


class RepoNotFoundError(Exception):
    """Raised when the target repo doesn't exist."""


class RepoBindingService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def bind(
        self,
        repo_id: int,
        wechat_group_id: str,
        bound_by: int,
        note: str | None = None,
    ) -> Repo:
        del note  # reserved for future, not stored yet
        normalized = wechat_group_id.strip()
        if not normalized:
            raise ValueError("wechat_group_id must be non-empty")

        repo = await self.db.get(Repo, repo_id)
        if repo is None:
            raise RepoNotFoundError(f"repo {repo_id} not found")

        # Idempotent: re-bind same pair -> no-op
        if repo.wechat_group_id == normalized:
            return repo

        # Conflict: group already bound to another repo
        existing = (
            await self.db.execute(
                select(Repo).where(
                    Repo.wechat_group_id == normalized,
                    Repo.id != repo_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise BindingConflictError(
                f"group {normalized} already bound to repo {existing.id}"
            )

        repo.wechat_group_id = normalized
        repo.wechat_group_bound_at = datetime.utcnow()
        repo.wechat_group_bound_by = bound_by
        await self.db.flush()
        logger.info(
            "repo_binding bind repo=%s group=%s by=%s",
            repo_id, normalized, bound_by,
        )
        return repo

    async def unbind(self, repo_id: int) -> Repo:
        repo = await self.db.get(Repo, repo_id)
        if repo is None:
            raise RepoNotFoundError(f"repo {repo_id} not found")

        if repo.wechat_group_id is None:
            return repo  # idempotent

        old_group = repo.wechat_group_id
        repo.wechat_group_id = None
        repo.wechat_group_bound_at = None
        repo.wechat_group_bound_by = None
        await self.db.flush()
        logger.info("repo_binding unbind repo=%s old_group=%s", repo_id, old_group)
        return repo


async def send_welcome(wechat: WeChatClient, group_id: str, repo_name: str) -> None:
    """Send a welcome message to the bound group. Logs but doesn't raise on failure."""
    try:
        await wechat.send_text(
            group_id,
            (
                f"本群已绑定 [{repo_name}] 仓库。\n"
                "@我并直接说出你的需求即可，例如：'我想加个登录功能'。\n"
                "我会引导你补充细节，最后请你确认开发方案。"
            ),
        )
    except Exception:
        logger.exception("send_welcome failed group=%s repo=%s", group_id, repo_name)


async def send_unbind_notice(wechat: WeChatClient, group_id: str, repo_name: str) -> None:
    try:
        await wechat.send_text(
            group_id,
            f"本群已与 [{repo_name}] 仓库解除绑定，自然语言提需求功能已关闭。",
        )
    except Exception:
        logger.exception(
            "send_unbind_notice failed group=%s repo=%s", group_id, repo_name
        )
```

- [ ] **Step 4: Run pure-helper test**

```bash
cd backend && python tests/e2e_repo_binding.py
```
Expected (without env vars): `get_repo_by_wechat_group_id none-case ok` + `set BIND_GROUP_TEST_REPO_ID + BIND_GROUP_TEST_GROUP_ID...` + `set BIND_GROUP_TEST_REPO2_ID...` + `all e2e_repo_binding checks passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/repo_binding_service.py backend/tests/e2e_repo_binding.py
git commit -m "feat(repo_binding): bind/unbind service + welcome/unbind helpers"
```

---

## Task 6: Admin API — bind / unbind endpoints

**Files:**
- Modify: `backend/app/api/admin.py:43-44, ~end of file`

- [ ] **Step 1: Locate the existing repo management surface**

Run `grep -n "set_repo_webhook\|update_repo_description" backend/app/api/admin.py` — note the line of `update_repo_description` (~1271) and add new endpoints **immediately after** it. Both follow the same `Depends(verify_token)` + `_read_form_data` pattern.

- [ ] **Step 2: Add imports**

In `backend/app/api/admin.py`, add to the import block at the top:

```python
from app.services.repo_binding_service import (
    BindingConflictError,
    RepoBindingService,
    RepoNotFoundError,
    send_unbind_notice,
    send_welcome,
)
```

- [ ] **Step 3: Add bind / unbind endpoints**

Append to `backend/app/api/admin.py` (after `update_repo_description`):

```python
@router.post("/repos/{repo_id}/bind-group")
async def bind_repo_group(
    request: Request,
    repo_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    form = await _read_form_data(request)
    group_id = (form.get("group_id") or "").strip()
    if not group_id:
        raise HTTPException(status_code=400, detail="group_id is required")

    admin = await require_admin(request, db)
    svc = RepoBindingService(db)
    try:
        repo = await svc.bind(repo_id=repo_id, wechat_group_id=group_id, bound_by=admin.id)
    except BindingConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RepoNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    await db.commit()
    # Best-effort welcome (we don't roll back on send failure)
    await send_welcome(wechat, group_id, repo.name)
    return RedirectResponse(
        url=request.headers.get("referer") or "/admin/projects",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/repos/{repo_id}/unbind-group")
async def unbind_repo_group(
    request: Request,
    repo_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    svc = RepoBindingService(db)
    try:
        repo = await svc.unbind(repo_id=repo_id)
    except RepoNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    old_group = None
    if repo.wechat_group_id is not None:
        # Race: another request re-bound after our unbind. Don't notify.
        old_group = None
    else:
        # Capture from request for notification
        form = await _read_form_data(request) if request.method == "POST" else {}
        old_group = (form.get("old_group_id") or "").strip() or None

    await db.commit()
    if old_group:
        await send_unbind_notice(wechat, old_group, repo.name)

    return RedirectResponse(
        url=request.headers.get("referer") or "/admin/projects",
        status_code=status.HTTP_303_SEE_OTHER,
    )
```

- [ ] **Step 4: Smoke test endpoint registration**

```bash
cd backend && python -c "from app.main import app; print([r.path for r in app.routes if 'bind-group' in r.path])"
```
Expected: `['/admin/repos/{repo_id}/bind-group', '/admin/repos/{repo_id}/unbind-group']`

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/admin.py
git commit -m "feat(admin): bind/unbind endpoints for repo↔wechat-group"
```

---

## Task 7: Admin UI — bind button on the projects page

**Files:**
- Modify: `backend/templates/projects.html` (or wherever repo management lives)

- [ ] **Step 1: Locate the repo list block**

```bash
cd backend && grep -ln "github_full_name\|repos" templates/*.html
```
Find the template that already lists repos and existing actions (likely `projects.html`).

- [ ] **Step 2: Pass binding context to template**

In `backend/app/api/admin.py`, find the function that renders the repo list (e.g. `_render_projects_page` ~404 or `projects` ~833). Ensure the context dict includes the repos with `wechat_group_id` accessible. Since `Repo` model exposes those fields directly, no change needed — just verify the template iterates over repo objects with full attribute access.

- [ ] **Step 3: Add binding row in the template**

In the repo loop of `backend/templates/projects.html`, append a "群绑定" cell:

```html
{% if repo.wechat_group_id %}
  <span class="text-xs text-slate-500">群: <code>{{ repo.wechat_group_id }}</code></span>
  <form method="post" action="/admin/repos/{{ repo.id }}/unbind-group" class="inline">
    <input type="hidden" name="old_group_id" value="{{ repo.wechat_group_id }}">
    <button type="submit" class="ml-2 text-xs text-rose-600 hover:underline"
            onclick="return confirm('确定解除「{{ repo.name }}」与该群的绑定吗？')">
      解绑
    </button>
  </form>
{% else %}
  <form method="post" action="/admin/repos/{{ repo.id }}/bind-group" class="inline-flex items-center gap-1">
    <input type="text" name="group_id" placeholder="企业微信群 ID"
           class="rounded border border-slate-300 px-2 py-0.5 text-xs"
           required>
    <button type="submit" class="text-xs text-blue-600 hover:underline">绑定</button>
  </form>
{% endif %}
```

- [ ] **Step 4: Visually verify**

Start the backend (`cd backend && uvicorn app.main:app --reload`), log in to `/admin`, navigate to the projects/repos page, see the new column rendering correctly for both bound and unbound rows.

- [ ] **Step 5: Commit**

```bash
git add backend/templates/projects.html
git commit -m "feat(admin/ui): bind/unbind button for repo↔wechat-group"
```

---

## Task 8: PMAgent — `[READY_TO_CONFIRM]` marker mechanism

**Files:**
- Modify: `backend/app/agents/prompts/pm_prompts.py`
- Modify: `backend/app/agents/pm_agent.py`

- [ ] **Step 1: Update SYSTEM_PROMPT**

In `backend/app/agents/prompts/pm_prompts.py`, replace the existing `SYSTEM_PROMPT` with this version (adds rule 7 about `[READY_TO_CONFIRM]`):

```python
SYSTEM_PROMPT = """你是 SuperUserAI 的产品助手，负责跟提需求的同事聊清楚他想要什么。

提需求的人**通常不是程序员**，不懂技术名词，也没写过产品文档。你需要像一个耐心的同事那样跟他聊天。

当前项目标题：{project_title}
目标仓库：{repo_name}

沟通原则：
1. **用大白话**，避免以下术语：用户故事、PRD、MVP、UX/UI、边界条件、非功能需求、验收标准、API、接口、模型、字段、SOP、用户角色、流程图……能换成人话就换。如果对方先用了某个术语，可以跟着用。
2. **一次只问 1-3 个最关键的问题**，不要一次塞一堆。多用具体例子或二选一让对方好回答。
3. **从对方实际工作场景出发**：他在哪个环节卡住、想做什么操作、做完之后想得到什么结果。
4. 信息差不多了就**用一段话复述你理解的需求**让对方确认，并提示「如果没问题，回复 #确认 我就把它整理成开发任务」。
5. 回复**简短直接**，不要客套话，不要自称 AI 或模型。
6. 结合目标仓库 {repo_name} 的实际定位回应，避免给出明显不符的方案。
7. **当你判断已经聊清楚需求**（关键功能点、用户角色、操作流程都明确了），在回复**最后一行**单独输出 `[READY_TO_CONFIRM]`。系统会据此追加确认提示。**未达到该程度时不要输出此标记**——宁可多问一轮。

记住：你不是在写文档，你是在跟一个忙碌的业务同事聊天，让他舒服地把脑子里想要的东西说出来。
"""
```

- [ ] **Step 2: Add helper that detects + strips the marker**

In `backend/app/agents/pm_agent.py`, after the existing imports add:

```python
READY_MARKER = "[READY_TO_CONFIRM]"


def has_ready_marker(text: str) -> bool:
    return READY_MARKER in (text or "")


def strip_ready_marker(text: str) -> str:
    if not text:
        return text
    return text.replace(READY_MARKER, "").rstrip()
```

These are module-level (top of file, after imports but before `class PMAgent`).

- [ ] **Step 3: Add summary-and-confirm builder**

Add this method to `PMAgent`:

```python
    def build_confirm_hint(self) -> str:
        return (
            "\n\n如果上面理解没问题，请回复『确认』，我就把它提交审核。\n"
            "如果还要调整，直接告诉我哪里要改即可。"
        )
```

- [ ] **Step 4: Quick smoke test**

```bash
cd backend && python -c "
from app.agents.pm_agent import has_ready_marker, strip_ready_marker, PMAgent
assert has_ready_marker('hello [READY_TO_CONFIRM]')
assert not has_ready_marker('plain text')
assert strip_ready_marker('hello [READY_TO_CONFIRM]') == 'hello'
assert strip_ready_marker('[READY_TO_CONFIRM]') == ''
hint = PMAgent.__new__(PMAgent).build_confirm_hint()
assert '确认' in hint
print('marker helpers ok')
"
```
Expected: `marker helpers ok`

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/prompts/pm_prompts.py backend/app/agents/pm_agent.py
git commit -m "feat(pm_agent): in-band [READY_TO_CONFIRM] marker + confirm hint"
```

---

## Task 9: Intent prompts module

**Files:**
- Create: `backend/app/agents/prompts/intent_prompts.py`

- [ ] **Step 1: Create the prompts file**

Create `backend/app/agents/prompts/intent_prompts.py`:

```python
"""Prompts for group-bound natural language intent classification."""

CONFIRM_VERIFY_PROMPT = """你是用于核对用户是否同意进入开发的 AI 守门员。

下面是某项目的需求摘要 / 当前 PRD 草稿：
{summary}

最近 5 条对话：
{history}

用户刚刚发的消息：
"{content}"

请回答：用户是否在明确同意进入"开发审核"阶段？
- 答 yes 当且仅当用户的"同意"是确定的、无保留的（如"确认"、"开发吧"、"可以了"）
- 答 no 当用户表达不确定、提问、或讨论中（如"我觉得可以"、"应该差不多吧"、"这样确认下"、"确认一下没问题再说"）

只输出一个词：yes 或 no。
"""


def render_confirm_verify_prompt(
    summary: str,
    history_lines: list[str],
    content: str,
) -> str:
    safe_summary = (summary or "(无)").strip() or "(无)"
    safe_history = "\n".join(history_lines[-5:]) if history_lines else "(无)"
    return CONFIRM_VERIFY_PROMPT.format(
        summary=safe_summary,
        history=safe_history,
        content=content.strip(),
    )
```

- [ ] **Step 2: Smoke test**

```bash
cd backend && python -c "
from app.agents.prompts.intent_prompts import render_confirm_verify_prompt
out = render_confirm_verify_prompt('登录页加扫码', ['用户: 加上 OAuth', 'AI: 好的'], '确认')
assert 'yes 或 no' in out
assert '登录页加扫码' in out
assert '确认' in out
print('intent prompt ok')
"
```
Expected: `intent prompt ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/agents/prompts/intent_prompts.py
git commit -m "feat(prompts): add CONFIRM_VERIFY_PROMPT for intent verification"
```

---

## Task 10: GroupIntentClassifier — heuristic layer + LLM verifier

**Files:**
- Create: `backend/app/services/group_intent.py`
- Create: `backend/tests/e2e_group_intent.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/e2e_group_intent.py`:

```python
"""End-to-end smoke for GroupIntentClassifier (heuristic + LLM verifier).

LLM is fully mocked via a recorder so this runs without external services.
"""
from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "shared"))

from app.services.group_intent import (  # noqa: E402
    GroupIntentClassifier,
    Intent,
)


@dataclass
class FakeProject:
    id: int = 1
    status: str = "drafting"
    prd_content: str | None = None


@dataclass
class FakeSession:
    active_project_id: int | None = None
    state: str = "idle"


@dataclass
class FakeUser:
    id: int = 1
    role: str = "user"


class FakeLLM:
    def __init__(self, answer: str = "yes") -> None:
        self.answer = answer
        self.calls: list[list[dict]] = []

    async def chat(self, messages):
        self.calls.append(messages)

        class _Resp:
            def __init__(self, content): self.content = content
        return _Resp(self.answer)


def test_legacy_command_passes_through() -> None:
    clf = GroupIntentClassifier(llm=FakeLLM())
    user = FakeUser()
    session = FakeSession()
    res = asyncio.run(clf.classify(user, session, None, "#新需求 sandbox 测试"))
    assert res.intent == Intent.LEGACY_COMMAND, res
    print("legacy command passthrough ok")


def test_short_or_emoji_is_other() -> None:
    clf = GroupIntentClassifier(llm=FakeLLM())
    user = FakeUser()
    session = FakeSession()
    for text in ("", "!", "?", "🤔", "  "):
        res = asyncio.run(clf.classify(user, session, None, text))
        assert res.intent == Intent.OTHER, (text, res)
    print("other intent ok")


def test_admin_review_pattern() -> None:
    clf = GroupIntentClassifier(llm=FakeLLM())
    admin = FakeUser(role="admin")
    session = FakeSession()
    res = asyncio.run(clf.classify(admin, session, None, "通过项目 #123"))
    assert res.intent == Intent.REVIEW
    assert res.review_project_id == 123
    assert res.review_decision == "通过"
    assert res.review_reason == ""

    res2 = asyncio.run(clf.classify(admin, session, None, "拒绝项目 #45 理由是 PRD 不全"))
    assert res2.intent == Intent.REVIEW
    assert res2.review_project_id == 45
    assert res2.review_decision == "拒绝"
    assert res2.review_reason == "PRD 不全"

    # Non-admin same text -> not REVIEW
    user = FakeUser(role="user")
    res3 = asyncio.run(clf.classify(user, session, None, "通过项目 #123"))
    assert res3.intent != Intent.REVIEW
    print("admin review pattern ok")


def test_status_keyword() -> None:
    clf = GroupIntentClassifier(llm=FakeLLM())
    user = FakeUser()
    session = FakeSession(active_project_id=1)
    project = FakeProject()
    for text in ("现在到哪一步了", "怎么样了", "进度如何", "进展呢"):
        res = asyncio.run(clf.classify(user, session, project, text))
        assert res.intent == Intent.STATUS, (text, res)
    print("status keyword ok")


def test_no_active_project_starts_new() -> None:
    clf = GroupIntentClassifier(llm=FakeLLM())
    user = FakeUser()
    session = FakeSession(active_project_id=None)
    res = asyncio.run(clf.classify(user, session, None, "我想加个登录功能"))
    assert res.intent == Intent.NEW_PROJECT
    assert res.content_for_handler == "我想加个登录功能"
    print("new_project ok")


def test_modify_keyword_when_reviewing() -> None:
    clf = GroupIntentClassifier(llm=FakeLLM())
    user = FakeUser()
    session = FakeSession(active_project_id=1, state="confirming")
    project = FakeProject(status="reviewing", prd_content="some prd")
    res = asyncio.run(clf.classify(user, session, project, "改一下登录按钮位置"))
    assert res.intent == Intent.MODIFY
    print("modify keyword ok")


def test_confirm_candidate_llm_yes() -> None:
    llm = FakeLLM(answer="yes")
    clf = GroupIntentClassifier(llm=llm)
    user = FakeUser()
    session = FakeSession(active_project_id=1, state="chatting")
    project = FakeProject(status="drafting", prd_content="登录页加扫码")
    res = asyncio.run(clf.classify(user, session, project, "确认", history_lines=["AI: 我这样理解…"]))
    assert res.intent == Intent.CONFIRM
    assert len(llm.calls) == 1
    print("confirm yes ok")


def test_confirm_candidate_llm_no() -> None:
    llm = FakeLLM(answer="no")
    clf = GroupIntentClassifier(llm=llm)
    user = FakeUser()
    session = FakeSession(active_project_id=1, state="chatting")
    project = FakeProject(status="drafting", prd_content="登录页加扫码")
    res = asyncio.run(clf.classify(user, session, project, "确认下没问题再说", history_lines=["AI: 我这样理解…"]))
    assert res.intent == Intent.CHAT, res
    print("confirm no -> chat ok")


def test_confirm_candidate_llm_timeout_falls_back_to_chat() -> None:
    class TimeoutLLM:
        async def chat(self, messages):
            raise asyncio.TimeoutError("simulated")

    clf = GroupIntentClassifier(llm=TimeoutLLM())
    user = FakeUser()
    session = FakeSession(active_project_id=1, state="chatting")
    project = FakeProject(status="drafting", prd_content="x")
    res = asyncio.run(clf.classify(user, session, project, "确认"))
    assert res.intent == Intent.CHAT
    print("confirm timeout fallback ok")


def test_chat_default() -> None:
    clf = GroupIntentClassifier(llm=FakeLLM())
    user = FakeUser()
    session = FakeSession(active_project_id=1, state="chatting")
    project = FakeProject()
    res = asyncio.run(clf.classify(user, session, project, "再加上手机号绑定"))
    assert res.intent == Intent.CHAT
    print("chat default ok")


def main() -> None:
    test_legacy_command_passes_through()
    test_short_or_emoji_is_other()
    test_admin_review_pattern()
    test_status_keyword()
    test_no_active_project_starts_new()
    test_modify_keyword_when_reviewing()
    test_confirm_candidate_llm_yes()
    test_confirm_candidate_llm_no()
    test_confirm_candidate_llm_timeout_falls_back_to_chat()
    test_chat_default()
    print("\nall e2e_group_intent checks passed")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run, expect ImportError**

```bash
cd backend && python tests/e2e_group_intent.py
```
Expected: `ModuleNotFoundError: No module named 'app.services.group_intent'`

- [ ] **Step 3: Implement the classifier**

Create `backend/app/services/group_intent.py`:

```python
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from enum import Enum

from app.agents.prompts.intent_prompts import render_confirm_verify_prompt
from app.config import get_settings

logger = logging.getLogger(__name__)


class Intent(Enum):
    NEW_PROJECT = "new_project"
    CHAT = "chat"
    CONFIRM = "confirm"
    MODIFY = "modify"
    STATUS = "status"
    REVIEW = "review"
    OTHER = "other"
    LEGACY_COMMAND = "legacy_command"  # falls back to existing parse_command


@dataclass
class IntentResult:
    intent: Intent
    content_for_handler: str = ""  # text to pass to the handler
    review_project_id: int | None = None
    review_decision: str | None = None  # "通过" | "拒绝"
    review_reason: str = ""
    debug: dict | None = None


# Keyword sets — adjust freely; tests pin the *behavior*, not exact words.
_CONFIRM_WORDS = (
    "确认", "通过", "同意", "可以了", "开发吧", "没问题",
    "就这样", "ok 了", "好了就这", "可以开始",
)
_MODIFY_WORDS = ("改", "调", "不对", "重新", "再")
_STATUS_WORDS = ("进度", "状态", "到哪", "怎么样", "进展")

_REVIEW_RE = re.compile(
    r"^(?P<decision>通过|拒绝)项目\s*#?\s*(?P<id>\d+)(?:\s+理由是\s*(?P<reason>.+))?\s*$"
)
_EMOJI_PUNCT_RE = re.compile(
    r"^[\s\W_]*$"  # whitespace, punctuation, emoji-ish
)


class GroupIntentClassifier:
    def __init__(self, llm) -> None:
        self.llm = llm
        self._settings = get_settings()

    async def classify(
        self,
        user,
        session,
        project,
        content: str,
        history_lines: list[str] | None = None,
    ) -> IntentResult:
        text = (content or "").strip()
        if not text:
            return IntentResult(intent=Intent.OTHER)

        # 1. Legacy `#` commands — let parse_command handle.
        if text.startswith("#"):
            return IntentResult(intent=Intent.LEGACY_COMMAND, content_for_handler=text)

        # 2. Too short / pure punctuation / emoji-only.
        if len(text) < 2 or _EMOJI_PUNCT_RE.match(text):
            return IntentResult(intent=Intent.OTHER)

        # 3. Admin natural-language review.
        if getattr(user, "role", None) == "admin":
            m = _REVIEW_RE.match(text)
            if m:
                return IntentResult(
                    intent=Intent.REVIEW,
                    review_project_id=int(m.group("id")),
                    review_decision=m.group("decision"),
                    review_reason=(m.group("reason") or "").strip(),
                )

        # 4. Status query.
        if any(kw in text for kw in _STATUS_WORDS):
            return IntentResult(intent=Intent.STATUS)

        active_id = getattr(session, "active_project_id", None)
        proj_status = getattr(project, "status", None) if project is not None else None

        # 5. MODIFY: reviewing project + modify keyword.
        if (
            active_id is not None
            and proj_status == "reviewing"
            and any(kw in text for kw in _MODIFY_WORDS)
        ):
            return IntentResult(intent=Intent.MODIFY, content_for_handler=text)

        # 6. CONFIRM candidate: active drafting/reviewing + confirm word -> LLM verify.
        if (
            active_id is not None
            and proj_status in {"drafting", "reviewing"}
            and any(kw in text for kw in _CONFIRM_WORDS)
        ):
            verified = await self._verify_confirm_with_llm(
                summary=getattr(project, "prd_content", None) or "",
                history_lines=history_lines or [],
                content=text,
            )
            if verified:
                return IntentResult(intent=Intent.CONFIRM)
            return IntentResult(
                intent=Intent.CHAT,
                content_for_handler=text,
                debug={"confirm_rejected_by_llm": True},
            )

        # 7. NEW_PROJECT: no active project.
        if active_id is None:
            return IntentResult(intent=Intent.NEW_PROJECT, content_for_handler=text)

        # 8. Default: CHAT.
        return IntentResult(intent=Intent.CHAT, content_for_handler=text)

    async def _verify_confirm_with_llm(
        self,
        summary: str,
        history_lines: list[str],
        content: str,
    ) -> bool:
        prompt = render_confirm_verify_prompt(summary, history_lines, content)
        timeout = self._settings.intent_llm_timeout_seconds
        try:
            response = await asyncio.wait_for(
                self.llm.chat([{"role": "user", "content": prompt}]),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("intent_classify confirm verify timeout fallback=chat")
            return False
        except Exception:
            logger.exception("intent_classify confirm verify failed fallback=chat")
            return False

        answer = (getattr(response, "content", "") or "").strip().lower()
        decision = answer.startswith("yes")
        logger.info(
            "intent_classify confirm verify llm_answer=%r decision=%s",
            answer[:40],
            decision,
        )
        return decision
```

- [ ] **Step 4: Run tests until they pass**

```bash
cd backend && python tests/e2e_group_intent.py
```
Expected: every test prints "ok" then `all e2e_group_intent checks passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/group_intent.py backend/tests/e2e_group_intent.py
git commit -m "feat(group_intent): heuristic + LLM-verified intent classifier"
```

---

## Task 11: Refactor MessageHandler — extract `_handle_*_internal` methods

**Files:**
- Modify: `backend/app/services/message_handler.py`

This is a **pure refactor**: behavior unchanged, just exposes inner methods that don't depend on `Command` so the GroupMessageRouter can call them with already-classified intents.

- [ ] **Step 1: Add `_handle_new_project_internal` and have `_handle_new_project` delegate**

In `backend/app/services/message_handler.py`, **add** this method right after `_handle_new_project`:

```python
    async def _handle_new_project_internal(
        self,
        user: User,
        session: UserSession,
        wechat_user_id: str,
        repo: Repo,
        desc: str,
        group_id: str | None,
    ) -> str:
        """Variant of _handle_new_project where (repo, desc) are already resolved
        — used by GroupMessageRouter when the bound group implies the repo.
        """
        project = await self.project_service.create_project(
            repo_id=repo.id,
            title=self._build_project_title(desc),
            creator_id=user.id,
            wechat_group_id=group_id,
        )
        await self.session_manager.update_session_state(
            session,
            SessionState.CHATTING,
            project.id,
        )
        await self.project_service.add_message(project.id, wechat_user_id, "user", desc)

        ai_reply = await self.pm_agent.chat(project, repo, [], desc)
        await self.project_service.add_message(project.id, wechat_user_id, "assistant", ai_reply)

        return (
            f"已在仓库「{repo.name}」下创建需求会话：[{project.id}] {project.title}\n\n"
            f"{ai_reply}\n\n"
            "需求沟通完成后回复『确认』即可生成方案。"
        )
```

Then refactor `_handle_new_project` to use it:

```python
    async def _handle_new_project(
        self,
        user: User,
        session: UserSession,
        wechat_user_id: str,
        command: Command,
        group_id: str | None = None,
    ) -> str:
        repo_name = str(command.args.get("repo", "")).strip()
        desc = str(command.args.get("desc", "")).strip()
        if not repo_name or not desc:
            return "新需求指令格式不正确，请使用：#新需求 <仓库> <需求描述>"

        repo = await self.project_service.get_repo_by_name(repo_name)
        if repo is None:
            return f"未找到仓库「{repo_name}」，请检查仓库别名后重试。"

        if not await self._user_can_access_repo(user, repo.id):
            return (
                f"你还没有「{repo_name}」的提需求权限，请联系管理员开通后再试。\n"
                "可发送 #我的仓库 查看你当前能提需求的仓库。"
            )

        return await self._handle_new_project_internal(
            user, session, wechat_user_id, repo, desc, group_id=group_id
        )
```

- [ ] **Step 2: Add `_handle_chat_internal`**

Add after `_handle_chat`:

```python
    async def _handle_chat_internal(
        self,
        user: User,
        session: UserSession,
        wechat_user_id: str,
        content: str,
    ) -> str:
        del user
        if not content.strip():
            return "请输入要补充的需求内容。"

        project, repo, error_reply = await self._get_active_project_context(session)
        if error_reply is not None or project is None or repo is None:
            return error_reply or "当前没有可继续沟通的项目。"

        if (
            project.status == ProjectStatus.REVIEWING.value
            or session.state == SessionState.CONFIRMING.value
        ):
            return "当前方案已生成，如需调整请直接说『改一下…』或回复『确认』提交审核。"

        if session.state == SessionState.SCORING.value:
            return "当前项目正在等待评分，请发送 #评分 <1-10> <反馈>。"

        if project.status != ProjectStatus.DRAFTING.value:
            return f"当前项目状态为「{self._status_label(project.status)}」，不在需求沟通阶段。"

        history = await self.project_service.get_messages(project.id)
        await self.project_service.add_message(project.id, wechat_user_id, "user", content)
        await self.session_manager.update_session_state(session, SessionState.CHATTING, project.id)

        ai_reply = await self.pm_agent.chat(project, repo, history, content)
        await self.project_service.add_message(project.id, wechat_user_id, "assistant", ai_reply)
        return ai_reply
```

Then update `_handle_chat` to delegate:

```python
    async def _handle_chat(
        self,
        user: User,
        session: UserSession,
        wechat_user_id: str,
        command: Command,
    ) -> str:
        content = str(command.args.get("content", "")).strip()
        return await self._handle_chat_internal(user, session, wechat_user_id, content)
```

- [ ] **Step 3: Add `_handle_modify_internal`, `_handle_status_internal`**

Apply the same delegation pattern:

```python
    async def _handle_modify_internal(
        self,
        user: User,
        session: UserSession,
        wechat_user_id: str,
        feedback: str,
    ) -> str:
        del user
        if not feedback.strip():
            return "请告诉我具体要怎么改。"

        project, repo, error_reply = await self._get_active_project_context(session)
        if error_reply is not None or project is None or repo is None:
            return error_reply or "当前没有可修改的项目。"

        if not project.prd_content:
            return "当前项目还没有生成开发方案，请先继续聊清楚再回复『确认』。"

        if project.status == ProjectStatus.COMPLETED.value:
            return "当前项目已经完成，不能再修改方案。"

        if project.status not in {ProjectStatus.REVIEWING.value, ProjectStatus.REJECTED.value}:
            return f"当前项目状态为「{self._status_label(project.status)}」，暂时不能修改方案。"

        history = await self.project_service.get_messages(project.id)
        await self.project_service.add_message(project.id, wechat_user_id, "user", feedback)

        updated_prd = await self.pm_agent.modify_prd(
            project, repo, history, project.prd_content, feedback
        )
        await self.project_service.save_prd(project, updated_prd)
        await self.project_service.update_status(project, ProjectStatus.REVIEWING)
        await self.session_manager.update_session_state(
            session, SessionState.CONFIRMING, project.id
        )
        await self.project_service.add_message(
            project.id, wechat_user_id, "assistant",
            "方案已根据最新反馈完成更新。",
        )
        await self._notify_admins_for_review(project)

        return f"已根据你的反馈更新方案：\n\n{updated_prd}"


    async def _handle_status_internal(
        self,
        user: User,
        session: UserSession,
    ) -> str:
        return await self._handle_status(user, session)
```

Then refactor existing `_handle_modify` to delegate:

```python
    async def _handle_modify(
        self,
        user: User,
        session: UserSession,
        wechat_user_id: str,
        command: Command,
    ) -> str:
        feedback = str(command.args.get("content", "")).strip()
        return await self._handle_modify_internal(user, session, wechat_user_id, feedback)
```

- [ ] **Step 4: Reuse `_handle_confirm` and `_handle_review_command` as-is**

`_handle_confirm` doesn't need command args — just rename calls when needed; the existing signature `(user, session, wechat_user_id)` is fine.

`_handle_review_command` already takes a `Command` but its only fields are `project_id`, `decision`, `reason` — so add a thin internal:

```python
    async def _handle_review_internal(
        self,
        user: User,
        project_id: int,
        decision: str,
        reason: str,
    ) -> str:
        # Synthesize a Command and call existing logic — keeps audit/log paths identical.
        cmd = Command(
            type="review",
            args={"project_id": project_id, "decision": decision, "reason": reason},
        )
        return await self._handle_review_command(user, cmd)
```

(`Command` is already imported at top of file.)

- [ ] **Step 5: Add output `[READY_TO_CONFIRM]` strip in the `handle` send path**

In `MessageHandler.handle`, **before** the `if reply:` block, normalize the reply:

```python
        from app.agents.pm_agent import has_ready_marker, strip_ready_marker

        if reply and has_ready_marker(reply):
            cleaned = strip_ready_marker(reply)
            reply = cleaned + self.pm_agent.build_confirm_hint() if cleaned else self.pm_agent.build_confirm_hint().lstrip()
```

(Move the import to the top of the file with the other `from app.agents` import.)

- [ ] **Step 6: Run regression test**

```bash
cd backend && python tests/e2e_group_chat.py && python tests/e2e_review_command.py
```
Expected: both print their existing "ok" lines without errors.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/message_handler.py
git commit -m "refactor(message_handler): extract _handle_*_internal + strip [READY_TO_CONFIRM]"
```

---

## Task 12: Auto-activation helper for first-time bound-group senders

**Files:**
- Modify: `backend/app/services/session_manager.py`

- [ ] **Step 1: Add `get_or_create_user_for_bound_group` method**

In `backend/app/services/session_manager.py`, add this method to `SessionManager` (right after `get_or_create_user`):

```python
    async def get_or_create_user_for_bound_group(
        self,
        wechat_user_id: str,
        auto_activate: bool,
    ) -> tuple[User, bool]:
        """Like get_or_create_user, but auto-activates whitelist for *new* users
        when they first speak in a bound group. Returns (user, was_just_created).
        """
        stmt = select(User).where(User.wechat_user_id == wechat_user_id)
        existing = (await self.db.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            return existing, False

        user = User(wechat_user_id=wechat_user_id)
        if auto_activate:
            user.is_active = True
        self.db.add(user)
        await self.db.flush()
        return user, True
```

- [ ] **Step 2: Smoke test**

```bash
cd backend && python -c "
import inspect
from app.services.session_manager import SessionManager
sig = inspect.signature(SessionManager.get_or_create_user_for_bound_group)
assert 'auto_activate' in sig.parameters
print('session_manager helper ok')
"
```
Expected: `session_manager helper ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/session_manager.py
git commit -m "feat(session_manager): auto-activate whitelist for bound-group first-timers"
```

---

## Task 13: GroupMessageRouter — wire intent → handler

**Files:**
- Create: `backend/app/services/group_message_router.py`
- Create: `backend/tests/e2e_group_router.py`

- [ ] **Step 1: Write failing test**

Create `backend/tests/e2e_group_router.py`:

```python
"""End-to-end smoke for GroupMessageRouter — composes intent classification +
handler dispatch + auto-activation. Uses recording WeChat + stub LLM.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "shared"))

from app.database import AsyncSessionLocal  # noqa: E402
from app.services.group_message_router import GroupMessageRouter  # noqa: E402


class RecordingWeChat:
    def __init__(self) -> None:
        self.sent: list = []

    async def send_text(self, user_id, msg):
        self.sent.append(("text", user_id, msg))
        return {"status": "ok"}

    async def send_at_group(self, group_id, at_list, msg):
        self.sent.append(("at_group", group_id, at_list, msg))
        return {"status": "ok"}


class StubLLM:
    """Always answers 'no' for confirm-verify so we never accidentally promote."""
    async def chat(self, messages):
        class _R:
            content = "no"
        return _R()


async def test_unbound_group_returns_handled_false() -> None:
    """A group not in repos.wechat_group_id should return handled=False."""
    async with AsyncSessionLocal() as db:
        wechat = RecordingWeChat()
        router = GroupMessageRouter(db, wechat, llm=StubLLM())
        handled = await router.try_handle(
            wechat_user_id="user-x",
            group_id="R:NOT_BOUND",
            content="我想加个登录",
        )
        assert handled is False
    print("unbound group passthrough ok")


async def test_bound_group_full_flow() -> None:
    """Full flow only runs when env points at a real bound repo."""
    repo_id_env = os.environ.get("BIND_GROUP_TEST_REPO_ID")
    group_id_env = os.environ.get("BIND_GROUP_TEST_GROUP_ID")
    if not (repo_id_env and group_id_env):
        print("set BIND_GROUP_TEST_REPO_ID + BIND_GROUP_TEST_GROUP_ID to run e2e router test")
        return

    async with AsyncSessionLocal() as db:
        wechat = RecordingWeChat()
        router = GroupMessageRouter(db, wechat, llm=StubLLM())
        handled = await router.try_handle(
            wechat_user_id="router-test-user-001",
            group_id=group_id_env,
            content="我想加一个简单的待办列表，可以勾选完成",
        )
        assert handled is True
        # The recording wechat should have at least one send_at_group call
        assert any(s[0] == "at_group" for s in wechat.sent), wechat.sent
    print("bound group flow ok")


def main() -> None:
    asyncio.run(test_unbound_group_returns_handled_false())
    asyncio.run(test_bound_group_full_flow())
    print("all e2e_group_router checks passed")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run, expect ImportError**

```bash
cd backend && python tests/e2e_group_router.py
```
Expected: `ModuleNotFoundError: No module named 'app.services.group_message_router'`

- [ ] **Step 3: Implement the router**

Create `backend/app/services/group_message_router.py`:

```python
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import PMAgent
from app.config import get_settings
from app.gateway.command_parser import parse_command
from app.gateway.wechat_client import WeChatClient
from app.llm import create_llm
from app.models import Project, Repo, User
from app.services.group_intent import GroupIntentClassifier, Intent, IntentResult
from app.services.message_handler import MessageHandler
from app.services.project_service import ProjectService
from app.services.session_manager import SessionManager

logger = logging.getLogger(__name__)


class GroupMessageRouter:
    def __init__(
        self,
        db: AsyncSession,
        wechat: WeChatClient,
        llm=None,
    ) -> None:
        self.db = db
        self.wechat = wechat
        self.settings = get_settings()
        # Use a dedicated lightweight LLM if intent_llm_model is set; otherwise reuse default.
        # For simplicity v1, share the same LLM with PMAgent — distinct provider knob is in
        # config and can be wired later without changing call sites.
        self.intent_llm = llm or create_llm()
        self.session_manager = SessionManager(db)
        self.project_service = ProjectService(db)
        self.handler = MessageHandler(db, wechat)
        self.classifier = GroupIntentClassifier(llm=self.intent_llm)

    async def try_handle(
        self,
        wechat_user_id: str,
        group_id: str,
        content: str,
    ) -> bool:
        """Returns True iff this group is bound and the message has been routed."""
        repo = await self.project_service.get_repo_by_wechat_group_id(group_id)
        if repo is None:
            return False

        try:
            await self._handle_bound(repo, wechat_user_id, group_id, content)
            await self.db.commit()
        except Exception:
            logger.exception(
                "bound_group_route failed group=%s repo=%s sender=%s",
                group_id, repo.id, wechat_user_id,
            )
            await self.db.rollback()
        return True

    async def _handle_bound(
        self,
        repo: Repo,
        wechat_user_id: str,
        group_id: str,
        content: str,
    ) -> None:
        # 1. Resolve user (auto-activate if first-timer).
        user, just_created = await self.session_manager.get_or_create_user_for_bound_group(
            wechat_user_id,
            auto_activate=self.settings.group_bound_auto_activate,
        )
        if just_created:
            logger.info(
                "auto_activate user=%s via bound_group=%s repo=%s",
                wechat_user_id, group_id, repo.id,
            )

        # 2. Whitelist gate (still applies if auto_activate=False or admin override).
        if user.role != "admin" and not user.is_active:
            logger.info(
                "Whitelist gate: dropping message from inactive user wechat_user_id=%s",
                wechat_user_id,
            )
            return

        session = await self.session_manager.get_session(user)
        project: Project | None = None
        if session.active_project_id is not None:
            project = await self.project_service.get_project(session.active_project_id)

        # 3. Classify.
        history_lines: list[str] = []
        if project is not None:
            messages = await self.project_service.get_messages(project.id)
            history_lines = [
                f"{m.role}: {m.content}" for m in messages[-5:]
            ]
        result = await self.classifier.classify(
            user, session, project, content, history_lines=history_lines
        )

        logger.info(
            "bound_group_route group=%s repo=%s sender=%s intent=%s",
            group_id, repo.id, wechat_user_id, result.intent.value,
        )

        # 4. Dispatch.
        reply = await self._dispatch(
            result, user, session, wechat_user_id, group_id, repo, content
        )

        # 5. Send reply (mirror MessageHandler.handle's send pattern).
        if not reply:
            return

        # Strip [READY_TO_CONFIRM] marker if present.
        from app.agents.pm_agent import has_ready_marker, strip_ready_marker
        if has_ready_marker(reply):
            cleaned = strip_ready_marker(reply)
            reply = (cleaned + self.handler.pm_agent.build_confirm_hint()) if cleaned \
                else self.handler.pm_agent.build_confirm_hint().lstrip()

        try:
            at_label = (user.nickname if hasattr(user, "nickname") and user.nickname else None) or wechat_user_id
            await self.wechat.send_at_group(
                group_id, [wechat_user_id], f"@{at_label} {reply}"
            )
        except Exception:
            logger.exception(
                "send_at_group failed group=%s sender=%s", group_id, wechat_user_id
            )

    async def _dispatch(
        self,
        result: IntentResult,
        user: User,
        session,
        wechat_user_id: str,
        group_id: str,
        repo: Repo,
        original_content: str,
    ) -> str:
        match result.intent:
            case Intent.LEGACY_COMMAND:
                # Fall back to existing parse_command + MessageHandler flow.
                cmd = parse_command(result.content_for_handler)
                return await self.handler.handle(wechat_user_id, cmd, group_id=group_id) \
                    or ""
            case Intent.OTHER:
                return ""
            case Intent.NEW_PROJECT:
                return await self.handler._handle_new_project_internal(
                    user, session, wechat_user_id, repo, original_content,
                    group_id=group_id,
                )
            case Intent.CHAT:
                return await self.handler._handle_chat_internal(
                    user, session, wechat_user_id, original_content
                )
            case Intent.CONFIRM:
                return await self.handler._handle_confirm(
                    user, session, wechat_user_id
                )
            case Intent.MODIFY:
                return await self.handler._handle_modify_internal(
                    user, session, wechat_user_id, original_content
                )
            case Intent.STATUS:
                return await self.handler._handle_status_internal(user, session)
            case Intent.REVIEW:
                if (
                    result.review_project_id is None
                    or result.review_decision is None
                ):
                    return "审核命令解析失败，请使用「通过项目 #ID」或「拒绝项目 #ID 理由是 …」。"
                return await self.handler._handle_review_internal(
                    user,
                    result.review_project_id,
                    result.review_decision,
                    result.review_reason,
                )
            case _:
                logger.warning("unknown intent %s — falling back to chat", result.intent)
                return await self.handler._handle_chat_internal(
                    user, session, wechat_user_id, original_content
                )
```

- [ ] **Step 4: Run smoke test**

```bash
cd backend && python tests/e2e_group_router.py
```
Expected (without env): `unbound group passthrough ok` + `set BIND_GROUP_TEST_REPO_ID...` + `all e2e_group_router checks passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/group_message_router.py backend/tests/e2e_group_router.py
git commit -m "feat(group_router): wire intent classification to handler dispatch"
```

---

## Task 14: wechat_gateway — branch on bound group

**Files:**
- Modify: `backend/app/gateway/wechat_gateway.py:29-98`

- [ ] **Step 1: Add the bound-group fast path**

Edit `backend/app/gateway/wechat_gateway.py`. **Replace** the body of `_process_message_async` and `receive_message` with the version below:

```python
async def _process_message_async(
    user_id: str,
    command: Command,
    group_id: str | None = None,
) -> None:
    async with AsyncSessionLocal() as db:
        try:
            handler = MessageHandler(db, wechat)
            await handler.handle(user_id, command, group_id=group_id)
        except Exception:
            logger.exception(
                "Background message processing failed for user_id=%s group_id=%s command=%s",
                user_id, group_id, command.type,
            )


async def _process_bound_group_message_async(
    user_id: str,
    group_id: str,
    content: str,
) -> None:
    from app.services.group_message_router import GroupMessageRouter

    async with AsyncSessionLocal() as db:
        try:
            router = GroupMessageRouter(db, wechat)
            handled = await router.try_handle(user_id, group_id, content)
            if handled:
                return
            # Group is no longer bound — fall back to legacy parse_command path.
            cmd = parse_command(content)
            handler = MessageHandler(db, wechat)
            await handler.handle(user_id, cmd, group_id=group_id)
        except Exception:
            logger.exception(
                "Bound-group processing failed user_id=%s group_id=%s",
                user_id, group_id,
            )


@router.post("/msg")
async def receive_message(
    message: VWorkMessage,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    if message.is_self_msg == 1:
        logger.debug("Ignoring self message: msg_id=%s", message.msg_id)
        return {"status": "ok"}

    if message.msg_type != VWorkMsgType.TEXT.value:
        logger.info(
            "Ignoring non-text message: msg_id=%s msg_type=%s",
            message.msg_id, message.msg_type,
        )
        return {"status": "ok"}

    if not isinstance(message.content, str):
        logger.warning(
            "Ignoring text payload with non-string content: msg_id=%s",
            message.msg_id,
        )
        return {"status": "ok"}

    is_group = bool(message.sender)
    if is_group:
        at_list = message.at_list or []
        if message.self_user_id not in at_list and "notify@all" not in at_list:
            logger.debug(
                "Ignoring group message without @bot: msg_id=%s group_id=%s sender=%s",
                message.msg_id, message.user_id, message.sender,
            )
            return {"status": "ok"}
        sender_id = message.sender
        group_id: str | None = message.user_id
        content_text = _strip_at_prefix(message.content)
    else:
        sender_id = message.user_id
        group_id = None
        content_text = message.content

    # Bound-group fast path: if this group is bound to a repo, route through
    # the natural-language router. Otherwise fall back to legacy parse_command.
    if group_id is not None:
        logger.info(
            "Received WeChat message: msg_id=%s user=%s group=%s (deferring routing decision to bound check)",
            message.msg_id, sender_id, group_id,
        )
        background_tasks.add_task(
            _process_bound_group_message_async, sender_id, group_id, content_text
        )
        return {"status": "ok"}

    command = parse_command(content_text)
    logger.info(
        "Received WeChat message: msg_id=%s user=%s group=%s command=%s",
        message.msg_id, sender_id, group_id, command.type,
    )
    background_tasks.add_task(_process_message_async, sender_id, command, group_id)
    return {"status": "ok"}
```

- [ ] **Step 2: Smoke test gateway helpers (regression)**

```bash
cd backend && python tests/e2e_group_chat.py
```
Expected: `strip_at_prefix ok`, `group_vs_private_routing ok`, `notify_at_group_message_shape ok`, `all e2e_group_chat checks passed`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/gateway/wechat_gateway.py
git commit -m "feat(gateway): branch bound-group messages to natural language router"
```

---

## Task 15: Full bound-group end-to-end test

**Files:**
- Modify: `backend/tests/e2e_group_router.py` (extend `test_bound_group_full_flow`)

- [ ] **Step 1: Add a multi-turn end-to-end test**

Add to `backend/tests/e2e_group_router.py` (above `def main()`):

```python
async def test_bound_group_multi_turn_flow() -> None:
    """Three-turn flow: open requirement -> elaborate -> 确认 (LLM mocked yes)."""
    repo_id_env = os.environ.get("BIND_GROUP_TEST_REPO_ID")
    group_id_env = os.environ.get("BIND_GROUP_TEST_GROUP_ID")
    if not (repo_id_env and group_id_env):
        print("set BIND_GROUP_TEST_REPO_ID + BIND_GROUP_TEST_GROUP_ID to run multi-turn test")
        return

    user_id = "router-test-user-mt-001"

    class YesLLM:
        async def chat(self, messages):
            class _R:
                content = "yes"
            return _R()

    async with AsyncSessionLocal() as db:
        wechat = RecordingWeChat()
        router = GroupMessageRouter(db, wechat, llm=YesLLM())

        await router.try_handle(user_id, group_id_env, "我想做个简单的待办应用")
        await router.try_handle(user_id, group_id_env, "支持新增、勾选完成、删除三件事就行")
        # After two turns of context, user explicitly confirms.
        await router.try_handle(user_id, group_id_env, "确认")

    print("multi-turn flow ok (sent=%d)" % len(wechat.sent))


def main() -> None:
    asyncio.run(test_unbound_group_returns_handled_false())
    asyncio.run(test_bound_group_full_flow())
    asyncio.run(test_bound_group_multi_turn_flow())
    print("all e2e_group_router checks passed")
```

- [ ] **Step 2: Run with env**

When ready to test against a real DB:
```bash
cd backend && BIND_GROUP_TEST_REPO_ID=1 BIND_GROUP_TEST_GROUP_ID=R:GTEST_001 python tests/e2e_group_router.py
```
Expected: every test prints "ok"; final wechat.sent has at least 3 messages.

When env not set: prints skip lines + `all e2e_group_router checks passed`.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/e2e_group_router.py
git commit -m "test(group_router): add multi-turn bound-group flow"
```

---

## Task 16: Final regression sweep + manual smoke

**Files:** none (verification only).

- [ ] **Step 1: Run all e2e tests**

```bash
cd backend && for f in tests/e2e_*.py; do echo "=== $f ==="; python "$f" || echo "FAIL: $f"; done
```
Expected: every script prints its own "all … passed" line, no `FAIL:` lines.

- [ ] **Step 2: Boot the backend**

```bash
cd backend && uvicorn app.main:app --reload
```
In a separate shell, log into `/admin`, locate the repo with `wechat_group_id` UI, bind a test group via the form, verify:
- The repo row shows the group ID + 解绑 button.
- Try binding the same group to a second repo → expect 409.
- Unbind → repo returns to "未绑定" state.

- [ ] **Step 3: Live group test (optional, requires real WeChat)**

Per the `BIND_GROUP_TEST_*` env vars, send a real `@bot 我想加个登录功能` from a member of the bound group. Verify:
- Bot replies with a clarifying question.
- After 2-3 turns, bot reply ends with "请回复『确认』我就把它提交审核。"
- Reply "确认" → project moves to `reviewing` status, admin gets a review notification in the same group.
- Admin in the same group sends `通过项目 #N` → GitHub issue is created and creator is notified in-group.

- [ ] **Step 4: Final commit (if any docs/touch-ups needed)**

If anything was nudged, commit. Otherwise skip.

```bash
git status
# if clean: nothing to commit
```

---

## Self-Review Notes

**Spec coverage:**
- §3 Data model → Task 1 ✓
- §4 Bind/unbind UI + API → Tasks 5, 6, 7 ✓
- §5 Routing + intent classifier → Tasks 9, 10, 13, 14 ✓
- §5.7 PMAgent ready hint → Task 8 ✓
- §6 Review → existing logic + Task 10 (admin pattern) + Task 11 (`_handle_review_internal`) ✓
- §7 Edge cases:
  - Auto-activate first-time bound group sender → Task 12 + Task 13 ✓
  - Whitelist gate for unbound / private → preserved ✓
  - LLM timeout/error fail-safe → Task 10 (`_verify_confirm_with_llm`) ✓
  - `[READY_TO_CONFIRM]` strip → Task 11 step 5 + Task 13 ✓
  - SessionManager row lock → Task 4 ✓
  - Bind unique conflict 4xx → Task 6 ✓
- §8 Tests → Tasks 5, 10, 13, 15, 16 ✓
- §10 Settings → Task 2 ✓

**Placeholder check:** None of the steps say "TBD" / "fill in" / "similar to". All code is provided in full.

**Type/name consistency:**
- `Intent` enum members consistent across Tasks 10, 13.
- `IntentResult.content_for_handler` used in Tasks 10 and 13.
- `_handle_*_internal` signatures: Task 11 defines them; Task 13 calls them with matching args.
- `READY_MARKER` / `has_ready_marker` / `strip_ready_marker` defined in Task 8, used in Tasks 11 and 13.
- `RepoBindingService` raises `BindingConflictError` / `RepoNotFoundError`; Task 6 endpoint catches both.
- `GroupIntentClassifier.classify` signature `(user, session, project, content, history_lines=None)` consistent across Tasks 10, 13.

No drift detected.
