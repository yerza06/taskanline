"""Таблицы этапа 2: ограничения, уникальность и каскады в самой PostgreSQL."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.invitations.models import Invitation
from app.modules.projects.models import Project, ProjectMember
from app.modules.teams.models import Team, TeamMember
from app.modules.users.models import User
from app.modules.workspaces.models import Workspace, WorkspaceMember


async def make_user(session: AsyncSession, email: str = "ivan@example.com") -> User:
    user = User(email=email, password_hash="$argon2id$fake", full_name="Иван")
    session.add(user)
    await session.flush()
    return user


async def make_workspace(session: AsyncSession, owner: User, slug: str = "acme") -> Workspace:
    workspace = Workspace(name="Acme", slug=slug, created_by=owner.id)
    session.add(workspace)
    await session.flush()
    session.add(WorkspaceMember(workspace_id=workspace.id, user_id=owner.id, role="owner"))
    await session.flush()
    return workspace


async def make_team(session: AsyncSession, workspace: Workspace, key: str = "ENG") -> Team:
    team = Team(workspace_id=workspace.id, key=key, name="Engineering")
    session.add(team)
    await session.flush()
    return team


class TestWorkspace:
    async def test_slug_is_case_insensitive_unique(self, db_session: AsyncSession) -> None:
        owner = await make_user(db_session)
        await make_workspace(db_session, owner, "acme")
        db_session.add(Workspace(name="Другой", slug="ACME", created_by=owner.id))

        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_member_role_is_checked(self, db_session: AsyncSession) -> None:
        owner = await make_user(db_session)
        workspace = await make_workspace(db_session, owner)
        other = await make_user(db_session, "anna@example.com")
        db_session.add(WorkspaceMember(workspace_id=workspace.id, user_id=other.id, role="boss"))

        with pytest.raises(IntegrityError):
            await db_session.flush()


class TestTeam:
    async def test_key_is_unique_within_workspace(self, db_session: AsyncSession) -> None:
        owner = await make_user(db_session)
        workspace = await make_workspace(db_session, owner)
        await make_team(db_session, workspace, "ENG")
        db_session.add(Team(workspace_id=workspace.id, key="ENG", name="Второй"))

        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_same_key_in_other_workspace(self, db_session: AsyncSession) -> None:
        owner = await make_user(db_session)
        first = await make_workspace(db_session, owner, "first")
        second = await make_workspace(db_session, owner, "second")
        await make_team(db_session, first, "ENG")

        await make_team(db_session, second, "ENG")

    @pytest.mark.parametrize("key", ["eng", "E", "ENGINE", "EN1"])
    async def test_key_format_is_checked(self, db_session: AsyncSession, key: str) -> None:
        owner = await make_user(db_session)
        workspace = await make_workspace(db_session, owner)
        db_session.add(Team(workspace_id=workspace.id, key=key, name="Плохой"))

        # DBAPIError — родитель IntegrityError: колонка VARCHAR(5) по спеке, и для
        # "ENGINE" (6 символов) PostgreSQL валит вставку усечением строки раньше
        # проверки CHECK, а не самим нарушением ограничения.
        with pytest.raises(DBAPIError):
            await db_session.flush()


class TestMembershipIntegrity:
    async def test_team_member_requires_workspace_membership(
        self, db_session: AsyncSession
    ) -> None:
        """Членство глубже workspace без членства в нём невозможно на уровне базы."""
        owner = await make_user(db_session)
        workspace = await make_workspace(db_session, owner)
        team = await make_team(db_session, workspace)
        stranger = await make_user(db_session, "anna@example.com")
        db_session.add(
            TeamMember(
                workspace_id=workspace.id, team_id=team.id, user_id=stranger.id, role="member"
            )
        )

        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_leaving_workspace_drops_nested_memberships(
        self, db_session: AsyncSession
    ) -> None:
        owner = await make_user(db_session)
        workspace = await make_workspace(db_session, owner)
        team = await make_team(db_session, workspace)
        project = Project(workspace_id=workspace.id, team_id=team.id, name="Сайт")
        anna = await make_user(db_session, "anna@example.com")
        db_session.add(project)
        membership = WorkspaceMember(workspace_id=workspace.id, user_id=anna.id, role="guest")
        db_session.add(membership)
        await db_session.flush()
        db_session.add(
            TeamMember(workspace_id=workspace.id, team_id=team.id, user_id=anna.id, role="member")
        )
        db_session.add(
            ProjectMember(
                workspace_id=workspace.id, project_id=project.id, user_id=anna.id, role="viewer"
            )
        )
        await db_session.flush()

        await db_session.delete(membership)
        await db_session.flush()
        db_session.expunge_all()

        assert (
            await db_session.scalar(select(TeamMember).where(TeamMember.user_id == anna.id)) is None
        )
        assert (
            await db_session.scalar(select(ProjectMember).where(ProjectMember.user_id == anna.id))
            is None
        )


class TestProject:
    async def test_target_date_not_before_start(self, db_session: AsyncSession) -> None:
        owner = await make_user(db_session)
        team = await make_team(db_session, await make_workspace(db_session, owner))
        db_session.add(
            Project(
                workspace_id=team.workspace_id,
                team_id=team.id,
                name="Сайт",
                start_date=date(2026, 10, 1),
                target_date=date(2026, 9, 1),
            )
        )

        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_status_defaults_to_planned(self, db_session: AsyncSession) -> None:
        owner = await make_user(db_session)
        team = await make_team(db_session, await make_workspace(db_session, owner))
        project = Project(workspace_id=team.workspace_id, team_id=team.id, name="Сайт")
        db_session.add(project)
        await db_session.flush()

        assert project.status == "planned"


def invitation(workspace: Workspace, inviter: User, **overrides: object) -> Invitation:
    fields: dict[str, object] = {
        "workspace_id": workspace.id,
        "email": "anna@example.com",
        "scope_type": "workspace",
        "scope_id": workspace.id,
        "role": "member",
        "token_hash": "a" * 64,
        "invited_by": inviter.id,
        "expires_at": datetime.now(UTC) + timedelta(days=7),
    }
    fields.update(overrides)
    return Invitation(**fields)


class TestInvitation:
    async def test_one_pending_per_email_and_scope(self, db_session: AsyncSession) -> None:
        owner = await make_user(db_session)
        workspace = await make_workspace(db_session, owner)
        db_session.add(invitation(workspace, owner))
        await db_session.flush()
        db_session.add(invitation(workspace, owner, email="ANNA@example.com", token_hash="b" * 64))

        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_accepted_does_not_block_new(self, db_session: AsyncSession) -> None:
        owner = await make_user(db_session)
        workspace = await make_workspace(db_session, owner)
        db_session.add(invitation(workspace, owner, status="accepted"))
        await db_session.flush()

        db_session.add(invitation(workspace, owner, token_hash="b" * 64))
        await db_session.flush()

    async def test_role_must_match_scope(self, db_session: AsyncSession) -> None:
        """`lead` существует только у команды — в workspace так не позвать."""
        owner = await make_user(db_session)
        workspace = await make_workspace(db_session, owner)
        db_session.add(invitation(workspace, owner, role="lead"))

        with pytest.raises(IntegrityError):
            await db_session.flush()

    async def test_owner_role_is_not_invitable(self, db_session: AsyncSession) -> None:
        owner = await make_user(db_session)
        workspace = await make_workspace(db_session, owner)
        db_session.add(invitation(workspace, owner, role="owner"))

        with pytest.raises(IntegrityError):
            await db_session.flush()


async def test_deleting_workspace_cascades(db_session: AsyncSession) -> None:
    owner = await make_user(db_session)
    workspace = await make_workspace(db_session, owner)
    team = await make_team(db_session, workspace)
    db_session.add(Project(workspace_id=workspace.id, team_id=team.id, name="Сайт"))
    db_session.add(invitation(workspace, owner))
    await db_session.flush()
    workspace_id: UUID = workspace.id

    await db_session.delete(workspace)
    await db_session.flush()
    db_session.expunge_all()

    for model in (WorkspaceMember, Team, Project, Invitation):
        assert (
            await db_session.scalar(select(model).where(model.workspace_id == workspace_id)) is None
        )
