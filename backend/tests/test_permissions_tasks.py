"""Права на объекты этапа 3: задача, статус, метка, комментарий; ключ ENG-142; видимость.

Предикат видимости задач в списках и `compute_effective_role` — две реализации одного
правила §6.2. Тест сверяет их на всех формах членства: расхождение означало бы, что
в списке видно то, что по ссылке отдаёт 404, или наоборот.
"""

from itertools import count
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import WorkspaceRole
from app.core.errors import ApiError
from app.core.permissions import (
    EffectiveRole,
    compute_effective_role,
    find_task_by_key,
    load_access,
    task_visibility,
)
from app.modules.comments.models import Comment
from app.modules.labels.models import Label
from app.modules.projects.models import Project
from app.modules.states.models import WorkflowState
from app.modules.tasks.models import Task
from app.modules.teams.models import Team
from app.modules.users.models import User
from app.modules.workspaces.models import Workspace
from tests.org import grant

_numbers = count(1)


async def user(session: AsyncSession, email: str) -> User:
    person = User(email=email, password_hash="x", full_name=email.split("@")[0])
    session.add(person)
    await session.flush()
    return person


async def workspace(session: AsyncSession, owner: User, slug: str) -> Workspace:
    space = Workspace(name=slug, slug=slug, created_by=owner.id)
    session.add(space)
    await session.flush()
    await grant(session, user_id=owner.id, workspace_id=space.id, workspace_role="owner")
    return space


async def team(
    session: AsyncSession, space: Workspace, key: str, *, private: bool = False
) -> tuple[Team, WorkflowState]:
    crew = Team(workspace_id=space.id, key=key, name=key, is_private=private)
    session.add(crew)
    await session.flush()
    state = WorkflowState(
        workspace_id=space.id,
        team_id=crew.id,
        name="Todo",
        type="unstarted",
        color="#e2e2e2",
        position=0,
        is_default=True,
    )
    session.add(state)
    await session.flush()
    return crew, state


async def task(
    session: AsyncSession,
    crew: Team,
    state: WorkflowState,
    creator: User,
    project: Project | None = None,
    number: int | None = None,
) -> Task:
    item = Task(
        workspace_id=crew.workspace_id,
        team_id=crew.id,
        project_id=project.id if project else None,
        number=number or next(_numbers),
        title="Задача",
        state_id=state.id,
        creator_id=creator.id,
        sort_order="a0",
    )
    session.add(item)
    await session.flush()
    return item


async def project(session: AsyncSession, crew: Team, name: str = "Сайт") -> Project:
    item = Project(workspace_id=crew.workspace_id, team_id=crew.id, name=name)
    session.add(item)
    await session.flush()
    return item


class TestLoadAccessForTask:
    async def test_task_in_project_uses_project_membership(self, db_session: AsyncSession) -> None:
        owner = await user(db_session, "owner@example.com")
        space = await workspace(db_session, owner, "acme")
        crew, state = await team(db_session, space, "ENG")
        site = await project(db_session, crew)
        item = await task(db_session, crew, state, owner, site)
        anna = await user(db_session, "anna@example.com")
        await grant(
            db_session,
            user_id=anna.id,
            workspace_id=space.id,
            workspace_role="guest",
            project_id=site.id,
            project_role="viewer",
        )

        access = await load_access(db_session, anna.id, "task", item.id)

        assert access is not None
        assert (access.team_id, access.project_id) == (crew.id, site.id)
        assert compute_effective_role(access) == EffectiveRole.VIEWER

    async def test_backlog_task_is_hidden_from_project_contractor(
        self, db_session: AsyncSession
    ) -> None:
        owner = await user(db_session, "owner@example.com")
        space = await workspace(db_session, owner, "acme")
        crew, state = await team(db_session, space, "ENG")
        site = await project(db_session, crew)
        backlog = await task(db_session, crew, state, owner)
        anna = await user(db_session, "anna@example.com")
        await grant(
            db_session,
            user_id=anna.id,
            workspace_id=space.id,
            workspace_role="guest",
            project_id=site.id,
            project_role="admin",
        )

        access = await load_access(db_session, anna.id, "task", backlog.id)

        assert access is not None
        assert compute_effective_role(access) is None

    async def test_project_of_other_team_is_ignored(self, db_session: AsyncSession) -> None:
        """Защита в глубину: задача команды A с project_id проекта команды B не
        открывается участнику проекта B."""
        owner = await user(db_session, "owner@example.com")
        space = await workspace(db_session, owner, "acme")
        crew, state = await team(db_session, space, "ENG", private=True)
        other, _ = await team(db_session, space, "DES")
        foreign = await project(db_session, other)
        item = await task(db_session, crew, state, owner, foreign)
        anna = await user(db_session, "anna@example.com")
        await grant(
            db_session,
            user_id=anna.id,
            workspace_id=space.id,
            workspace_role="guest",
            project_id=foreign.id,
            project_role="admin",
        )

        access = await load_access(db_session, anna.id, "task", item.id)

        assert access is None or compute_effective_role(access) is None

    async def test_state_label_and_comment_resolve_to_their_owner(
        self, db_session: AsyncSession
    ) -> None:
        owner = await user(db_session, "owner@example.com")
        space = await workspace(db_session, owner, "acme")
        crew, state = await team(db_session, space, "ENG")
        site = await project(db_session, crew)
        item = await task(db_session, crew, state, owner, site)
        shared = Label(workspace_id=space.id, name="bug", color="#ff0000")
        own = Label(workspace_id=space.id, team_id=crew.id, name="ui", color="#ff0000")
        note = Comment(workspace_id=space.id, task_id=item.id, author_id=owner.id, body="Привет")
        db_session.add_all([shared, own, note])
        await db_session.flush()

        by_state = await load_access(db_session, owner.id, "state", state.id)
        by_shared = await load_access(db_session, owner.id, "label", shared.id)
        by_own = await load_access(db_session, owner.id, "label", own.id)
        by_comment = await load_access(db_session, owner.id, "comment", note.id)

        assert by_state is not None and (by_state.level, by_state.team_id) == ("team", crew.id)
        assert by_shared is not None and by_shared.level == "workspace"
        assert by_own is not None and (by_own.level, by_own.team_id) == ("team", crew.id)
        assert by_comment is not None
        assert (by_comment.level, by_comment.project_id) == ("project", site.id)


class TestFindTaskByKey:
    async def test_key_is_case_insensitive(self, db_session: AsyncSession) -> None:
        owner = await user(db_session, "owner@example.com")
        space = await workspace(db_session, owner, "acme")
        crew, state = await team(db_session, space, "ENG")
        item = await task(db_session, crew, state, owner, number=142)

        assert await find_task_by_key(db_session, owner.id, "eng-142") == item.id
        assert await find_task_by_key(db_session, owner.id, "ENG-143") is None

    @pytest.mark.parametrize("key", ["ENG", "ENG-", "ENG-0", "E-1", "ENGINE-1", "ENG-1-2", "1-ENG"])
    async def test_malformed_key_is_not_found(self, db_session: AsyncSession, key: str) -> None:
        owner = await user(db_session, "owner@example.com")
        assert await find_task_by_key(db_session, owner.id, key) is None

    async def test_invisible_task_is_not_found(self, db_session: AsyncSession) -> None:
        owner = await user(db_session, "owner@example.com")
        space = await workspace(db_session, owner, "acme")
        crew, state = await team(db_session, space, "ENG", private=True)
        await task(db_session, crew, state, owner, number=1)
        anna = await user(db_session, "anna@example.com")
        await grant(db_session, user_id=anna.id, workspace_id=space.id, workspace_role="member")

        assert await find_task_by_key(db_session, anna.id, "ENG-1") is None

    async def test_ambiguous_key_lists_only_visible_workspaces(
        self, db_session: AsyncSession
    ) -> None:
        owner = await user(db_session, "owner@example.com")
        first = await workspace(db_session, owner, "first")
        second = await workspace(db_session, owner, "second")
        third = await workspace(db_session, owner, "third")
        for space in (first, second, third):
            crew, state = await team(db_session, space, "ENG", private=space is third)
            await task(db_session, crew, state, owner, number=1)
        anna = await user(db_session, "anna@example.com")
        for space in (first, second, third):
            await grant(db_session, user_id=anna.id, workspace_id=space.id, workspace_role="member")

        with pytest.raises(ApiError) as error:
            await find_task_by_key(db_session, anna.id, "ENG-1")

        assert error.value.status_code == 409
        assert error.value.code == "task_key_ambiguous"
        assert sorted(error.value.details["workspace_ids"]) == sorted(
            [str(first.id), str(second.id)]
        )
        assert await find_task_by_key(db_session, anna.id, "ENG-1", workspace_id=second.id)


class TestTaskVisibility:
    async def test_predicate_agrees_with_effective_role(self, db_session: AsyncSession) -> None:
        owner = await user(db_session, "owner@example.com")
        space = await workspace(db_session, owner, "acme")
        public, public_state = await team(db_session, space, "PUB")
        secret, secret_state = await team(db_session, space, "SEC", private=True)
        public_site = await project(db_session, public, "Открытый")
        secret_site = await project(db_session, secret, "Закрытый")
        tasks = [
            await task(db_session, public, public_state, owner),
            await task(db_session, public, public_state, owner, public_site),
            await task(db_session, secret, secret_state, owner),
            await task(db_session, secret, secret_state, owner, secret_site),
        ]

        shapes: list[dict[str, object]] = [
            {"workspace_role": "owner"},
            {"workspace_role": "admin"},
            {"workspace_role": "member"},
            {"workspace_role": "guest"},
            {"workspace_role": "member", "team_id": secret.id, "team_role": "member"},
            {"workspace_role": "guest", "team_id": secret.id, "team_role": "lead"},
            {"workspace_role": "guest", "project_id": secret_site.id, "project_role": "viewer"},
            {"workspace_role": "guest", "project_id": public_site.id, "project_role": "member"},
            {"workspace_role": "member", "project_id": secret_site.id, "project_role": "admin"},
        ]
        for index, shape in enumerate(shapes):
            person = await user(db_session, f"user{index}@example.com")
            await grant(db_session, user_id=person.id, workspace_id=space.id, **shape)  # type: ignore[arg-type]

            expected: set[UUID] = set()
            for item in tasks:
                access = await load_access(db_session, person.id, "task", item.id)
                role = compute_effective_role(access) if access else None
                if role is not None and role >= EffectiveRole.VIEWER:
                    expected.add(item.id)

            visible = set(
                await db_session.scalars(
                    select(Task.id).where(
                        Task.workspace_id == space.id,
                        task_visibility(WorkspaceRole(str(shape["workspace_role"])), person.id),
                    )
                )
            )
            assert visible == expected, shape
