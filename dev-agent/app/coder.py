from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from app.llm import LLMClient
from app.repo_analyzer import RepoAnalyzer


@dataclass(slots=True)
class FileChange:
    path: str
    action: str
    content: str = ""


@dataclass(slots=True)
class DevelopResult:
    plan: list[str]
    files: list[FileChange]
    commit_message: str


class Coder:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or LLMClient()

    async def develop(self, issue_body: str, repo_path: str) -> DevelopResult:
        analyzer = RepoAnalyzer(repo_path)
        structure = analyzer.get_structure()
        key_files = analyzer.get_key_files()
        key_files_text = self._format_key_files(key_files)

        system_prompt = (
            "You are a senior software engineer modifying an existing repository. "
            "Return JSON only, without markdown or extra explanation. "
            'The JSON schema is {"plan": ["step"], "files": [{"path": "relative/path", '
            '"action": "create|update|delete|write", "content": "full file content"}], '
            '"commit_message": "feat: ..."} . '
            "Use repository-relative paths only. For delete actions omit content or set it to an empty string."
        )
        user_prompt = (
            f"Issue body:\n{issue_body or '(empty)'}\n\n"
            f"Repository structure:\n{structure}\n\n"
            f"Key files:\n{key_files_text}\n\n"
            "Generate the minimal set of file changes needed to implement the issue."
        )

        raw_response = await self.llm_client.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        payload = self._parse_json_response(raw_response)
        return DevelopResult(
            plan=self._normalize_plan(payload.get("plan")),
            files=self._normalize_files(payload.get("files", [])),
            commit_message=str(payload.get("commit_message") or "feat: implement requested changes"),
        )

    def apply_changes(self, repo_path: str | Path, changes: Sequence[FileChange | dict[str, Any]]) -> None:
        repo_root = Path(repo_path).resolve()
        for item in changes:
            change = item if isinstance(item, FileChange) else FileChange(**item)
            target = (repo_root / change.path).resolve()
            try:
                target.relative_to(repo_root)
            except ValueError as exc:
                raise ValueError(f"Refusing to write outside repository: {change.path}") from exc

            action = change.action.lower()
            if action == "delete":
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink(missing_ok=True)
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(change.content, encoding="utf-8")

    @staticmethod
    def _format_key_files(key_files: dict[str, str]) -> str:
        if not key_files:
            return "(no key files found)"

        sections = []
        for path, content in key_files.items():
            sections.append(f"## {path}\n```text\n{content}\n```")
        return "\n\n".join(sections)

    @staticmethod
    def _normalize_plan(plan: Any) -> list[str]:
        if isinstance(plan, list):
            return [str(step) for step in plan]
        if isinstance(plan, str) and plan.strip():
            return [plan.strip()]
        return []

    @staticmethod
    def _normalize_files(files: Any) -> list[FileChange]:
        normalized: list[FileChange] = []
        if not isinstance(files, list):
            return normalized

        for item in files:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "").strip()
            if not path:
                continue
            action = str(item.get("action") or "write").strip().lower()
            content = item.get("content")
            normalized.append(
                FileChange(
                    path=path,
                    action=action,
                    content="" if content is None else str(content),
                )
            )
        return normalized

    def _parse_json_response(self, response_text: str) -> dict[str, Any]:
        candidates = [response_text.strip()]

        fenced_blocks = re.findall(r"```(?:json)?\s*(.*?)```", response_text, flags=re.DOTALL | re.IGNORECASE)
        candidates.extend(block.strip() for block in fenced_blocks if block.strip())

        decoder = json.JSONDecoder()
        for candidate in candidates:
            if not candidate:
                continue
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

            for index, char in enumerate(candidate):
                if char != "{":
                    continue
                try:
                    payload, _ = decoder.raw_decode(candidate[index:])
                    if isinstance(payload, dict):
                        return payload
                except json.JSONDecodeError:
                    continue

        raise ValueError("LLM response did not contain valid JSON")
