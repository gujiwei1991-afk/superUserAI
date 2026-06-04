"""回归保护：SYSTEM_PROMPT 必须包含'治标→治本'升级雷达的关键锚点。
纯文件读取，不 import app(避免触发 anthropic 依赖),本地/CI 均可跑。
效果(模型是否真的升级需求)靠真机对话评估,不在此断言。
"""
from pathlib import Path

PROMPT_FILE = (
    Path(__file__).resolve().parents[1]
    / "app" / "agents" / "prompts" / "pm_prompts.py"
)


def test_system_prompt_contains_upgrade_radar():
    src = PROMPT_FILE.read_text(encoding="utf-8")
    # 雷达存在性锚点
    assert "治标" in src and "治本" in src, "缺少治标→治本升级雷达小节"
    assert "可配置" in src, "缺少'可配置'升级方向(下拉框写死场景)"
    # 克制规则锚点(防止整段被删后只剩清单、丢了克制)
    assert "最多提一次" in src, "缺少'最多提一次'克制规则"
    assert "别硬塞" in src, "缺少'简单需求别硬塞'克制规则"
