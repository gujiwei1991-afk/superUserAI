"""Unit tests for StagingDeployService (mocked SSH + wechat).

Stand-alone runnable: `python tests/test_staging_deploy_service.py`.
Prints `all test_staging_deploy_service checks passed` on success.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "shared"))

from app.services.staging_deploy_service import _parse_ssh_target  # noqa: E402


def test_parse_target_user_at_host() -> None:
    user, host, port = _parse_ssh_target("deploy@server.com", default_user="fallback")
    assert (user, host, port) == ("deploy", "server.com", None), (user, host, port)
    print("parse user@host ok")


def test_parse_target_user_at_host_with_port() -> None:
    user, host, port = _parse_ssh_target("deploy@server.com:2222", default_user="fallback")
    assert (user, host, port) == ("deploy", "server.com", 2222), (user, host, port)
    print("parse user@host:port ok")


def test_parse_target_only_host_uses_default_user() -> None:
    user, host, port = _parse_ssh_target("server.com", default_user="deploy")
    assert (user, host, port) == ("deploy", "server.com", None), (user, host, port)
    print("parse host-only uses default_user ok")


def test_parse_target_only_host_with_port() -> None:
    user, host, port = _parse_ssh_target("server.com:2222", default_user="deploy")
    assert (user, host, port) == ("deploy", "server.com", 2222), (user, host, port)
    print("parse host:port uses default_user ok")


def test_parse_target_invalid_port_raises() -> None:
    try:
        _parse_ssh_target("deploy@server.com:abc", default_user="x")
    except ValueError:
        print("parse invalid port raises ValueError ok")
        return
    raise AssertionError("expected ValueError")


def test_parse_target_empty_raises() -> None:
    try:
        _parse_ssh_target("", default_user="x")
    except ValueError:
        print("parse empty raises ValueError ok")
        return
    raise AssertionError("expected ValueError")


def main() -> None:
    test_parse_target_user_at_host()
    test_parse_target_user_at_host_with_port()
    test_parse_target_only_host_uses_default_user()
    test_parse_target_only_host_with_port()
    test_parse_target_invalid_port_raises()
    test_parse_target_empty_raises()
    print("\nall test_staging_deploy_service checks passed")


if __name__ == "__main__":
    main()
