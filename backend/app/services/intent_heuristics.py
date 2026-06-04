"""意图护栏:判断一条消息是否"实质新需求"(无第三方依赖,可独立加载/单测)。

用于卡点 A:已完成项目下,只有够实质的消息才自动开新一轮需求;
"做得不错""谢谢了"这类闲聊不开,避免误建空项目。
"""
from __future__ import annotations

import re

# 去标点/空白后的实质字符(中文/字母/数字)达到该数,才算实质新需求。
# 取 5:挡掉"做得不错"(4)/"谢谢了"(3)等闲聊,放行"加个颜色筛选"(6)。
_MIN_SUBSTANTIVE = 5

_NON_WORD_RE = re.compile(r"\W", re.UNICODE)  # 去标点/空白,保留中文/字母/数字


def is_substantive_request(text: str) -> bool:
    """这条消息是否像一个实质的新需求(而非闲聊/感叹)。"""
    residual = _NON_WORD_RE.sub("", (text or "").strip())
    return len(residual) >= _MIN_SUBSTANTIVE
