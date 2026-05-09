"""Prompts for group-bound natural language intent classification."""

CONFIRM_VERIFY_PROMPT = """你是用于核对用户是否同意进入开发的 AI 守门员。

下面是某项目的需求摘要 / 当前 PRD 草稿：
{summary}

最近 5 条对话：
{history}

用户刚刚发的消息：
"{content}"

请回答：用户是否在向系统表达「我同意提交审核」？

判定规则（**宽容版** —— 中文用户经常把补充信息和确认放在同一条消息里）：

- **答 yes**：消息里出现明确的同意词（"确认"、"同意"、"通过"、"开发吧"、"可以了"、"没问题就这样"、"做吧"、"好的就这样"），且整体语气是同意——即使消息前半段还在补充少量细节也算 yes
  - 示例 yes：「确认」「确认，开发吧」「1. xxx 2. yyy 确认」「ok 没问题，就这样吧」「好，可以开始了」
- **答 no**：用户在提问、犹豫、要求修改、或只是日常聊天里恰好出现"确认"二字
  - 示例 no：「再确认下，是不是 xxx？」「我去问一下产品再来确认」「这个还要确认下」「确认啥？」「嗯」（仅一个字、无明确动词）

只输出一个词：yes 或 no。**不要输出任何解释或标点**。
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
