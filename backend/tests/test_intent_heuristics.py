"""卡点 A 护栏单测:已完成项目下,够实质的消息才当"新需求"自动开新一轮,
挡掉"做得不错""谢谢了"这类闲聊,避免误开空项目。

intent_heuristics 无第三方依赖,importlib 直接加载(绕过 app.services.__init__)。
"""
import importlib.util
from pathlib import Path

_PATH = (
    Path(__file__).resolve().parents[1] / "app" / "services" / "intent_heuristics.py"
)
_spec = importlib.util.spec_from_file_location("intent_heuristics", _PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
is_substantive_request = _mod.is_substantive_request


def test_substantive_requests_true():
    assert is_substantive_request("加个颜色筛选") is True
    assert is_substantive_request("再加个搜索框") is True
    assert is_substantive_request("增加一列规格，头盔分夏季冬季") is True


def test_chitchat_false():
    assert is_substantive_request("做得不错") is False
    assert is_substantive_request("谢谢了") is False
    assert is_substantive_request("挺好的") is False


def test_empty_or_punct_false():
    assert is_substantive_request("") is False
    assert is_substantive_request("  ，。！ ") is False
