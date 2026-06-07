"""全角输入法兼容:＃→#、全角空格 → 半角(importlib 加载,绕过 app.gateway.__init__)。"""
import importlib.util
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "app" / "gateway" / "command_parser.py"
_spec = importlib.util.spec_from_file_location("command_parser_fw_ut", _PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["command_parser_fw_ut"] = _mod  # dataclass(slots=True) 需要
_spec.loader.exec_module(_mod)
parse_command = _mod.parse_command


def test_fullwidth_hash():
    cmd = parse_command("＃补充 14 内容")
    assert cmd.type == "supplement"
    assert cmd.args == {"project_id": 14, "content": "内容"}


def test_fullwidth_space():
    cmd = parse_command("#补充　14 内容")
    assert cmd.type == "supplement"
    assert cmd.args == {"project_id": 14, "content": "内容"}


def test_fullwidth_hash_and_space():
    cmd = parse_command("＃改需求　13　增加权限矩阵")
    assert cmd.type == "revise_prd"
    assert cmd.args["project_id"] == 13
    assert cmd.args["content"] == "增加权限矩阵"


def test_fullwidth_simple_command():
    cmd = parse_command("＃列表")
    assert cmd.type == "list"


def test_halfwidth_still_works():
    cmd = parse_command("#打回 13 头盔没说清")
    assert cmd.type == "send_back"
    assert cmd.args == {"project_id": 13, "content": "头盔没说清"}
