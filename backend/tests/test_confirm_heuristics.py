"""确认判定护栏单测。confirm_heuristics 无第三方依赖,本地/CI 直接可跑。

严格取向:只有"消息主体就是确认"才算确认候选;长需求文本里夹带
"确认"等子串(如"装备确认中…")一律不算,避免误判 confirm→提前生成 PRD。

用 importlib 直接从文件加载,绕过 app.services.__init__(它会 import
message_handler → 触发 anthropic 依赖,本机未装)。
"""
import importlib.util
from pathlib import Path

_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app" / "services" / "confirm_heuristics.py"
)
_spec = importlib.util.spec_from_file_location("confirm_heuristics", _MODULE_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
is_confirmation_subject = _mod.is_confirmation_subject


# —— 主体就是确认:应为 True ——
def test_bare_confirm():
    assert is_confirmation_subject("确认") is True


def test_confirm_with_short_tail():
    assert is_confirmation_subject("确认，开发吧") is True
    assert is_confirmation_subject("可以了") is True
    assert is_confirmation_subject("没问题就这样") is True
    assert is_confirmation_subject("好，确认") is True


# —— 长需求文本夹带确认词:应为 False(核心回归用例) ——
def test_requirement_text_with_confirm_substring_is_not_confirm():
    text = (
        "装备确认中，增加一列“规格”。只需要3个规格，其中头盔规格为："
        "夏季、冬季；送餐箱规格为：30L、45L、62L；衣服型号为：L、XL、2XL"
    )
    assert is_confirmation_subject(text) is False


def test_requirement_without_confirm_word_is_not_confirm():
    # 不含任何确认词,本就不该进确认候选
    assert is_confirmation_subject("增加一列规格，头盔分夏季冬季") is False


def test_empty_or_blank():
    assert is_confirmation_subject("") is False
    assert is_confirmation_subject("   ") is False
