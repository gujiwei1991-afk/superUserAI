from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import PMAgent
from app.agents.pm_agent import has_ready_marker, strip_ready_marker
from app.gateway.command_parser import Command
from app.gateway.wechat_client import WeChatClient
from app.models import Feedback, Project, Repo, Session as UserSession, User, UserRepo
from app.services.project_review import (
    create_issue_for_project,
    notify_creator_approved,
    notify_creator_rejected,
    notify_creator_targeted,
)
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

    async def handle(
        self,
        wechat_user_id: str,
        command: Command,
        group_id: str | None = None,
        send: bool = True,
    ) -> str:
        reply = "抱歉，当前处理消息时出现异常，请稍后再试。"
        user: User | None = None
        try:
            user = await self.session_manager.get_or_create_user(wechat_user_id)

            if user.role != "admin" and not user.is_active:
                logger.info(
                    "Whitelist gate: dropping message from inactive user wechat_user_id=%s",
                    wechat_user_id,
                )
                await self.db.commit()
                return ""

            session = await self.session_manager.get_session(user)

            match command.type:
                case "new_project":
                    reply = await self._handle_new_project(
                        user, session, wechat_user_id, command, group_id=group_id
                    )
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
                case "switch":
                    reply = await self._handle_switch(user, session, command)
                case "close_project":
                    reply = await self._handle_close_project(user, session, command)
                case "supplement":
                    reply = await self._handle_supplement(user, command)
                case "revise_prd":
                    reply = await self._handle_revise_prd(user, command)
                case "send_back":
                    reply = await self._handle_send_back(user, command)
                case "my_repos":
                    reply = await self._handle_my_repos(user)
                case "help":
                    reply = self._handle_help(user)
                case "review":
                    reply = await self._handle_review_command(user, command)
                case _:
                    reply = self._handle_help(user)

            await self.db.commit()
        except Exception:
            logger.exception("Failed to handle message for wechat_user_id=%s", wechat_user_id)
            await self.db.rollback()

        # Strip [READY_TO_CONFIRM] marker (PMAgent in-band signal) before send,
        # appending the standard confirm hint.
        if reply and has_ready_marker(reply):
            cleaned = strip_ready_marker(reply)
            hint = self.pm_agent.build_confirm_hint()
            reply = (cleaned + hint) if cleaned else hint.lstrip()

        if reply and send:
            try:
                if group_id:
                    # @ 提及交给 vworkApi 的 at_list 渲染,msg 内不再手动拼 @昵称
                    # (否则群里会出现 chip + 文本两个 @,即重复 @)。
                    await self.wechat.send_at_group(
                        group_id, [wechat_user_id], reply
                    )
                else:
                    await self.wechat.send_text(wechat_user_id, reply)
            except Exception:
                logger.exception(
                    "Failed to send WeChat reply for wechat_user_id=%s group_id=%s "
                    "(DB state already persisted)",
                    wechat_user_id,
                    group_id,
                )

        return reply

    async def _handle_switch(
        self,
        user: User,
        session: UserSession,
        command: Command,
    ) -> str:
        pid = command.args.get("project_id")
        if pid is None:
            return "用法：#切换 <项目ID>，比如 #切换 12。发 #列表 看你的项目和 ID。"
        project = await self.project_service.get_project(pid)
        if project is None or project.creator_id != user.id:
            return f"没找到属于你的项目 #{pid}。发 #列表 看看你的项目。"
        await self.session_manager.update_session_state(
            session, SessionState.CHATTING, project.id
        )
        return (
            f"已切换到 [{pid}] {project.title}（{self._status_label(project.status)}）。\n"
            "现在可以直接说要改/加什么。"
        )

    async def _handle_close_project(
        self,
        user: User,
        session: UserSession,
        command: Command,
    ) -> str:
        pid = command.args.get("project_id")
        if pid is None:
            return "用法：#关闭 <项目ID>，比如 #关闭 12。发 #列表 看你的项目和 ID。"
        project = await self.project_service.get_project(pid)
        if project is None or (project.creator_id != user.id and user.role != "admin"):
            return f"没找到属于你的项目 #{pid}。发 #列表 看看你的项目。"
        closable = {
            ProjectStatus.DRAFTING.value,
            ProjectStatus.REVIEWING.value,
            ProjectStatus.REJECTED.value,
        }
        if project.status not in closable:
            return (
                f"项目 #{pid} 当前状态为「{self._status_label(project.status)}」，"
                "已进入开发或已结束，不能关闭。"
            )
        await self.project_service.update_status(project, ProjectStatus.CLOSED)
        if session.active_project_id == project.id:
            await self.session_manager.update_session_state(
                session, SessionState.IDLE, None
            )
        return f"已关闭需求 [{pid}] {project.title}，这个需求作废、不再继续。"

    async def _load_admin_target(
        self, user: User, pid: int
    ) -> tuple[Project | None, str]:
        """管理员定向命令公共校验:admin 权限 + 按 ID 取项目。
        返回 (project, error);error 非空表示未过校验,project 为 None。
        pid 缺失(None)由各 handler 自行出定制用法提示,不进此函数。"""
        if user.role != "admin":
            return None, "只有管理员可以使用该命令。"
        project = await self.project_service.get_project(pid)
        if project is None:
            return None, f"找不到项目 #{pid}。"
        return project, ""

    async def _handle_supplement(self, user: User, command: Command) -> str:
        pid = command.args.get("project_id")
        content = str(command.args.get("content", "")).strip()
        if pid is None or not content:
            return "用法：#补充 <项目ID> <补充内容>，比如 #补充 12 送餐箱要支持 30/45/62L 三种规格。"
        project, err = await self._load_admin_target(user, pid)
        if err:
            return err
        if project.status != ProjectStatus.DRAFTING.value:
            return (
                f"项目 #{pid} 当前状态为「{self._status_label(project.status)}」，已过沟通阶段。"
                "要调整方案用 #改需求 <ID> <说明>，要打回重聊用 #打回 <ID> <说明>。"
            )
        await self.project_service.add_message(
            project.id, user.wechat_user_id, "user", f"【管理员补充】{content}"
        )
        await notify_creator_targeted(
            self.db,
            self.wechat,
            project,
            f"管理员补充了一条需求说明：「{content}」。你继续在群里说时，我会带上这条一起理解；"
            f"若已切到别的需求，发 #切换 {pid} 回到这个需求继续。",
        )
        return f"已把补充写入需求 [{pid}] {project.title}，提出人下次沟通时机器人会带上。"

    async def _handle_revise_prd(self, user: User, command: Command) -> str:
        pid = command.args.get("project_id")
        content = str(command.args.get("content", "")).strip()
        if pid is None or not content:
            return "用法：#改需求 <项目ID> <修改说明>，比如 #改需求 12 增加一节『权限矩阵』。"
        project, err = await self._load_admin_target(user, pid)
        if err:
            return err
        if not project.prd_content or project.status != ProjectStatus.REVIEWING.value:
            return (
                f"项目 #{pid} 当前状态为「{self._status_label(project.status)}」，"
                "不在待审核阶段，无法改方案。"
            )
        repo = await self.db.get(Repo, project.repo_id) if project.repo_id else None
        if repo is None:
            return f"项目 #{pid} 没有关联仓库，无法改方案。"
        history = await self.project_service.get_messages(project.id)
        await self.project_service.add_message(
            project.id, user.wechat_user_id, "user", f"【管理员修改要求】{content}"
        )
        updated_prd = await self.pm_agent.modify_prd(
            project, repo, history, project.prd_content, content
        )
        await self.project_service.save_prd(project, updated_prd)
        await self.project_service.update_status(project, ProjectStatus.REVIEWING)
        await self.project_service.add_message(
            project.id, user.wechat_user_id, "assistant", "方案已按管理员要求更新。"
        )
        await self._notify_admins_for_review(project)
        await notify_creator_targeted(
            self.db,
            self.wechat,
            project,
            f"管理员调整了你的需求《{project.title}》的方案，已重新生成、正在重新审核。",
        )
        return f"已按你的说明重写方案并重新送审：\n\n{updated_prd}"

    async def _handle_send_back(self, user: User, command: Command) -> str:
        pid = command.args.get("project_id")
        content = str(command.args.get("content", "")).strip()
        if pid is None or not content:
            return "用法：#打回 <项目ID> <打回说明>，比如 #打回 12 头盔规格还没说清，请补充。"
        project, err = await self._load_admin_target(user, pid)
        if err:
            return err
        if project.status != ProjectStatus.REVIEWING.value:
            return (
                f"项目 #{pid} 当前状态为「{self._status_label(project.status)}」，"
                "不在待审核阶段，无法打回。"
            )
        await self.project_service.update_status(project, ProjectStatus.DRAFTING)
        await self.project_service.add_message(
            project.id, user.wechat_user_id, "user", f"【管理员打回】{content}"
        )
        await notify_creator_targeted(
            self.db,
            self.wechat,
            project,
            f"管理员把需求《{project.title}》打回继续完善，意见：{content}。"
            f"发 #切换 {pid} 回到这个需求，按意见补充后再回复『确认』重新提交。",
        )
        return f"已打回需求 [{pid}] {project.title} 给提出人继续完善。"

    async def _handle_new_project(
        self,
        user: User,
        session: UserSession,
        wechat_user_id: str,
        command: Command,
        group_id: str | None = None,
    ) -> str:
        repo_name = str(command.args.get("repo", "")).strip()
        desc = str(command.args.get("desc", "")).strip()
        if not repo_name or not desc:
            return (
                "「#新需求」要带上仓库名，格式：#新需求 <仓库> <需求>\n"
                "例：#新需求 oaSys 给装备管理加个规格列\n"
                "不知道有哪些仓库？发 #我的仓库 看看你能提需求的仓库。"
            )

        repo = await self.project_service.get_repo_by_name(repo_name)
        if repo is None:
            return (
                f"未找到仓库「{repo_name}」。发 #我的仓库 看看你能提需求的仓库别名，"
                "再用「#新需求 <仓库> <需求>」重发。"
            )

        if not await self._user_can_access_repo(user, repo.id):
            return (
                f"你还没有「{repo_name}」的提需求权限，请联系管理员开通后再试。\n"
                "可发送 #我的仓库 查看你当前能提需求的仓库。"
            )

        return await self._handle_new_project_internal(
            user, session, wechat_user_id, repo, desc, group_id=group_id
        )

    async def _handle_new_project_internal(
        self,
        user: User,
        session: UserSession,
        wechat_user_id: str,
        repo: Repo,
        desc: str,
        group_id: str | None = None,
    ) -> str:
        """Variant of _handle_new_project where (repo, desc) are already resolved
        — used by GroupMessageRouter when the bound group implies the repo.
        """
        project = await self.project_service.create_project(
            repo_id=repo.id,
            title=self._build_project_title(desc),
            creator_id=user.id,
            wechat_group_id=group_id,
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
            "需求沟通完成后回复『确认』即可生成方案。"
        )

    async def _handle_chat(
        self,
        user: User,
        session: UserSession,
        wechat_user_id: str,
        command: Command,
    ) -> str:
        content = str(command.args.get("content", "")).strip()
        return await self._handle_chat_internal(user, session, wechat_user_id, content)

    async def _handle_chat_internal(
        self,
        user: User,
        session: UserSession,
        wechat_user_id: str,
        content: str,
    ) -> str:
        del user
        if not content.strip():
            return "请输入要补充的需求内容。"

        project, repo, error_reply = await self._get_active_project_context(session)
        if error_reply is not None or project is None or repo is None:
            return error_reply or "当前没有可继续沟通的项目，请先发送 #新需求。"

        if project.status == ProjectStatus.REVIEWING.value or session.state == SessionState.CONFIRMING.value:
            return "当前方案已生成，如需调整请直接说『改一下…』，或回复『确认』提交审核。"

        if session.state == SessionState.SCORING.value:
            return "当前项目正在等待评分，请发送 #评分 <1-10> <反馈>。"

        if project.status == ProjectStatus.COMPLETED.value:
            # 已完成项目下的零碎消息(未达开新轮门槛):友好引导,不冷拒。
            # 够实质的新需求会在意图层直接开新一轮,不会走到这里。
            return (
                "这个项目已经完成啦～想做点新东西，直接把要做的说清楚点就行"
                "（比如“加个颜色筛选，能按颜色筛装备”），我帮你开新一轮；"
                "也可以发「#新需求 <仓库> <需求>」。"
            )

        if project.status != ProjectStatus.DRAFTING.value:
            return f"当前项目状态为「{self._status_label(project.status)}」，不在需求沟通阶段，请发送 #状态 查看进度。"

        history = await self.project_service.get_messages(project.id)
        await self.project_service.add_message(project.id, wechat_user_id, "user", content)
        await self.session_manager.update_session_state(session, SessionState.CHATTING, project.id)

        ai_reply = await self.pm_agent.chat(project, repo, history, content)
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
        await self._notify_admins_for_review(project)

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
        feedback = str(command.args.get("content", "")).strip()
        return await self._handle_modify_internal(user, session, wechat_user_id, feedback)

    async def _handle_modify_internal(
        self,
        user: User,
        session: UserSession,
        wechat_user_id: str,
        feedback: str,
    ) -> str:
        del user
        if not feedback.strip():
            return "请告诉我具体要怎么改。"

        project, repo, error_reply = await self._get_active_project_context(session)
        if error_reply is not None or project is None or repo is None:
            return error_reply or "当前没有可修改的项目，请先发送 #新需求。"

        if not project.prd_content:
            return "当前项目还没有生成方案，请先继续沟通后回复『确认』。"

        if project.status == ProjectStatus.COMPLETED.value:
            return "当前项目已经完成，如需新调整请发送 #新需求 重新开始。"

        # 验收阶段（含等待和已部署）→ 直接派 AI 改代码，不动 PRD
        if project.status in {
            ProjectStatus.ACCEPTANCE.value,
            ProjectStatus.DEPLOYED.value,
        }:
            return await self._dispatch_fix_iteration(
                project, repo, feedback, wechat_user_id,
            )

        if project.status not in {ProjectStatus.REVIEWING.value, ProjectStatus.REJECTED.value}:
            return f"当前项目状态为「{self._status_label(project.status)}」，暂时不能修改方案。"

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
            "方案已根据最新反馈完成更新。",
        )
        await self._notify_admins_for_review(project)

        return f"已根据你的反馈更新方案：\n\n{updated_prd}"

    async def _dispatch_fix_iteration(
        self,
        project: Project,
        repo: Repo,
        feedback: str,
        wechat_user_id: str,
    ) -> str:
        """Acceptance-stage `#修改`：派 dev-agent 改代码（不动 PRD）。"""
        from app.services.project_review import request_fix_iteration
        try:
            issue_number = await request_fix_iteration(
                self.db,
                project=project,
                repo=repo,
                fix_description=feedback,
            )
        except Exception:
            logger.exception(
                "fix iteration dispatch failed project=%s repo=%s",
                project.id, repo.id,
            )
            return "派发修复任务失败，请稍后重试或联系管理员。"

        await self.project_service.add_message(
            project.id, wechat_user_id, "user", f"#修改 {feedback}"
        )
        await self.project_service.add_message(
            project.id, wechat_user_id, "assistant",
            f"已派 AI 开始修复（issue #{issue_number}），修好后会在测试环境/生产环境再次通知你验收。",
        )
        return (
            f"已派 AI 开始修复（GitHub issue #{issue_number}）。\n"
            "修好后会重新部署到测试环境，请稍候。"
        )

    async def _handle_score(
        self,
        user: User,
        session: UserSession,
        wechat_user_id: str,
        command: Command,
    ) -> str:
        try:
            score = int(command.args.get("score", 0))
        except (TypeError, ValueError):
            return "评分必须是 1-10 之间的整数，例如：#评分 8 功能基本符合预期"
        if not (1 <= score <= 10):
            return "评分必须是 1-10 之间的整数，例如：#评分 8 功能基本符合预期"

        comment = str(command.args.get("comment", "")).strip()
        if not comment:
            return "评分时请同时附带文字反馈，例如：#评分 8 功能基本符合预期"

        project, _, error_reply = await self._get_active_project_context(session)
        if error_reply is not None or project is None:
            return error_reply or "当前没有可评分的项目，请先发送 #状态 或 #列表 查看项目。"

        # 状态白名单
        if project.status == ProjectStatus.COMPLETED.value:
            return "该项目已完成评分，不能重复评分。如有新反馈请发起 #新需求。"
        if project.status == ProjectStatus.STAGED.value:
            return "PR 还在 staging 环境，等合并到 main 部署上线后再评分。"
        if project.status not in {
            ProjectStatus.DEPLOYED.value,
            ProjectStatus.ACCEPTANCE.value,
        }:
            return f"当前项目状态为「{self._status_label(project.status)}」，暂时不能评分。"

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

    async def _handle_status_internal(
        self,
        user: User,
        session: UserSession,
    ) -> str:
        return await self._handle_status(user, session)

    async def _handle_review_internal(
        self,
        user: User,
        project_id: int,
        decision: str,
        reason: str,
    ) -> str:
        cmd = Command(
            type="review",
            args={
                "project_id": project_id,
                "decision": decision,
                "reason": reason,
            },
        )
        return await self._handle_review_command(user, cmd)

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
        # 已关闭(作废)的项目不再展示。
        projects = [p for p in projects if p.status != ProjectStatus.CLOSED.value]
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

    def _handle_help(self, user: User | None = None) -> str:
        admin_lines = (
            "\n#审核 <项目id> 通过\n"
            "#审核 <项目id> 拒绝 <理由>\n"
        ) if user is not None and user.role == "admin" else ""
        return (
            "可用指令：\n"
            "#新需求 <仓库> <需求描述>\n"
            "#确认\n"
            "#修改 <修改意见>\n"
            "#评分 <1-10> <反馈>\n"
            "#状态\n"
            "#列表\n"
            "#我的仓库\n"
            "#帮助"
            f"{admin_lines}\n\n"
            "在群里使用时,请先 @ 机器人 再输入指令,例如:@SuperUserAI #新需求 sandbox 一个 todo 应用。\n"
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

    async def _handle_review_command(self, user: User, command: Command) -> str:
        if user.role != "admin":
            return "只有管理员可以使用 #审核 命令。"

        try:
            project_id = int(command.args.get("project_id"))
            decision = str(command.args.get("decision", ""))
        except (TypeError, ValueError):
            return "审核命令参数解析失败，请使用:#审核 <项目id> 通过/拒绝 [理由]"
        if decision not in {"通过", "拒绝"}:
            return "无效的审核决定，请使用「通过」或「拒绝」。"
        reason = str(command.args.get("reason", ""))

        project = await self.db.get(Project, project_id)
        if project is None:
            return f"找不到项目 #{project_id}。"

        if project.status != ProjectStatus.REVIEWING.value:
            return (
                f"项目 #{project.id} 当前状态是「{self._status_label(project.status)}」，"
                "不是待审核，无法审批。"
            )

        repo = await self.db.get(Repo, project.repo_id) if project.repo_id else None

        if decision == "通过":
            if repo is None:
                return "项目没有关联仓库，无法创建 GitHub Issue。"
            try:
                issue_number = await create_issue_for_project(
                    self.db,
                    project=project,
                    repo=repo,
                    approver_id=user.id,
                )
            except Exception as exc:
                # GitHub 调用失败时,create_issue_for_project 在写入 project 字段前就抛了,
                # 没有需要回滚的脏状态;让外层 handle() 的 commit 自然走空 transaction。
                logger.exception("create_issue_for_project failed for project=%s", project.id)
                return f"创建 GitHub Issue 失败:{exc}"
            await self.db.refresh(project)
            await notify_creator_approved(self.db, self.wechat, project)
            return (
                f"✅ 已审核通过项目 #{project.id}，"
                f"GitHub Issue #{issue_number} 已创建，dev-agent 30 秒内会拾取。"
            )

        # 拒绝路径
        project.status = ProjectStatus.REJECTED.value
        await self.db.flush()
        await self.db.refresh(project)
        await notify_creator_rejected(self.db, self.wechat, project, reason)
        return f"已拒绝项目 #{project.id}。"

    async def _notify_admins_for_review(self, project: Project) -> None:
        prd_excerpt = (project.prd_content or "").strip()
        if len(prd_excerpt) > 600:
            prd_excerpt = prd_excerpt[:600] + "…"

        creator = await self.db.get(User, project.creator_id)
        creator_name = (
            (creator.nickname or creator.wechat_user_id) if creator else "未知"
        )
        body = (
            f"📝 新需求待审核 #{project.id}\n"
            f"标题:{project.title}\n"
            f"提出人:{creator_name}\n\n"
            f"PRD 摘要:\n{prd_excerpt or '(空)'}\n\n"
            f"通过:#审核 {project.id} 通过\n"
            f"拒绝:#审核 {project.id} 拒绝 <理由>"
        )

        # 如果项目来自群,直接发到群里(所有成员可见,免逐个私聊 admin)
        if project.wechat_group_id:
            try:
                await self.wechat.send_text(project.wechat_group_id, body)
                logger.info(
                    "Sent review notification to group project=%s group=%s",
                    project.id,
                    project.wechat_group_id,
                )
                return
            except Exception:
                logger.exception(
                    "notify_review to group failed; falling back to admin DMs project=%s group=%s",
                    project.id,
                    project.wechat_group_id,
                )

        stmt = select(User).where(
            User.role == "admin",
            User.wechat_user_id.is_not(None),
        )
        result = await self.db.execute(stmt)
        admins = list(result.scalars().all())
        if not admins:
            return

        for admin in admins:
            try:
                await self.wechat.send_text(admin.wechat_user_id, body)
            except Exception:
                logger.exception(
                    "notify admin failed admin=%s project=%s",
                    admin.wechat_user_id,
                    project.id,
                )

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
            ProjectStatus.STAGED.value: "测试环境就绪",
            ProjectStatus.ACCEPTANCE.value: "待验收",
            ProjectStatus.COMPLETED.value: "已完成",
            ProjectStatus.REJECTED.value: "已驳回",
            ProjectStatus.CLOSED.value: "已关闭",
        }
        return labels.get(status, status)
