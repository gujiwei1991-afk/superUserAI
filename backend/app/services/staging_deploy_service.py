"""Staging auto-deploy service.

Handles SSH-driven docker compose deploys to user's self-managed staging
server, triggered by GitHub PR webhooks.

Spec: docs/superpowers/specs/2026-05-10-staging-auto-deploy-design.md
"""
from __future__ import annotations

import logging

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
