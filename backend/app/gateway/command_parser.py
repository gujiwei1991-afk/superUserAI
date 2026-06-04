from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Command:
    type: str
    args: dict[str, object] = field(default_factory=dict)


def parse_command(content: str) -> Command:
    content = content.strip()
    if not content.startswith("#"):
        return Command(type="chat", args={"content": content})

    name, _, remainder = content.partition(" ")
    remainder = remainder.strip()
    command_name = name.casefold()

    match command_name:
        case "#新需求" | "#new":
            # 始终按"新需求"意图返回,缺仓库名/需求就传空值,交 _handle_new_project
            # 统一校验并给友好提示;不再静默降级成 chat(否则会撞状态拦截、报无关错)。
            repo_and_desc = remainder.split(maxsplit=1)
            repo = repo_and_desc[0] if repo_and_desc else ""
            desc = repo_and_desc[1] if len(repo_and_desc) == 2 else ""
            return Command(type="new_project", args={"repo": repo, "desc": desc})
        case "#确认":
            return Command(type="confirm")
        case "#修改":
            if not remainder:
                return Command(type="chat", args={"content": content})

            return Command(type="modify", args={"content": remainder})
        case "#评分":
            score_and_comment = remainder.split(maxsplit=1)
            if len(score_and_comment) != 2:
                return Command(type="chat", args={"content": content})

            score_text, comment = score_and_comment
            try:
                score = int(score_text)
            except ValueError:
                return Command(type="chat", args={"content": content})

            if score < 1 or score > 10 or not comment:
                return Command(type="chat", args={"content": content})

            return Command(type="score", args={"score": score, "comment": comment})
        case "#审核":
            parts = remainder.split(maxsplit=2)
            if len(parts) < 2:
                return Command(type="chat", args={"content": content})

            raw_id, decision = parts[0], parts[1]
            if not raw_id.isdigit() or decision not in {"通过", "拒绝"}:
                return Command(type="chat", args={"content": content})

            reason = parts[2].strip() if len(parts) == 3 else ""
            return Command(
                type="review",
                args={
                    "project_id": int(raw_id),
                    "decision": decision,
                    "reason": reason,
                },
            )
        case "#状态":
            return Command(type="status")
        case "#列表":
            return Command(type="list")
        case "#切换" | "#switch":
            raw = remainder.strip().lstrip("#").strip()
            pid = int(raw) if raw.isdigit() else None
            return Command(type="switch", args={"project_id": pid})
        case "#我的仓库" | "#repos":
            return Command(type="my_repos")
        case "#帮助" | "#help":
            return Command(type="help")
        case _:
            return Command(type="chat", args={"content": content})
