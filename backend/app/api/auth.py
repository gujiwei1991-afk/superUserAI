from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Cookie, HTTPException, status
from jose import JWTError, jwt

from app.config import get_settings

ACCESS_TOKEN_COOKIE = "access_token"


def verify_admin_password(password: str) -> bool:
    if not password:
        return False
    expected = get_settings().jwt_secret
    return hmac.compare_digest(password, expected)


def create_access_token(
    subject: str,
    role: str,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    settings = get_settings()
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes),
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_token(token: str) -> dict[str, Any] | None:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        return None

    subject = payload.get("sub")
    role = payload.get("role")
    if not isinstance(subject, str) or not subject or not isinstance(role, str) or not role:
        return None

    return payload


def require_admin(
    access_token: str | None = Cookie(default=None, alias=ACCESS_TOKEN_COOKIE),
) -> dict[str, Any]:
    payload = verify_token(access_token) if access_token else None
    if payload is None or payload.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_302_FOUND,
            detail="Authentication required",
            headers={"Location": "/admin/login"},
        )

    return payload
