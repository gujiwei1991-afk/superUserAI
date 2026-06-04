"""回归保护:确认核对 prompt 必须是"严格版"(纯文件读取,不 import app)。

严格取向:confirm 会立刻生成 PRD、推进开发,prompt 必须明确"长需求文本
夹带确认词不算确认",并删除原"宽容版"里"补充少量细节也算 yes"的规则。
"""
from pathlib import Path

PROMPT_FILE = (
    Path(__file__).resolve().parents[1]
    / "app" / "agents" / "prompts" / "intent_prompts.py"
)


def test_confirm_verify_prompt_is_strict():
    src = PROMPT_FILE.read_text(encoding="utf-8")
    assert "严格版" in src, "确认核对 prompt 仍是宽容版"
    assert "补充少量细节也算" not in src, "宽容规则残留(应删除)"
    # 反例 + "确认中/待确认非确认"规则锚点
    assert "装备确认中" in src, "缺少长需求误判反例"
    assert "待确认" in src or "业务状态" in src, "缺少'确认中/待确认非拍板'规则"
