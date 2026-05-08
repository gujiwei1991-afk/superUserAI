from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Message, Project, Repo
from app.services.github_service import GitHubService
from shared.constants import ProjectStatus


class ProjectService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_repo_by_name(self, name: str) -> Repo | None:
        normalized_name = name.strip()
        stmt = select(Repo).where(func.lower(Repo.name) == normalized_name.casefold())
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_repo_by_name_or_id(self, repo_id: int) -> Repo | None:
        return await self.db.get(Repo, repo_id)

    async def create_project(
        self,
        repo_id: int,
        title: str,
        creator_id: int,
        wechat_group_id: str | None = None,
    ) -> Project:
        project = Project(
            repo_id=repo_id,
            title=title,
            creator_id=creator_id,
            status=ProjectStatus.DRAFTING.value,
            wechat_group_id=wechat_group_id,
        )
        self.db.add(project)
        await self.db.flush()
        return project

    async def get_project(self, project_id: int) -> Project | None:
        return await self.db.get(Project, project_id)

    async def update_status(self, project: Project, status: ProjectStatus) -> Project:
        project.status = status.value
        await self.db.flush()
        return project

    async def save_prd(self, project: Project, prd_content: str) -> Project:
        project.prd_content = prd_content
        await self.db.flush()
        return project

    async def approve_and_create_issue(
        self,
        project: Project,
        repo: Repo,
        approver_id: int,
    ) -> int:
        github = GitHubService()
        footer = f"---\nSuperUserAI Project ID: {project.id}"
        issue_body = (
            f"{project.prd_content.strip()}\n\n{footer}"
            if project.prd_content and project.prd_content.strip()
            else footer
        )

        try:
            issue_data = await github.create_issue(
                owner=repo.github_owner,
                repo=repo.github_repo,
                title=f"[SuperUserAI] {project.title}",
                body=issue_body,
                labels=["superuserai", "auto-dev"],
            )
        finally:
            await github.close()

        issue_number = int(issue_data["number"])
        project.github_issue_number = issue_number
        project.approver_id = approver_id
        project.status = ProjectStatus.APPROVED.value
        await self.db.flush()
        return issue_number

    async def get_messages(self, project_id: int) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.project_id == project_id)
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def add_message(
        self,
        project_id: int,
        wechat_user_id: str,
        role: str,
        content: str,
        msg_type: int | None = None,
    ) -> Message:
        message = Message(
            project_id=project_id,
            wechat_user_id=wechat_user_id,
            role=role,
            content=content,
            msg_type=msg_type,
        )
        self.db.add(message)
        await self.db.flush()
        return message

    async def get_user_projects(self, creator_id: int) -> list[Project]:
        stmt = (
            select(Project)
            .where(Project.creator_id == creator_id)
            .order_by(Project.created_at.desc(), Project.id.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
