"""#关闭 <项目ID> 命令解析(importlib 加载,绕过 app.gateway.__init__)。"""
import importlib.util
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "app" / "gateway" / "command_parser.py"
_spec = importlib.util.spec_from_file_location("command_parser_close_ut", _PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["command_parser_close_ut"] = _mod  # dataclass(slots=True) 需要
_spec.loader.exec_module(_mod)
parse_command = _mod.parse_command


def test_close_with_id():
    cmd = parse_command("#关闭 12")
    assert cmd.type == "close_project"
    assert cmd.args == {"project_id": 12}


def test_close_with_hash_id():
    cmd = parse_command("#关闭 #12")
    assert cmd.type == "close_project"
    assert cmd.args["project_id"] == 12


def test_close_missing_id():
    cmd = parse_command("#关闭")
    assert cmd.type == "close_project"
    assert cmd.args["project_id"] is None


def test_close_nonnumeric():
    cmd = parse_command("#关闭 abc")
    assert cmd.type == "close_project"
    assert cmd.args["project_id"] is None
