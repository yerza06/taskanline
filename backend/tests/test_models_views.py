"""Таблица views: инвариант scope держит сама база."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.views.models import View
from tests.test_models_org import make_team, make_user, make_workspace


@pytest.mark.parametrize(
    ("scope", "with_owner", "with_team", "valid"),
    [
        ("user", True, False, True),
        ("user", False, False, False),
        ("user", True, True, False),
        ("team", False, True, True),
        ("team", True, True, False),
        ("team", False, False, False),
        ("workspace", False, False, True),
        ("workspace", True, False, False),
        ("workspace", False, True, False),
    ],
)
async def test_scope_invariant(
    db_session: AsyncSession, scope: str, with_owner: bool, with_team: bool, valid: bool
) -> None:
    user = await make_user(db_session)
    workspace = await make_workspace(db_session, user)
    team = await make_team(db_session, workspace)
    db_session.add(
        View(
            workspace_id=workspace.id,
            scope=scope,
            owner_id=user.id if with_owner else None,
            team_id=team.id if with_team else None,
            name="Срез",
            filters={},
            position=0,
            created_by=user.id,
        )
    )

    if valid:
        await db_session.flush()
    else:
        with pytest.raises(IntegrityError):
            await db_session.flush()


async def test_sort_by_is_checked(db_session: AsyncSession) -> None:
    user = await make_user(db_session)
    workspace = await make_workspace(db_session, user)
    db_session.add(
        View(
            workspace_id=workspace.id,
            scope="workspace",
            name="Срез",
            filters={},
            sort_by="random",
            position=0,
            created_by=user.id,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()
