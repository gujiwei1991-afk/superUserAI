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
            def __init__(self, content):
                self.content = content

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
    res = asyncio.run(
        clf.classify(user, session, project, "确认", history_lines=["AI: 我这样理解…"])
    )
    assert res.intent == Intent.CONFIRM
    assert len(llm.calls) == 1
    print("confirm yes ok")


def test_confirm_candidate_llm_no() -> None:
    llm = FakeLLM(answer="no")
    clf = GroupIntentClassifier(llm=llm)
    user = FakeUser()
    session = FakeSession(active_project_id=1, state="chatting")
    project = FakeProject(status="drafting", prd_content="登录页加扫码")
    res = asyncio.run(
        clf.classify(
            user, session, project, "确认下没问题再说", history_lines=["AI: 我这样理解…"]
        )
    )
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
