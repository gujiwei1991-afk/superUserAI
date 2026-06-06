"""管理员定向命令解析(importlib 加载,绕过 app.gateway.__init__)。"""
import importlib.util
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "app" / "gateway" / "command_parser.py"
_spec = importlib.util.spec_from_file_location("command_parser_admin_ut", _PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["command_parser_admin_ut"] = _mod  # dataclass(slots=True) 需要
_spec.loader.exec_module(_mod)
parse_command = _mod.parse_command


def test_supplement_full():
    cmd = parse_command("#补充 12 送餐箱要支持三种规格")
    assert cmd.type == "supplement"
    assert cmd.args == {"project_id": 12, "content": "送餐箱要支持三种规格"}


def test_revise_full():
    cmd = parse_command("#改需求 12 增加权限矩阵")
    assert cmd.type == "revise_prd"
    assert cmd.args == {"project_id": 12, "content": "增加权限矩阵"}


def test_sendback_full():
    cmd = parse_command("#打回 12 头盔规格没说清")
    assert cmd.type == "send_back"
    assert cmd.args == {"project_id": 12, "content": "头盔规格没说清"}


def test_supplement_hash_id():
    cmd = parse_command("#补充 #12 内容")
    assert cmd.args["project_id"] == 12
    assert cmd.args["content"] == "内容"


def test_supplement_missing_content():
    cmd = parse_command("#补充 12")
    assert cmd.type == "supplement"
    assert cmd.args == {"project_id": 12, "content": ""}


def test_supplement_missing_id():
    cmd = parse_command("#补充")
    assert cmd.type == "supplement"
    assert cmd.args == {"project_id": None, "content": ""}


def test_revise_nonnumeric_id():
    cmd = parse_command("#改需求 abc 内容")
    assert cmd.args["project_id"] is None
    assert cmd.args["content"] == "内容"
