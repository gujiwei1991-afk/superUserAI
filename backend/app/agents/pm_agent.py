from __future__ import annotations

from collections.abc import Sequence

from app.agents.prompts.pm_prompts import PRD_GENERATION_PROMPT, SYSTEM_PROMPT
from app.llm import BaseLLM, create_llm
from app.models import Message, Project, Repo


READY_MARKER = "[READY_TO_CONFIRM]"


def has_ready_marker(text: str) -> bool:
    return READY_MARKER in (text or "")


def strip_ready_marker(text: str) -> str:
    if not text:
        return text
    return text.replace(READY_MARKER, "").rstrip()


class PMAgent:
    def __init__(self, llm: BaseLLM | None = None) -> None:
        self.llm = llm or create_llm()

    async def chat(
        self,
        project: Project,
        repo: Repo,
        history: Sequence[Message],
        user_message: str,
    ) -> str:
        messages = self._build_messages(project, repo, history)
        messages.append({"role": "user", "content": user_message})
        response = await self.llm.chat(messages)
        return response.content.strip() or "我已经记录这条需求，请再补充一些关键细节。"

    async def generate_prd(
        self,
        project: Project,
        repo: Repo,
        history: Sequence[Message],
    ) -> str:
        messages = self._build_messages(project, repo, history)
        messages.append(
            {
                "role": "user",
                "content": PRD_GENERATION_PROMPT.format(
                    project_title=project.title,
                    repo_name=repo.name,
                ),
            }
        )
        response = await self.llm.chat(messages)
        return response.content.strip() or "PRD 生成失败，请稍后重试。"

    async def modify_prd(
        self,
        project: Project,
        repo: Repo,
        history: Sequence[Message],
        current_prd: str,
        feedback: str,
    ) -> str:
        messages = self._build_messages(project, repo, history)
        messages.append(
            {
                "role": "user",
                "content": (
                    "请根据以下用户反馈修改现有 PRD，并返回更新后的完整 Markdown 文档。\n\n"
                    f"项目标题：{project.title}\n"
                    f"目标仓库：{repo.name}\n\n"
                    f"当前 PRD：\n{current_prd}\n\n"
                    f"用户反馈：\n{feedback}\n\n"
                    "要求：保留已有合理内容，只修改必要部分；若信息仍不足，请在文档中明确标注待确认项。"
                ),
            }
        )
        response = await self.llm.chat(messages)
        return response.content.strip() or current_prd

    def _build_messages(
        self,
        project: Project,
        repo: Repo,
        history: Sequence[Message],
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(
                    project_title=project.title,
                    repo_name=repo.name,
                ),
            }
        ]
        for item in history:
            messages.append(
                {
                    "role": self._normalize_role(item.role),
                    "content": item.content,
                }
            )
        return messages

    @staticmethod
    def _normalize_role(role: str) -> str:
        normalized_role = role.strip().lower()
        if normalized_role in {"assistant", "system"}:
            return normalized_role
        return "user"

    def build_confirm_hint(self) -> str:
        return (
            "\n\n如果上面理解没问题，请回复『确认』，我就把它提交审核。\n"
            "如果还要调整，直接告诉我哪里要改即可。"
        )
