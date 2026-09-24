"""Помощники тестов организационной структуры."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.mail import MailMessage
from app.modules.projects.models import ProjectMember
from app.modules.teams.models import TeamMember
from app.modules.users.models import User
from app.modules.workspaces.models import WorkspaceMember

CSRF = {"X-Requested-With": "XMLHttpRequest"}
PASSWORD = "correct horse battery"


class RecordingMailer:
    """Почтальон тестов: складывает письма в список вместо отправки."""

    def __init__(self) -> None:
        self.sent: list[MailMessage] = []

    async def send(self, message: MailMessage) -> None:
        self.sent.append(message)


async def user_id_of(session: AsyncSession, email: str) -> UUID:
    user_id = await session.scalar(select(User.id).where(User.email == email))
    assert user_id is not None, f"нет пользователя {email}"
    return user_id


async def grant(
    session: AsyncSession,
    *,
    user_id: UUID,
    workspace_id: str | UUID,
    workspace_role: str,
    team_id: str | UUID | None = None,
    team_role: str | None = None,
    project_id: str | UUID | None = None,
    project_role: str | None = None,
) -> None:
    """Членства напрямую в базе — минуя приглашения, которые проверяются отдельно."""
    workspace = UUID(str(workspace_id))
    session.add(WorkspaceMember(workspace_id=workspace, user_id=user_id, role=workspace_role))
    await session.flush()
    if team_id is not None and team_role is not None:
        session.add(
            TeamMember(
                workspace_id=workspace, team_id=UUID(str(team_id)), user_id=user_id, role=team_role
            )
        )
    if project_id is not None and project_role is not None:
        session.add(
            ProjectMember(
                workspace_id=workspace,
                project_id=UUID(str(project_id)),
                user_id=user_id,
                role=project_role,
            )
        )
    await session.flush()
