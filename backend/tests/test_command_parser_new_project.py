"""卡点 B 回归:`#新需求` 格式不全不再静默降级成 chat。

用 importlib 直接加载 command_parser.py(纯标准库,无 app 依赖),绕过
app.gateway.__init__(会 import wechat_gateway → 触发 anthropic)。
"""
import importlib.util
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "app" / "gateway" / "command_parser.py"
_spec = importlib.util.spec_from_file_location("command_parser_under_test", _PATH)
_mod = importlib.util.module_from_spec(_spec)
# @dataclass(slots=True) 重建类时要从 sys.modules 取模块,手动加载需先注册。
sys.modules["command_parser_under_test"] = _mod
_spec.loader.exec_module(_mod)
parse_command = _mod.parse_command


def test_new_project_full_ok():
    cmd = parse_command("#新需求 oaSys 加个登录")
    assert cmd.type == "new_project"
    assert cmd.args == {"repo": "oaSys", "desc": "加个登录"}


def test_new_alias_ok():
    cmd = parse_command("#new oaSys add login here")
    assert cmd.type == "new_project"
    assert cmd.args["repo"] == "oaSys"
    assert cmd.args["desc"] == "add login here"


def test_missing_repo_or_desc_no_longer_downgrades_to_chat():
    # 缺仓库名/需求,统一返回 new_project 交 handler 友好提示,不再降级 chat 撞状态拦截
    for text in ["#新需求", "#新需求 装备加规格", "#新需求 oaSys", "#new"]:
        cmd = parse_command(text)
        assert cmd.type == "new_project", f"{text!r} 不应降级成 {cmd.type}"


def test_non_command_still_chat():
    # 非 # 开头仍是 chat,不受影响
    assert parse_command("随便聊聊").type == "chat"
