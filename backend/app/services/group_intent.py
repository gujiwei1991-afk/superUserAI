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
    "确认",
    "通过",
    "同意",
    "可以了",
    "开发吧",
    "没问题",
    "就这样",
    "ok 了",
    "好了就这",
    "可以开始",
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
