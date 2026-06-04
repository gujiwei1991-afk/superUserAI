"""确认意图的确定性护栏(无第三方依赖,可独立加载/单测)。

严格取向:只有"消息主体就是确认"才算确认候选。长需求文本里夹带
"确认/通过"等子串(如"装备确认中,增加一列规格…")一律不算 —— 否则会被
误判成 confirm、提前生成半成品 PRD、污染项目流程。
"""
from __future__ import annotations

import re

# 进入确认候选的关键词。命中只是"候选",最终仍由长度护栏 + LLM 复核裁决。
CONFIRM_WORDS: tuple[str, ...] = (
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
    "做吧",
    "嗯好",
    "好的就这",
    "这就开发",
    "可以开发",
    "提交吧",
    "提交审核",
)

# 去掉确认词后,剩余"实质字符"(中文/字母/数字)不超过该值,才算主体是确认。
# 取 5 给"好的确认下提交"这类留余量;更长的(在描述需求)一律判 False。
_RESIDUAL_MAX = 5

_NON_WORD_RE = re.compile(r"\W", re.UNICODE)  # 去标点/空白,保留中文/字母/数字


def is_confirmation_subject(text: str) -> bool:
    """这条消息的主体是否就是"确认"(而非长需求里夹带确认词)。"""
    residual = (text or "").strip()
    if not residual:
        return False
    if not any(kw in residual for kw in CONFIRM_WORDS):
        return False
    for kw in CONFIRM_WORDS:
        residual = residual.replace(kw, "")
    residual = _NON_WORD_RE.sub("", residual)
    return len(residual) <= _RESIDUAL_MAX
