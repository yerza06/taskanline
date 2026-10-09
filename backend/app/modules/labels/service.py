"""Бизнес-правила меток."""

from collections import defaultdict
from collections.abc import Collection, Sequence
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.permissions import AccessContext
from app.modules.labels.models import Label
from app.modules.labels.repository import LabelRepository
from app.modules.labels.schemas import LabelCreate, LabelUpdate
from app.modules.teams.service import TeamService


def _name_taken(name: str) -> ApiError:
    return ApiError(409, "label_name_taken", "Метка с таким названием уже есть", {"name": name})


class LabelService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._labels = LabelRepository(session)

    async def list_for_team(self, ctx: AccessContext) -> Sequence[Label]:
        """Метки, применимые к задачам команды: её собственные и общие для workspace."""
        return await self._labels.list_for(ctx.workspace_id, [ctx.team])

    async def list_visible(self, ctx: AccessContext) -> Sequence[Label]:
        """Метки workspace и всех видимых пользователю команд."""
        teams = await TeamService(self._session).list_visible(ctx)
        return await self._labels.list_for(ctx.workspace_id, [team.id for team in teams])

    async def create(self, ctx: AccessContext, data: LabelCreate) -> Label:
        if await self._labels.name_taken(ctx.workspace_id, data.team_id, data.name):
            raise _name_taken(data.name)
        try:
            label = await self._labels.add(
                Label(
                    workspace_id=ctx.workspace_id,
                    team_id=data.team_id,
                    name=data.name,
                    color=data.color,
                )
            )
        except IntegrityError as error:
            await self._session.rollback()
            raise _name_taken(data.name) from error
        await self._session.commit()
        return label

    async def get(self, ctx: AccessContext, label_id: UUID) -> Label:
        label = await self._labels.get_in_workspace(label_id, ctx.workspace_id)
        if label is None:
            raise ApiError(404, "label_not_found", "Метка не найдена")
        return label

    async def update(self, ctx: AccessContext, label_id: UUID, data: LabelUpdate) -> Label:
        label = await self.get(ctx, label_id)
        changes = data.model_dump(exclude_unset=True)
        name = changes.get("name")
        if name is not None and await self._labels.name_taken(
            label.workspace_id, label.team_id, name, exclude=label.id
        ):
            raise _name_taken(name)
        for field, value in changes.items():
            setattr(label, field, value)
        try:
            await self._session.commit()
        except IntegrityError as error:
            await self._session.rollback()
            raise _name_taken(str(name)) from error
        return label

    async def delete(self, ctx: AccessContext, label_id: UUID) -> None:
        label = await self.get(ctx, label_id)
        await self._labels.delete(label.id, label.workspace_id)
        await self._session.commit()

    # --- Для задач ------------------------------------------------------------

    async def get_many(self, label_ids: Collection[UUID], workspace_id: UUID) -> Sequence[Label]:
        return await self._labels.get_many(label_ids, workspace_id)

    async def labels_by_task(self, task_ids: Collection[UUID]) -> dict[UUID, list[Label]]:
        grouped: dict[UUID, list[Label]] = defaultdict(list)
        for task_id, label in await self._labels.labels_of_tasks(task_ids):
            grouped[task_id].append(label)
        return grouped

    async def replace_for_task(
        self, *, workspace_id: UUID, team_id: UUID, task_id: UUID, label_ids: Collection[UUID]
    ) -> tuple[list[Label], list[Label]]:
        """Заменить набор меток задачи; вернуть (добавленные, снятые). Без commit.

        Метка применима, если она общая для workspace или принадлежит команде задачи.
        """
        wanted = set(label_ids)
        found = {label.id: label for label in await self._labels.get_many(wanted, workspace_id)}
        unusable = [
            str(label_id)
            for label_id in sorted(wanted)
            if label_id not in found or found[label_id].team_id not in (None, team_id)
        ]
        if unusable:
            raise ApiError(
                400,
                "label_not_applicable",
                "Метка не найдена или принадлежит другой команде",
                {"label_ids": unusable},
            )

        current = {
            label.id: label for label in (await self.labels_by_task([task_id])).get(task_id, [])
        }
        added = [found[label_id] for label_id in sorted(wanted - current.keys())]
        removed = [current[label_id] for label_id in sorted(current.keys() - wanted)]
        await self._labels.detach(task_id, [label.id for label in removed])
        await self._labels.attach(workspace_id, task_id, [label.id for label in added])
        return added, removed
