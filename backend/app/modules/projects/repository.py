"""Запросы к projects и project_members."""

from collections.abc import Sequence
from datetime import date
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ProjectRole, ProjectStatus
from app.modules.projects.models import Project, ProjectMember
from app.modules.users.models import User


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_many(self, project_ids: Sequence[UUID], workspace_id: UUID) -> Sequence[Project]:
        if not project_ids:
            return []
        stmt = select(Project).where(
            Project.id.in_(project_ids), Project.workspace_id == workspace_id
        )
        return (await self._session.scalars(stmt)).all()

    async def get_in_workspace(self, project_id: UUID, workspace_id: UUID) -> Project | None:
        project: Project | None = await self._session.scalar(
            select(Project).where(Project.id == project_id, Project.workspace_id == workspace_id)
        )
        return project

    async def create(
        self,
        *,
        workspace_id: UUID,
        team_id: UUID,
        name: str,
        description: str | None,
        status: ProjectStatus,
        lead_id: UUID | None,
        start_date: date | None,
        target_date: date | None,
    ) -> Project:
        project = Project(
            workspace_id=workspace_id,
            team_id=team_id,
            name=name,
            description=description,
            status=status,
            lead_id=lead_id,
            start_date=start_date,
            target_date=target_date,
        )
        self._session.add(project)
        await self._session.flush()
        return project

    async def list_for_team(
        self, workspace_id: UUID, team_id: UUID, *, include_archived: bool
    ) -> Sequence[Project]:
        stmt = (
            select(Project)
            .where(Project.workspace_id == workspace_id, Project.team_id == team_id)
            .order_by(Project.name, Project.id)
        )
        if not include_archived:
            stmt = stmt.where(Project.archived_at.is_(None))
        return (await self._session.scalars(stmt)).all()

    async def delete(self, project_id: UUID, workspace_id: UUID) -> None:
        await self._session.execute(
            delete(Project).where(Project.id == project_id, Project.workspace_id == workspace_id)
        )

    async def get_member(self, project_id: UUID, user_id: UUID) -> ProjectMember | None:
        member: ProjectMember | None = await self._session.scalar(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id, ProjectMember.user_id == user_id
            )
        )
        return member

    async def get_member_with_user(
        self, project_id: UUID, user_id: UUID
    ) -> tuple[ProjectMember, User] | None:
        stmt = (
            select(ProjectMember, User)
            .join(User, User.id == ProjectMember.user_id)
            .where(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
        )
        return (await self._session.execute(stmt)).tuples().one_or_none()

    async def list_members(self, project_id: UUID) -> list[tuple[ProjectMember, User]]:
        stmt = (
            select(ProjectMember, User)
            .join(User, User.id == ProjectMember.user_id)
            .where(ProjectMember.project_id == project_id)
            .order_by(User.full_name, User.id)
        )
        return list((await self._session.execute(stmt)).tuples())

    async def add_member(
        self, *, workspace_id: UUID, project_id: UUID, user_id: UUID, role: ProjectRole
    ) -> ProjectMember:
        member = ProjectMember(
            workspace_id=workspace_id, project_id=project_id, user_id=user_id, role=role
        )
        self._session.add(member)
        await self._session.flush()
        return member

    async def add_member_if_absent(
        self, *, workspace_id: UUID, project_id: UUID, user_id: UUID, role: ProjectRole
    ) -> ProjectMember:
        """Вставка без гонки: `ON CONFLICT DO NOTHING` вместо «проверил — вставил».

        Два конкурентных accept одного и того же членства раньше оба проходили
        `get_member is None` и падали вторым `INSERT` в `IntegrityError` на
        `idx_project_members_unique`.
        """
        stmt = (
            pg_insert(ProjectMember)
            .values(workspace_id=workspace_id, project_id=project_id, user_id=user_id, role=role)
            .on_conflict_do_nothing(index_elements=["project_id", "user_id"])
        )
        await self._session.execute(stmt)
        await self._session.flush()
        member = await self.get_member(project_id, user_id)
        assert member is not None, "строка обязана существовать после INSERT ... ON CONFLICT"
        return member

    async def delete_member(self, member: ProjectMember) -> None:
        await self._session.delete(member)
        await self._session.flush()

    async def memberships_of(self, user_id: UUID) -> Sequence[ProjectMember]:
        stmt = (
            select(ProjectMember)
            .where(ProjectMember.user_id == user_id)
            .order_by(ProjectMember.created_at)
        )
        return (await self._session.scalars(stmt)).all()
