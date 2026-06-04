"""Prompts for group-bound natural language intent classification."""

CONFIRM_VERIFY_PROMPT = """你是用于核对用户是否同意进入开发的 AI 守门员。

下面是某项目的需求摘要 / 当前 PRD 草稿：
{summary}

最近 5 条对话：
{history}

用户刚刚发的消息：
"{content}"

请回答：用户是否在向系统表达「我同意提交审核」？

判定规则（**严格版** —— 答 yes 会立刻拿当前对话生成 PRD、推进开发，宁可漏判也不要错判）：

- **答 yes**：整条消息的主体就是"拍板同意提交"，几乎不含别的实质内容
  - 示例 yes：「确认」「确认，开发吧」「可以了，就这样」「好，可以开始了」「没问题，提交吧」
- **答 no**（拿不准就答 no）：只要消息里还带着实质的需求内容、补充、提问或犹豫，即使夹带"确认"字样，也一律 no
  - "确认中""待确认""确认一下""再确认下"是**业务状态或请求**，不是拍板，一律 no
  - 消息在**描述或补充需求**（列字段、规格、数据、步骤）时，即便含"确认"也答 no
  - 示例 no：「装备确认中，增加一列规格。头盔：夏季、冬季；送餐箱：30L、45L、62L」「再确认下，是不是 xxx？」「这个还要确认下」「我去问一下产品再来确认」「确认啥？」「嗯」

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
