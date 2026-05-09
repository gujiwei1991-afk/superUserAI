from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Session as UserSession
from app.models import User
from shared.constants import SessionState


class SessionManager:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_or_create_user(self, wechat_user_id: str) -> User:
        stmt = select(User).where(User.wechat_user_id == wechat_user_id)
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        if user is not None:
            return user

        user = User(wechat_user_id=wechat_user_id)
        self.db.add(user)
        await self.db.flush()
        return user

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

    async def get_session(self, user: User) -> UserSession:
        stmt = select(UserSession).where(UserSession.user_id == user.id)
        result = await self.db.execute(stmt)
        session = result.scalar_one_or_none()
        if session is not None:
            return session

        session = UserSession(user_id=user.id, state=SessionState.IDLE.value)
        self.db.add(session)
        await self.db.flush()
        return session

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
