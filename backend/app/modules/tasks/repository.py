"""Запросы к tasks и task_relations."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    Select,
    and_,
    delete,
    exists,
    func,
    literal,
    literal_column,
    or_,
    select,
    tuple_,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.enums import RelationType, StateType, ViewGroupBy
from app.modules.labels.models import TaskLabel
from app.modules.states.models import WorkflowState
from app.modules.tasks.models import Task, TaskRelation, search_document
from app.modules.tasks.ordering import SortSpec, group_expression


@dataclass(frozen=True)
class TaskFilters:
    """Фильтры списка: внутри поля — OR, между полями — AND."""

    team_ids: Collection[UUID] = ()
    project_ids: Collection[UUID] = ()
    state_ids: Collection[UUID] = ()
    state_types: Collection[StateType] = ()
    assignee_ids: Collection[UUID] = ()
    # `assignee_id=none` — задачи без исполнителя; сочетается с id через OR.
    unassigned: bool = False
    creator_ids: Collection[UUID] = ()
    label_ids: Collection[UUID] = ()
    priorities: Collection[int] = ()
    parent_ids: Collection[UUID] = ()
    due_before: date | None = None
    due_after: date | None = None
    query: str | None = None
    deleted: bool = False
    extra: list[ColumnElement[bool]] = field(default_factory=list)


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, task: Task) -> Task:
        self._session.add(task)
        await self._session.flush()
        return task

    async def get_in_workspace(self, task_id: UUID, workspace_id: UUID) -> Task | None:
        task: Task | None = await self._session.scalar(
            select(Task).where(Task.id == task_id, Task.workspace_id == workspace_id)
        )
        return task

    async def get_many(self, task_ids: Collection[UUID], workspace_id: UUID) -> Sequence[Task]:
        if not task_ids:
            return []
        stmt = select(Task).where(Task.id.in_(task_ids), Task.workspace_id == workspace_id)
        return (await self._session.scalars(stmt)).all()

    # --- Список -----------------------------------------------------------------

    async def page(
        self,
        workspace_id: UUID,
        visibility: ColumnElement[bool],
        filters: TaskFilters,
        *,
        after: tuple[str, UUID] | None,
        limit: int,
    ) -> Sequence[Task]:
        """Курсорная страница по `(sort_order, id)`: вставка перед курсором не даёт
        ни дублей, ни пропусков — следующая страница начинается строго после него."""
        stmt = (
            select(Task)
            .where(Task.workspace_id == workspace_id, visibility, *_conditions(filters))
            .order_by(Task.sort_order, Task.id)
            .limit(limit + 1)
        )
        if after is not None:
            stmt = stmt.where(tuple_(Task.sort_order, Task.id) > tuple_(*map(literal, after)))
        return (await self._session.scalars(stmt)).all()

    # --- Выполнение view ------------------------------------------------------------

    def _view_base(
        self,
        workspace_id: UUID,
        conditions: Sequence[ColumnElement[bool]],
        group_by: ViewGroupBy | None,
    ) -> Select[Any]:
        stmt: Select[Any] = select(Task).where(
            Task.workspace_id == workspace_id, Task.deleted_at.is_(None), *conditions
        )
        if group_by == ViewGroupBy.LABEL:
            # Строка на каждую метку: задача с двумя метками — в двух группах.
            stmt = stmt.outerjoin(TaskLabel, TaskLabel.task_id == Task.id)
        return stmt

    async def view_count(
        self, workspace_id: UUID, conditions: Sequence[ColumnElement[bool]]
    ) -> int:
        stmt = self._view_base(workspace_id, conditions, None).with_only_columns(func.count())
        return int(await self._session.scalar(stmt) or 0)

    async def view_group_counts(
        self,
        workspace_id: UUID,
        conditions: Sequence[ColumnElement[bool]],
        group_by: ViewGroupBy,
    ) -> list[tuple[Any, int]]:
        key = group_expression(group_by)
        stmt = (
            self._view_base(workspace_id, conditions, group_by)
            .with_only_columns(key, func.count(func.distinct(Task.id)))
            .group_by(key)
        )
        return [(row[0], row[1]) for row in await self._session.execute(stmt)]

    async def view_page(
        self,
        workspace_id: UUID,
        conditions: Sequence[ColumnElement[bool]],
        sort: SortSpec,
        *,
        group_by: ViewGroupBy | None,
        only_group: tuple[Any] | None,
        after: tuple[Any, UUID] | None,
        limit: int,
    ) -> list[tuple[Task, Any]]:
        """Задачи с ключом группы, по `limit + 1` на группу.

        Все группы сразу — одной выборкой с `row_number() OVER (PARTITION BY …)`; одна
        группа (`only_group`) — обычная страница с курсором внутри неё.
        """
        base = self._view_base(workspace_id, conditions, group_by)
        key = group_expression(group_by) if group_by else literal(None)
        if only_group is not None or group_by is None:
            stmt = base.add_columns(key.label("group_key"))
            if only_group is not None:
                (value,) = only_group
                stmt = stmt.where(key.is_(None) if value is None else key == value)
            if after is not None:
                stmt = stmt.where(sort.after(after))
            stmt = stmt.order_by(*sort.order_by()).limit(limit + 1)
            return [(row[0], row[1]) for row in (await self._session.execute(stmt)).all()]

        ranked = base.add_columns(
            key.label("group_key"),
            func.row_number().over(partition_by=key, order_by=sort.order_by()).label("position"),
        ).subquery()
        task = aliased(Task, ranked)
        stmt = (
            select(task, ranked.c.group_key)
            .where(ranked.c.position <= limit + 1)
            .order_by(ranked.c.position)
        )
        return [(row[0], row[1]) for row in (await self._session.execute(stmt)).all()]

    async def children(
        self, parent_id: UUID, workspace_id: UUID, visibility: ColumnElement[bool]
    ) -> Sequence[Task]:
        stmt = (
            select(Task)
            .where(
                Task.parent_id == parent_id,
                Task.workspace_id == workspace_id,
                Task.deleted_at.is_(None),
                visibility,
            )
            .order_by(Task.sort_order, Task.id)
        )
        return (await self._session.scalars(stmt)).all()

    async def visible_ids(
        self, task_ids: Collection[UUID], workspace_id: UUID, visibility: ColumnElement[bool]
    ) -> set[UUID]:
        if not task_ids:
            return set()
        stmt = select(Task.id).where(
            Task.id.in_(task_ids),
            Task.workspace_id == workspace_id,
            Task.deleted_at.is_(None),
            visibility,
        )
        return set(await self._session.scalars(stmt))

    # --- Статусы ----------------------------------------------------------------

    async def count_in_state(self, state_id: UUID) -> int:
        """Считаются и удалённые: внешний ключ на статус держат и они."""
        count = await self._session.scalar(
            select(func.count()).select_from(Task).where(Task.state_id == state_id)
        )
        return count or 0

    async def in_state(self, state_id: UUID) -> Sequence[Task]:
        return (await self._session.scalars(select(Task).where(Task.state_id == state_id))).all()

    # --- Порядок ----------------------------------------------------------------

    async def edge_sort_order(
        self, team_id: UUID, *, last: bool, exclude: UUID | None = None
    ) -> str | None:
        column = func.max(Task.sort_order) if last else func.min(Task.sort_order)
        stmt = select(column).where(Task.team_id == team_id)
        if exclude is not None:
            stmt = stmt.where(Task.id != exclude)
        edge: str | None = await self._session.scalar(stmt)
        return edge

    async def neighbour_sort_order(
        self, team_id: UUID, anchor: Task, *, after: bool, exclude: UUID
    ) -> str | None:
        """Ключ соседа якоря по всей команде — сразу после него или сразу перед ним."""
        position = tuple_(Task.sort_order, Task.id)
        # Параметры, а не текст запроса; коллация сравнения — колонки, то есть "C".
        anchor_position = tuple_(literal(anchor.sort_order), literal(anchor.id))
        stmt: Select[tuple[str]] = select(Task.sort_order).where(
            Task.team_id == team_id, Task.id != exclude
        )
        if after:
            stmt = stmt.where(position > anchor_position).order_by(Task.sort_order, Task.id)
        else:
            stmt = stmt.where(position < anchor_position).order_by(
                Task.sort_order.desc(), Task.id.desc()
            )
        neighbour: str | None = await self._session.scalar(stmt.limit(1))
        return neighbour

    async def team_order(self, team_id: UUID) -> Sequence[Task]:
        stmt = select(Task).where(Task.team_id == team_id).order_by(Task.sort_order, Task.id)
        return (await self._session.scalars(stmt)).all()

    # --- Подзадачи --------------------------------------------------------------

    async def depth(self, task_id: UUID) -> int:
        """Уровень задачи в дереве: корень — 1."""
        chain = (
            select(Task.id, Task.parent_id, literal_column("1").label("level"))
            .where(Task.id == task_id)
            .cte("chain", recursive=True)
        )
        parent = select(Task.id, Task.parent_id, (chain.c.level + 1).label("level")).join(
            chain, Task.id == chain.c.parent_id
        )
        chain = chain.union_all(parent)
        level = await self._session.scalar(select(func.max(chain.c.level)))
        return level or 1

    async def subtree(self, task_id: UUID) -> tuple[set[UUID], int]:
        """Все потомки задачи и высота её поддерева (лист — 1)."""
        tree = (
            select(Task.id, literal_column("1").label("level"))
            .where(Task.id == task_id)
            .cte("tree", recursive=True)
        )
        child = select(Task.id, (tree.c.level + 1).label("level")).join(
            tree, Task.parent_id == tree.c.id
        )
        tree = tree.union_all(child)
        rows = (await self._session.execute(select(tree.c.id, tree.c.level))).all()
        return {row[0] for row in rows} - {task_id}, max(row[1] for row in rows)

    # --- Связи ------------------------------------------------------------------

    async def add_relation(self, relation: TaskRelation) -> TaskRelation:
        self._session.add(relation)
        await self._session.flush()
        return relation

    async def get_relation(self, relation_id: UUID, workspace_id: UUID) -> TaskRelation | None:
        relation: TaskRelation | None = await self._session.scalar(
            select(TaskRelation).where(
                TaskRelation.id == relation_id, TaskRelation.workspace_id == workspace_id
            )
        )
        return relation

    async def delete_relation(self, relation: TaskRelation) -> None:
        await self._session.execute(delete(TaskRelation).where(TaskRelation.id == relation.id))

    async def relation_exists(
        self, source: UUID, target: UUID, kind: RelationType, *, symmetric: bool
    ) -> bool:
        same = and_(TaskRelation.source_task_id == source, TaskRelation.target_task_id == target)
        if symmetric:
            same = or_(
                same,
                and_(TaskRelation.source_task_id == target, TaskRelation.target_task_id == source),
            )
        condition = and_(same, TaskRelation.type == kind)
        return bool(await self._session.scalar(select(exists().where(condition))))

    async def blocks_reachable(self, start: UUID, goal: UUID) -> bool:
        """Есть ли путь `start → … → goal` по связям `blocks`. `WITH RECURSIVE`
        с UNION (не UNION ALL) останавливается и на уже существующих циклах."""
        reach = (
            select(TaskRelation.target_task_id.label("task_id"))
            .where(TaskRelation.source_task_id == start, TaskRelation.type == RelationType.BLOCKS)
            .cte("reach", recursive=True)
        )
        step = select(TaskRelation.target_task_id).join(
            reach,
            and_(
                TaskRelation.source_task_id == reach.c.task_id,
                TaskRelation.type == RelationType.BLOCKS,
            ),
        )
        reach = reach.union(step)
        return bool(await self._session.scalar(select(exists().where(reach.c.task_id == goal))))

    async def relations_of(self, task_id: UUID) -> Sequence[TaskRelation]:
        stmt = (
            select(TaskRelation)
            .where(
                or_(TaskRelation.source_task_id == task_id, TaskRelation.target_task_id == task_id)
            )
            .order_by(TaskRelation.created_at, TaskRelation.id)
        )
        return (await self._session.scalars(stmt)).all()


def _conditions(filters: TaskFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [
        Task.deleted_at.is_not(None) if filters.deleted else Task.deleted_at.is_(None)
    ]
    if filters.team_ids:
        conditions.append(Task.team_id.in_(filters.team_ids))
    if filters.project_ids:
        conditions.append(Task.project_id.in_(filters.project_ids))
    if filters.state_ids:
        conditions.append(Task.state_id.in_(filters.state_ids))
    if filters.state_types:
        conditions.append(
            Task.state_id.in_(
                select(WorkflowState.id).where(WorkflowState.type.in_(filters.state_types))
            )
        )
    if filters.assignee_ids or filters.unassigned:
        options: list[ColumnElement[bool]] = []
        if filters.assignee_ids:
            options.append(Task.assignee_id.in_(filters.assignee_ids))
        if filters.unassigned:
            options.append(Task.assignee_id.is_(None))
        conditions.append(or_(*options))
    if filters.creator_ids:
        conditions.append(Task.creator_id.in_(filters.creator_ids))
    if filters.label_ids:
        # Единственный фильтр через EXISTS: метки лежат в связке task_labels.
        conditions.append(
            exists().where(TaskLabel.task_id == Task.id, TaskLabel.label_id.in_(filters.label_ids))
        )
    if filters.priorities:
        conditions.append(Task.priority.in_(filters.priorities))
    if filters.parent_ids:
        conditions.append(Task.parent_id.in_(filters.parent_ids))
    if filters.due_before is not None:
        conditions.append(Task.due_date <= filters.due_before)
    if filters.due_after is not None:
        conditions.append(Task.due_date >= filters.due_after)
    if filters.query:
        conditions.append(
            search_document().op("@@")(
                func.websearch_to_tsquery(literal_column("'simple'"), filters.query)
            )
        )
    conditions.extend(filters.extra)
    return conditions
