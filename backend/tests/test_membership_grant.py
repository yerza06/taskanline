"""Вставка членства без гонки: `add_member_if_absent` и `grant` поверх него.

Два конкурентных accept одного и того же приглашения (или двух приглашений в одно
и то же пространство/команду/проект) раньше оба проходили `get_member is None` и
пытались вставить строку — второй падал в `IntegrityError` на уникальном индексе
и превращался в 500. Здесь строка сперва вставляется напрямую, имитируя гонку, а
затем вызывается `add_member_if_absent` и `grant` поверх неё — они не должны ни
упасть, ни понизить уже выданную роль.
"""

from collections.abc import Awaitable, Callable
from uuid import UUID

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ProjectRole, TeamRole, WorkspaceRole
from app.modules.projects.repository import ProjectRepository
from app.modules.projects.service import ProjectService
from app.modules.teams.repository import TeamRepository
from app.modules.teams.service import TeamService
from app.modules.workspaces.repository import WorkspaceRepository
from app.modules.workspaces.service import WorkspaceService
from tests.org import create_project, create_team, create_workspace, user_id_of

SignUp = Callable[..., Awaitable[AsyncClient]]


async def _join_workspace(
    db_session: AsyncSession, *, workspace_id: str, user_id: UUID, role: WorkspaceRole
) -> None:
    """FK team_members/project_members → workspace_members требует членство раньше."""
    await WorkspaceRepository(db_session).add_member(
        workspace_id=UUID(workspace_id), user_id=user_id, role=role
    )


class TestWorkspaceAddMemberIfAbsent:
    async def test_conflict_keeps_existing_row_instead_of_raising(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        await sign_up("guest@example.com")
        user_id = await user_id_of(db_session, "guest@example.com")
        repo = WorkspaceRepository(db_session)
        await repo.add_member(
            workspace_id=UUID(workspace["id"]), user_id=user_id, role=WorkspaceRole.GUEST
        )

        # Строка уже есть — второй "конкурентный" INSERT не должен упасть в IntegrityError.
        member = await repo.add_member_if_absent(
            workspace_id=UUID(workspace["id"]), user_id=user_id, role=WorkspaceRole.MEMBER
        )

        assert member.role == WorkspaceRole.GUEST

    async def test_inserts_when_row_is_missing(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        await sign_up("guest@example.com")
        user_id = await user_id_of(db_session, "guest@example.com")

        member = await WorkspaceRepository(db_session).add_member_if_absent(
            workspace_id=UUID(workspace["id"]), user_id=user_id, role=WorkspaceRole.MEMBER
        )

        assert member.role == WorkspaceRole.MEMBER


class TestWorkspaceGrantIsRaceSafe:
    async def test_existing_row_is_raised_not_reinserted(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        await sign_up("guest@example.com")
        user_id = await user_id_of(db_session, "guest@example.com")
        await WorkspaceRepository(db_session).add_member(
            workspace_id=UUID(workspace["id"]), user_id=user_id, role=WorkspaceRole.GUEST
        )

        await WorkspaceService(db_session).grant(workspace["id"], user_id, WorkspaceRole.MEMBER)

        role = await WorkspaceService(db_session).get_member_role(workspace["id"], user_id)
        assert role == WorkspaceRole.MEMBER


class TestTeamAddMemberIfAbsent:
    async def test_conflict_keeps_existing_row_instead_of_raising(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        team = await create_team(owner, workspace["id"])
        await sign_up("member@example.com")
        user_id = await user_id_of(db_session, "member@example.com")
        await _join_workspace(
            db_session, workspace_id=workspace["id"], user_id=user_id, role=WorkspaceRole.MEMBER
        )
        repo = TeamRepository(db_session)
        await repo.add_member(
            workspace_id=UUID(workspace["id"]),
            team_id=UUID(team["id"]),
            user_id=user_id,
            role=TeamRole.MEMBER,
        )

        member = await repo.add_member_if_absent(
            workspace_id=UUID(workspace["id"]),
            team_id=UUID(team["id"]),
            user_id=user_id,
            role=TeamRole.LEAD,
        )

        assert member.role == TeamRole.MEMBER


class TestTeamGrantIsRaceSafe:
    async def test_existing_row_is_raised_not_reinserted(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        team = await create_team(owner, workspace["id"])
        await sign_up("member@example.com")
        user_id = await user_id_of(db_session, "member@example.com")
        await _join_workspace(
            db_session, workspace_id=workspace["id"], user_id=user_id, role=WorkspaceRole.MEMBER
        )
        await TeamRepository(db_session).add_member(
            workspace_id=UUID(workspace["id"]),
            team_id=UUID(team["id"]),
            user_id=user_id,
            role=TeamRole.MEMBER,
        )

        await TeamService(db_session).grant(workspace["id"], team["id"], user_id, TeamRole.LEAD)

        role = await TeamService(db_session).get_member_role(team["id"], user_id)
        assert role == TeamRole.LEAD


class TestProjectAddMemberIfAbsent:
    async def test_conflict_keeps_existing_row_instead_of_raising(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        team = await create_team(owner, workspace["id"])
        project = await create_project(owner, team["id"])
        await sign_up("viewer@example.com")
        user_id = await user_id_of(db_session, "viewer@example.com")
        await _join_workspace(
            db_session, workspace_id=workspace["id"], user_id=user_id, role=WorkspaceRole.GUEST
        )
        repo = ProjectRepository(db_session)
        await repo.add_member(
            workspace_id=UUID(workspace["id"]),
            project_id=UUID(project["id"]),
            user_id=user_id,
            role=ProjectRole.VIEWER,
        )

        member = await repo.add_member_if_absent(
            workspace_id=UUID(workspace["id"]),
            project_id=UUID(project["id"]),
            user_id=user_id,
            role=ProjectRole.MEMBER,
        )

        assert member.role == ProjectRole.VIEWER


class TestProjectGrantIsRaceSafe:
    async def test_existing_row_is_raised_not_reinserted(
        self, sign_up: SignUp, db_session: AsyncSession
    ) -> None:
        owner = await sign_up("owner@example.com")
        workspace = await create_workspace(owner)
        team = await create_team(owner, workspace["id"])
        project = await create_project(owner, team["id"])
        await sign_up("viewer@example.com")
        user_id = await user_id_of(db_session, "viewer@example.com")
        await _join_workspace(
            db_session, workspace_id=workspace["id"], user_id=user_id, role=WorkspaceRole.GUEST
        )
        await ProjectRepository(db_session).add_member(
            workspace_id=UUID(workspace["id"]),
            project_id=UUID(project["id"]),
            user_id=user_id,
            role=ProjectRole.VIEWER,
        )

        await ProjectService(db_session).grant(
            workspace["id"], project["id"], user_id, ProjectRole.MEMBER
        )

        role = await ProjectService(db_session).get_member_role(project["id"], user_id)
        assert role == ProjectRole.MEMBER
