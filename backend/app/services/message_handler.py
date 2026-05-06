from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import PMAgent
from app.gateway.command_parser import Command
from app.gateway.wechat_client import WeChatClient
from app.models import Feedback, Project, Repo, Session as UserSession, User, UserRepo
from app.services.project_service import ProjectService
from app.services.session_manager import SessionManager
from shared.constants import ProjectStatus, SessionState

logger = logging.getLogger(__name__)


class MessageHandler:
    def __init__(self, db: AsyncSession, wechat: WeChatClient) -> None:
        self.db = db
        self.wechat = wechat
        self.session_manager = SessionManager(db)
        self.project_service = ProjectService(db)
        self.pm_agent = PMAgent()

    async def handle(self, wechat_user_id: str, command: Command) -> str:
        reply = "抱歉，当前处理消息时出现异常，请稍后再试。"
        try:
            user = await self.session_manager.get_or_create_user(wechat_user_id)
            session = await self.session_manager.get_session(user)

            match command.type:
                case "new_project":
                    reply = await self._handle_new_project(user, session, wechat_user_id, command)
                case "chat":
                    reply = await self._handle_chat(user, session, wechat_user_id, command)
                case "confirm":
                    reply = await self._handle_confirm(user, session, wechat_user_id)
                case "modify":
                    reply = await self._handle_modify(user, session, wechat_user_id, command)
                case "score":
                    reply = await self._handle_score(user, session, wechat_user_id, command)
                case "status":
                    reply = await self._handle_status(user, session)
                case "list":
                    reply = await self._handle_list(user, session)
                case "my_repos":
                    reply = await self._handle_my_repos(user)
                case "help":
                    reply = self._handle_help()
                case _:
                    reply = self._handle_help()

            await self.db.commit()
        except Exception:
            logger.exception("Failed to handle message for wechat_user_id=%s", wechat_user_id)
            await self.db.rollback()

        try:
            await self.wechat.send_text(wechat_user_id, reply)
        except Exception:
            logger.exception(
                "Failed to send WeChat reply for wechat_user_id=%s (DB state already persisted)",
                wechat_user_id,
            )

        return reply

    async def _handle_new_project(
        self,
        user: User,
        session: UserSession,
        wechat_user_id: str,
        command: Command,
    ) -> str:
        repo_name = str(command.args.get("repo", "")).strip()
        desc = str(command.args.get("desc", "")).strip()
        if not repo_name or not desc:
            return "新需求指令格式不正确，请使用：#新需求 <仓库> <需求描述>"

        repo = await self.project_service.get_repo_by_name(repo_name)
        if repo is None:
            return f"未找到仓库「{repo_name}」，请检查仓库别名后重试。"

        if not await self._user_can_access_repo(user, repo.id):
            return (
                f"你还没有「{repo_name}」的提需求权限，请联系管理员开通后再试。\n"
                "可发送 #我的仓库 查看你当前能提需求的仓库。"
            )

        project = await self.project_service.create_project(
            repo_id=repo.id,
            title=self._build_project_title(desc),
            creator_id=user.id,
        )
        await self.session_manager.update_session_state(
            session,
            SessionState.CHATTING,
            project.id,
        )
        await self.project_service.add_message(project.id, wechat_user_id, "user", desc)

        ai_reply = await self.pm_agent.chat(project, repo, [], desc)
        await self.project_service.add_message(project.id, wechat_user_id, "assistant", ai_reply)

        return (
            f"已在仓库「{repo.name}」下创建需求会话：[{project.id}] {project.title}\n\n"
            f"{ai_reply}\n\n"
            "需求沟通完成后发送 #确认 生成 PRD。"
        )

    async def _handle_chat(
        self,
        user: User,
        session: UserSession,
        wechat_user_id: str,
        command: Command,
    ) -> str:
        del user

        user_message = str(command.args.get("content", "")).strip()
        if not user_message:
            return "请输入要补充的需求内容。"

        project, repo, error_reply = await self._get_active_project_context(session)
        if error_reply is not None or project is None or repo is None:
            return error_reply or "当前没有可继续沟通的项目，请先发送 #新需求。"

        if project.status == ProjectStatus.REVIEWING.value or session.state == SessionState.CONFIRMING.value:
            return "当前 PRD 已生成，如需调整请发送 #修改 <内容>。"

        if session.state == SessionState.SCORING.value:
            return "当前项目正在等待评分，请发送 #评分 <1-10> <反馈>。"

        if project.status != ProjectStatus.DRAFTING.value:
            return f"当前项目状态为「{self._status_label(project.status)}」，不在需求沟通阶段，请发送 #状态 查看进度。"

        history = await self.project_service.get_messages(project.id)
        await self.project_service.add_message(project.id, wechat_user_id, "user", user_message)
        await self.session_manager.update_session_state(session, SessionState.CHATTING, project.id)

        ai_reply = await self.pm_agent.chat(project, repo, history, user_message)
        await self.project_service.add_message(project.id, wechat_user_id, "assistant", ai_reply)
        return ai_reply

    async def _handle_confirm(
        self,
        user: User,
        session: UserSession,
        wechat_user_id: str,
    ) -> str:
        del user

        project, repo, error_reply = await self._get_active_project_context(session)
        if error_reply is not None or project is None or repo is None:
            return error_reply or "当前没有可确认的项目，请先发送 #新需求。"

        if project.status == ProjectStatus.COMPLETED.value:
            return "当前项目已经完成，如需新需求请发送 #新需求。"

        if project.prd_content and project.status == ProjectStatus.REVIEWING.value:
            return (
                "当前项目的 PRD 已生成，状态为待审核。\n\n"
                f"{project.prd_content}\n\n"
                "如需调整，请发送 #修改 <内容>。"
            )

        if project.status != ProjectStatus.DRAFTING.value:
            return f"当前项目状态为「{self._status_label(project.status)}」，无法再次生成 PRD。"

        history = await self.project_service.get_messages(project.id)
        prd = await self.pm_agent.generate_prd(project, repo, history)
        await self.project_service.save_prd(project, prd)
        await self.project_service.update_status(project, ProjectStatus.REVIEWING)
        await self.session_manager.update_session_state(
            session,
            SessionState.CONFIRMING,
            project.id,
        )
        await self.project_service.add_message(
            project.id,
            wechat_user_id,
            "assistant",
            "PRD 已生成，项目状态已更新为 reviewing。",
        )

        return (
            "已根据当前对话生成 PRD，项目状态已更新为待审核。\n\n"
            f"{prd}\n\n"
            "如需调整，请发送 #修改 <内容>。"
        )

    async def _handle_modify(
        self,
        user: User,
        session: UserSession,
        wechat_user_id: str,
        command: Command,
    ) -> str:
        del user

        feedback = str(command.args.get("content", "")).strip()
        if not feedback:
            return "请在 #修改 后补充需要调整的内容。"

        project, repo, error_reply = await self._get_active_project_context(session)
        if error_reply is not None or project is None or repo is None:
            return error_reply or "当前没有可修改的项目，请先发送 #新需求。"

        if not project.prd_content:
            return "当前项目还没有生成 PRD，请先继续沟通并发送 #确认。"

        if project.status == ProjectStatus.COMPLETED.value:
            return "当前项目已经完成，不能再修改 PRD。"

        if project.status not in {ProjectStatus.REVIEWING.value, ProjectStatus.REJECTED.value}:
            return f"当前项目状态为「{self._status_label(project.status)}」，暂时不能修改 PRD。"

        history = await self.project_service.get_messages(project.id)
        await self.project_service.add_message(project.id, wechat_user_id, "user", feedback)

        updated_prd = await self.pm_agent.modify_prd(
            project,
            repo,
            history,
            project.prd_content,
            feedback,
        )
        await self.project_service.save_prd(project, updated_prd)
        await self.project_service.update_status(project, ProjectStatus.REVIEWING)
        await self.session_manager.update_session_state(
            session,
            SessionState.CONFIRMING,
            project.id,
        )
        await self.project_service.add_message(
            project.id,
            wechat_user_id,
            "assistant",
            "PRD 已根据最新反馈完成更新。",
        )

        return f"已根据你的反馈更新 PRD：\n\n{updated_prd}"

    async def _handle_score(
        self,
        user: User,
        session: UserSession,
        wechat_user_id: str,
        command: Command,
    ) -> str:
        score = int(command.args.get("score", 0))
        comment = str(command.args.get("comment", "")).strip()
        if not comment:
            return "评分时请同时附带文字反馈，例如：#评分 8 功能基本符合预期"

        project, _, error_reply = await self._get_active_project_context(session)
        if error_reply is not None or project is None:
            return error_reply or "当前没有可评分的项目，请先发送 #状态 或 #列表 查看项目。"

        if project.status in {ProjectStatus.DRAFTING.value, ProjectStatus.REVIEWING.value}:
            return "当前项目还处在需求阶段，暂时不能评分。请等待开发和验收流程完成后再评分。"

        project.score = float(score)
        project.feedback = comment
        self.db.add(
            Feedback(
                project_id=project.id,
                user_id=user.id,
                score=float(score),
                comment=comment,
            )
        )
        await self.project_service.add_message(
            project.id,
            wechat_user_id,
            "user",
            f"#评分 {score} {comment}",
        )
        await self.project_service.update_status(project, ProjectStatus.COMPLETED)
        await self.session_manager.update_session_state(session, SessionState.IDLE, project.id)
        await self.db.flush()

        return f"已记录评分：{score} 分。\n反馈：{comment}\n当前项目已标记为完成。"

    async def _handle_status(self, user: User, session: UserSession) -> str:
        del user

        project, repo, error_reply = await self._get_active_project_context(session)
        if error_reply is not None or project is None:
            return error_reply or "当前没有激活项目，请先发送 #新需求。"

        repo_name = repo.name if repo is not None else f"repo#{project.repo_id}"
        lines = [
            f"当前项目：[{project.id}] {project.title}",
            f"仓库：{repo_name}",
            f"状态：{self._status_label(project.status)}",
        ]

        if project.prd_content:
            lines.append("PRD：已生成")
        if project.github_issue_number is not None:
            lines.append(f"GitHub Issue：#{project.github_issue_number}")
        if project.github_pr_number is not None:
            lines.append(f"GitHub PR：#{project.github_pr_number}")
        if project.score is not None:
            lines.append(f"评分：{project.score:g}")
        if project.feedback:
            lines.append(f"反馈：{project.feedback}")

        if project.status == ProjectStatus.DRAFTING.value:
            lines.append("继续补充需求可直接发送消息，确认后发送 #确认。")
        elif project.status == ProjectStatus.REVIEWING.value:
            lines.append("如需调整 PRD，请发送 #修改 <内容>。")

        return "\n".join(lines)

    async def _handle_list(self, user: User, session: UserSession) -> str:
        projects = await self.project_service.get_user_projects(user.id)
        if not projects:
            return "你还没有创建过项目，发送 #新需求 <仓库> <需求描述> 开始第一条需求。"

        lines = ["你的项目列表："]
        for index, project in enumerate(projects[:10], start=1):
            repo = await self.project_service.get_repo_by_name_or_id(project.repo_id)
            repo_name = repo.name if repo is not None else f"repo#{project.repo_id}"
            lines.append(
                f"{index}. [{project.id}] {project.title} | {repo_name} | {self._status_label(project.status)}"
            )

        if len(projects) > 10:
            lines.append(f"仅展示最近 10 个项目，共 {len(projects)} 个。")
        if session.active_project_id is not None:
            lines.append(f"当前激活项目 ID：{session.active_project_id}")

        return "\n".join(lines)

    def _handle_help(self) -> str:
        return (
            "可用指令：\n"
            "#新需求 <仓库> <需求描述>\n"
            "#确认\n"
            "#修改 <修改意见>\n"
            "#评分 <1-10> <反馈>\n"
            "#状态\n"
            "#列表\n"
            "#我的仓库\n"
            "#帮助\n\n"
            "不带 # 的普通文本会继续发送给 PM AI。"
        )

    async def _handle_my_repos(self, user: User) -> str:
        if user.role == "admin":
            repos = (
                await self.db.execute(select(Repo).order_by(Repo.name))
            ).scalars().all()
            if not repos:
                return "系统当前没有配置任何仓库。"
            lines = [f"你是管理员，可以给所有仓库提需求（共 {len(repos)} 个）："]
            for r in repos:
                lines.append(f"• {r.name}（{r.github_owner}/{r.github_repo}）")
            lines.append("")
            lines.append("提需求格式：#新需求 <仓库别名> <需求描述>")
            return "\n".join(lines)

        stmt = (
            select(Repo)
            .join(UserRepo, UserRepo.repo_id == Repo.id)
            .where(UserRepo.user_id == user.id)
            .order_by(Repo.name)
        )
        repos = (await self.db.execute(stmt)).scalars().all()
        if not repos:
            return "你目前没有任何仓库的提需求权限，请联系管理员开通。"
        lines = [f"你可以给以下 {len(repos)} 个仓库提需求："]
        for r in repos:
            lines.append(f"• {r.name}（{r.github_owner}/{r.github_repo}）")
        lines.append("")
        lines.append("提需求格式：#新需求 <仓库别名> <需求描述>")
        return "\n".join(lines)

    async def _user_can_access_repo(self, user: User, repo_id: int) -> bool:
        if user.role == "admin":
            return True
        stmt = select(UserRepo).where(
            UserRepo.user_id == user.id,
            UserRepo.repo_id == repo_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def _get_active_project_context(
        self,
        session: UserSession,
    ) -> tuple[Project | None, Repo | None, str | None]:
        if session.active_project_id is None:
            return None, None, "当前没有激活项目，请先发送 #新需求 <仓库> <需求描述>。"

        project = await self.project_service.get_project(session.active_project_id)
        if project is None:
            await self.session_manager.update_session_state(session, SessionState.IDLE, None)
            return None, None, "当前会话关联的项目不存在，已重置会话，请重新发送 #新需求。"

        repo = await self.project_service.get_repo_by_name_or_id(project.repo_id)
        if repo is None:
            return None, None, "当前项目关联的仓库不存在，请联系管理员检查仓库配置。"

        return project, repo, None

    @staticmethod
    def _build_project_title(desc: str) -> str:
        normalized_desc = " ".join(desc.split())
        if len(normalized_desc) <= 40:
            return normalized_desc
        return f"{normalized_desc[:40].rstrip()}..."

    @staticmethod
    def _status_label(status: str) -> str:
        labels = {
            ProjectStatus.DRAFTING.value: "需求沟通中",
            ProjectStatus.REVIEWING.value: "PRD 待审核",
            ProjectStatus.APPROVED.value: "已批准",
            ProjectStatus.DEVELOPING.value: "开发中",
            ProjectStatus.DEPLOYED.value: "已部署",
            ProjectStatus.ACCEPTANCE.value: "待验收",
            ProjectStatus.COMPLETED.value: "已完成",
            ProjectStatus.REJECTED.value: "已驳回",
        }
        return labels.get(status, status)
