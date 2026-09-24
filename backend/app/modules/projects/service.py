"""Бизнес-правила проектов и участия в них."""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ProjectRole
from app.core.errors import ApiError
from app.core.permissions import AccessContext
from app.modules.projects.models import Project, ProjectMember
from app.modules.projects.repository import ProjectRepository
from app.modules.projects.schemas import ProjectCreate, ProjectUpdate
from app.modules.users.models import User
from app.modules.workspaces.service import WorkspaceService

ROLE_RANK = {ProjectRole.VIEWER: 0, ProjectRole.MEMBER: 1, ProjectRole.ADMIN: 2}

Member = tuple[ProjectMember, User]


def _check_dates(start: date | None, target: date | None) -> None:
    """Проверка после слияния с сохранёнными датами: PATCH часто присылает одну из двух."""
    if start is not None and target is not None and target < start:
        raise ApiError(
            400,
            "invalid_date_range",
            "Дата окончания раньше даты начала",
            {"start_date": start.isoformat(), "target_date": target.isoformat()},
        )


class ProjectService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._projects = ProjectRepository(session)
        self._workspaces = WorkspaceService(session)

    async def create(self, ctx: AccessContext, data: ProjectCreate) -> Project:
        await self._check_lead(ctx.workspace_id, data.lead_id)
        _check_dates(data.start_date, data.target_date)
        project = await self._projects.create(
            workspace_id=ctx.workspace_id, team_id=ctx.team, **data.model_dump()
        )
        await self._session.commit()
        return project

    async def list_for_team(
        self, ctx: AccessContext, *, include_archived: bool
    ) -> Sequence[Project]:
        return await self._projects.list_for_team(
            ctx.workspace_id, ctx.team, include_archived=include_archived
        )

    async def get(self, ctx: AccessContext) -> Project:
        project = await self._projects.get_in_workspace(ctx.project, ctx.workspace_id)
        if project is None:
            raise ApiError(404, "project_not_found", "Проект не найден")
        return project

    async def get_in_workspace(self, project_id: UUID, workspace_id: UUID) -> Project | None:
        return await self._projects.get_in_workspace(project_id, workspace_id)

    async def update(self, ctx: AccessContext, data: ProjectUpdate) -> Project:
        project = await self.get(ctx)
        changes = data.model_dump(exclude_unset=True)
        if changes.get("lead_id") is not None:
            await self._check_lead(ctx.workspace_id, changes["lead_id"])
        _check_dates(
            changes.get("start_date", project.start_date),
            changes.get("target_date", project.target_date),
        )

        for field, value in changes.items():
            setattr(project, field, value)
        if changes:
            project.updated_at = datetime.now(UTC)
        await self._session.commit()
        return project

    async def archive(self, ctx: AccessContext) -> Project:
        project = await self.get(ctx)
        # Повторное архивирование не сдвигает метку: она означает «когда убрали».
        if project.archived_at is None:
            project.archived_at = datetime.now(UTC)
            project.updated_at = project.archived_at
            await self._session.commit()
        return project

    async def unarchive(self, ctx: AccessContext) -> Project:
        project = await self.get(ctx)
        if project.archived_at is not None:
            project.archived_at = None
            project.updated_at = datetime.now(UTC)
            await self._session.commit()
        return project

    async def delete(self, ctx: AccessContext) -> None:
        await self._projects.delete(ctx.project, ctx.workspace_id)
        await self._session.commit()

    async def list_members(self, ctx: AccessContext) -> list[Member]:
        return await self._projects.list_members(ctx.project)

    async def change_member_role(
        self, ctx: AccessContext, user_id: UUID, role: ProjectRole
    ) -> Member:
        member, user = await self._member(ctx.project, user_id)
        member.role = role
        await self._session.commit()
        return member, user

    async def remove_member(self, ctx: AccessContext, user_id: UUID) -> None:
        member, _ = await self._member(ctx.project, user_id)
        await self._projects.delete_member(member)
        await self._session.commit()

    async def grant(
        self, workspace_id: UUID, project_id: UUID, user_id: UUID, role: ProjectRole
    ) -> None:
        """Членство по приглашению: создать или повысить. Без commit."""
        member = await self._projects.get_member(project_id, user_id)
        if member is None:
            await self._projects.add_member(
                workspace_id=workspace_id, project_id=project_id, user_id=user_id, role=role
            )
        elif ROLE_RANK[role] > ROLE_RANK[ProjectRole(member.role)]:
            member.role = role
            await self._session.flush()

    async def get_member_role(self, project_id: UUID, user_id: UUID) -> ProjectRole | None:
        member = await self._projects.get_member(project_id, user_id)
        return ProjectRole(member.role) if member is not None else None

    async def memberships_of(self, user_id: UUID) -> Sequence[ProjectMember]:
        return await self._projects.memberships_of(user_id)

    async def _check_lead(self, workspace_id: UUID, lead_id: UUID | None) -> None:
        if lead_id is None:
            return
        if await self._workspaces.get_member_role(workspace_id, lead_id) is None:
            raise ApiError(
                400,
                "lead_not_member",
                "Ответственным может быть только участник рабочего пространства",
                {"lead_id": str(lead_id)},
            )

    async def _member(self, project_id: UUID, user_id: UUID) -> Member:
        found = await self._projects.get_member_with_user(project_id, user_id)
        if found is None:
            raise ApiError(404, "member_not_found", "Участник не найден")
        return found
