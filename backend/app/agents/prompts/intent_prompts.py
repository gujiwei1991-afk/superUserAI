"""Prompts for group-bound natural language intent classification."""

CONFIRM_VERIFY_PROMPT = """你是用于核对用户是否同意进入开发的 AI 守门员。

下面是某项目的需求摘要 / 当前 PRD 草稿：
{summary}

最近 5 条对话：
{history}

用户刚刚发的消息：
"{content}"

请回答：用户是否在明确同意进入"开发审核"阶段？
- 答 yes 当且仅当用户的"同意"是确定的、无保留的（如"确认"、"开发吧"、"可以了"）
- 答 no 当用户表达不确定、提问、或讨论中（如"我觉得可以"、"应该差不多吧"、"这样确认下"、"确认一下没问题再说"）

只输出一个词：yes 或 no。
"""


def render_confirm_verify_prompt(
    summary: str,
    history_lines: list[str],
    content: str,
) -> str:
    safe_summary = (summary or "(无)").strip() or "(无)"
    safe_history = "\n".join(history_lines[-5:]) if history_lines else "(无)"
    return CONFIRM_VERIFY_PROMPT.format(
        summary=safe_summary,
        history=safe_history,
        content=content.strip(),
    )
