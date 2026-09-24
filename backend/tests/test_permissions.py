"""Эффективная роль: чистая функция по §6.2 модели данных и запрос, который её кормит."""

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from uuid6 import uuid7

from app.core.enums import AuthMethod, InstanceRole, ProjectRole, TeamRole, WorkspaceRole
from app.core.errors import ApiError
from app.core.permissions import (
    MIN_ROLE,
    AccessRow,
    EffectiveRole,
    Permission,
    compute_effective_role,
    load_access,
    resolve_access,
)
from app.core.principal import READ, WRITE, Principal
from app.modules.projects.models import Project
from app.modules.teams.models import Team
from app.modules.users.models import User
from app.modules.workspaces.models import Workspace
from tests.org import grant

WS = uuid7()


def row(
    level: str = "project",
    workspace_role: WorkspaceRole | None = WorkspaceRole.MEMBER,
    team_is_private: bool | None = False,
    team_role: TeamRole | None = None,
    project_role: ProjectRole | None = None,
) -> AccessRow:
    return AccessRow(
        level=level,  # type: ignore[arg-type]
        workspace_id=WS,
        team_id=None if level == "workspace" else uuid7(),
        project_id=uuid7() if level == "project" else None,
        workspace_role=workspace_role,
        team_is_private=None if level == "workspace" else team_is_private,
        team_role=team_role,
        project_role=project_role,
    )


class TestComputeEffectiveRole:
    def test_no_workspace_membership_means_no_access(self) -> None:
        """Даже явное членство в проекте без workspace не даёт ничего."""
        assert (
            compute_effective_role(row(workspace_role=None, project_role=ProjectRole.ADMIN)) is None
        )

    @pytest.mark.parametrize(
        ("role", "expected"),
        [
            (WorkspaceRole.OWNER, EffectiveRole.OWNER),
            (WorkspaceRole.ADMIN, EffectiveRole.ADMIN),
            (WorkspaceRole.MEMBER, EffectiveRole.MEMBER),
        ],
    )
    def test_workspace_role_flows_down(self, role: WorkspaceRole, expected: EffectiveRole) -> None:
        assert compute_effective_role(row(workspace_role=role)) == expected

    def test_guest_gets_nothing_below_workspace(self) -> None:
        assert compute_effective_role(row(workspace_role=WorkspaceRole.GUEST)) is None
        assert compute_effective_role(row("team", workspace_role=WorkspaceRole.GUEST)) is None

    def test_guest_sees_workspace_itself(self) -> None:
        assert (
            compute_effective_role(row("workspace", workspace_role=WorkspaceRole.GUEST))
            == EffectiveRole.GUEST
        )

    def test_private_team_hides_from_workspace_member(self) -> None:
        assert compute_effective_role(row(team_is_private=True)) is None

    @pytest.mark.parametrize("role", [WorkspaceRole.ADMIN, WorkspaceRole.OWNER])
    def test_privacy_does_not_apply_to_admins(self, role: WorkspaceRole) -> None:
        assert compute_effective_role(row(workspace_role=role, team_is_private=True)) is not None

    def test_private_team_member_gets_access(self) -> None:
        assert (
            compute_effective_role(row(team_is_private=True, team_role=TeamRole.MEMBER))
            == EffectiveRole.MEMBER
        )

    def test_team_lead_is_admin(self) -> None:
        assert (
            compute_effective_role(row(workspace_role=WorkspaceRole.GUEST, team_role=TeamRole.LEAD))
            == EffectiveRole.ADMIN
        )

    @pytest.mark.parametrize(
        ("role", "expected"),
        [
            (ProjectRole.VIEWER, EffectiveRole.VIEWER),
            (ProjectRole.MEMBER, EffectiveRole.MEMBER),
            (ProjectRole.ADMIN, EffectiveRole.ADMIN),
        ],
    )
    def test_contractor_gets_exactly_project_role(
        self, role: ProjectRole, expected: EffectiveRole
    ) -> None:
        """Сценарий подрядчика: гость + роль в проекте = ровно эта роль."""
        assert (
            compute_effective_role(row(workspace_role=WorkspaceRole.GUEST, project_role=role))
            == expected
        )

    def test_maximum_wins(self) -> None:
        assert (
            compute_effective_role(
                row(workspace_role=WorkspaceRole.MEMBER, project_role=ProjectRole.VIEWER)
            )
            == EffectiveRole.MEMBER
        )


def test_every_permission_has_minimum_role() -> None:
    assert set(MIN_ROLE) == set(Permission)


class TestLoadAccess:
    async def _world(self, session: AsyncSession, *, private: bool = False) -> tuple[User, Project]:
        owner = User(email="owner@example.com", password_hash="x", full_name="Владелец")
        session.add(owner)
        await session.flush()
        workspace = Workspace(name="Acme", slug="acme", created_by=owner.id)
        session.add(workspace)
        await session.flush()
        await grant(session, user_id=owner.id, workspace_id=workspace.id, workspace_role="owner")
        team = Team(workspace_id=workspace.id, key="ENG", name="Eng", is_private=private)
        session.add(team)
        await session.flush()
        project = Project(workspace_id=workspace.id, team_id=team.id, name="Сайт")
        session.add(project)
        await session.flush()
        return owner, project

    async def _user(self, session: AsyncSession, email: str = "anna@example.com") -> User:
        user = User(email=email, password_hash="x", full_name="Анна")
        session.add(user)
        await session.flush()
        return user

    async def test_collects_all_three_levels(self, db_session: AsyncSession) -> None:
        _, project = await self._world(db_session, private=True)
        anna = await self._user(db_session)
        await grant(
            db_session,
            user_id=anna.id,
            workspace_id=project.workspace_id,
            workspace_role="guest",
            team_id=project.team_id,
            team_role="member",
            project_id=project.id,
            project_role="admin",
        )

        access = await load_access(db_session, anna.id, "project", project.id)

        assert access is not None
        assert access.workspace_id == project.workspace_id
        assert access.team_id == project.team_id
        assert access.team_is_private is True
        assert access.workspace_role == WorkspaceRole.GUEST
        assert access.team_role == TeamRole.MEMBER
        assert access.project_role == ProjectRole.ADMIN

    async def test_stranger_row_has_no_roles(self, db_session: AsyncSession) -> None:
        _, project = await self._world(db_session)
        stranger = await self._user(db_session)

        access = await load_access(db_session, stranger.id, "project", project.id)

        assert access is not None
        assert access.workspace_role is None

    async def test_unknown_object_is_none(self, db_session: AsyncSession) -> None:
        stranger = await self._user(db_session)

        assert await load_access(db_session, stranger.id, "team", uuid7()) is None

    async def test_team_level_ignores_project_membership(self, db_session: AsyncSession) -> None:
        """Подрядчик в проекте не видит команду целиком."""
        _, project = await self._world(db_session)
        anna = await self._user(db_session)
        await grant(
            db_session,
            user_id=anna.id,
            workspace_id=project.workspace_id,
            workspace_role="guest",
            project_id=project.id,
            project_role="member",
        )

        access = await load_access(db_session, anna.id, "team", project.team_id)

        assert access is not None
        assert compute_effective_role(access) is None


def principal(user_id: UUID, *, write: bool = True) -> Principal:
    return Principal(
        user_id=user_id,
        instance_role=InstanceRole.USER,
        scopes=frozenset({READ, WRITE} if write else {READ}),
        auth_method=AuthMethod.SESSION,
        token_id=None,
    )


class TestResolveAccess:
    async def test_stranger_gets_404(self, db_session: AsyncSession) -> None:
        owner = User(email="owner@example.com", password_hash="x", full_name="В")
        db_session.add(owner)
        await db_session.flush()
        workspace = Workspace(name="Acme", slug="acme", created_by=owner.id)
        db_session.add(workspace)
        await db_session.flush()

        with pytest.raises(ApiError) as error:
            await resolve_access(
                db_session,
                principal(uuid7()),
                on="workspace",
                object_id=workspace.id,
                permission=Permission.WORKSPACE_READ,
            )

        assert error.value.status_code == 404
        assert error.value.code == "workspace_not_found"

    async def test_insufficient_role_is_403(self, db_session: AsyncSession) -> None:
        owner = User(email="owner@example.com", password_hash="x", full_name="В")
        db_session.add(owner)
        await db_session.flush()
        workspace = Workspace(name="Acme", slug="acme", created_by=owner.id)
        db_session.add(workspace)
        await db_session.flush()
        await grant(
            db_session, user_id=owner.id, workspace_id=workspace.id, workspace_role="member"
        )

        with pytest.raises(ApiError) as error:
            await resolve_access(
                db_session,
                principal(owner.id),
                on="workspace",
                object_id=workspace.id,
                permission=Permission.WORKSPACE_DELETE,
            )

        assert error.value.status_code == 403
        assert error.value.code == "insufficient_role"
        assert error.value.details == {"required": "owner"}

    async def test_read_token_cannot_mutate(self, db_session: AsyncSession) -> None:
        """Scope проверяется раньше роли: ответ не зависит от того, что за объект."""
        with pytest.raises(ApiError) as error:
            await resolve_access(
                db_session,
                principal(uuid7(), write=False),
                on="workspace",
                object_id=uuid7(),
                permission=Permission.WORKSPACE_UPDATE,
            )

        assert error.value.code == "insufficient_scope"
