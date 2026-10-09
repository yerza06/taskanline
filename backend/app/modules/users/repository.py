"""Запросы к таблице `users`. Про HTTP здесь ничего не известно."""

from collections.abc import Collection, Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, literal, or_, select, text, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import InstanceRole
from app.modules.users.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def get_many(self, user_ids: Collection[UUID]) -> Sequence[User]:
        if not user_ids:
            return []
        return (await self._session.scalars(select(User).where(User.id.in_(user_ids)))).all()

    async def get_many_by_email(self, emails: Collection[str]) -> Sequence[User]:
        if not emails:
            return []
        return (await self._session.scalars(select(User).where(User.email.in_(emails)))).all()

    async def get_by_email(self, email: str) -> User | None:
        """Сравнение регистронезависимо: колонка объявлена как CITEXT."""
        user: User | None = await self._session.scalar(select(User).where(User.email == email))
        return user

    async def create(
        self, *, email: str, password_hash: str, full_name: str, role: InstanceRole
    ) -> User:
        user = User(email=email, password_hash=password_hash, full_name=full_name, role=role)
        self._session.add(user)
        await self._session.flush()
        return user

    async def any_user_exists(self) -> bool:
        return bool(await self._session.scalar(select(func.count()).select_from(User)))

    async def lock_bootstrap(self) -> None:
        """Блокировка на время решения «первый ли это пользователь».

        Без неё две одновременные регистрации на пустой базе обе увидят ноль строк
        и обе получат роль superadmin. Блокировка транзакционная — снимается сама.
        """
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext('users_bootstrap'))")
        )

    # --- Для админ-панели ---------------------------------------------------------

    async def search(
        self,
        *,
        query: str | None,
        role: InstanceRole | None,
        status: str | None,
        after: tuple[datetime, UUID] | None,
        limit: int,
    ) -> Sequence[User]:
        """Новые первыми; `status`: active, blocked, deleted."""
        stmt = select(User)
        if query:
            pattern = f"%{query.replace('%', '').replace('_', '')}%"
            stmt = stmt.where(or_(User.email.ilike(pattern), User.full_name.ilike(pattern)))
        if role is not None:
            stmt = stmt.where(User.role == role)
        if status == "deleted":
            stmt = stmt.where(User.deleted_at.is_not(None))
        elif status == "blocked":
            stmt = stmt.where(User.deleted_at.is_(None), User.is_active.is_(False))
        elif status == "active":
            stmt = stmt.where(User.deleted_at.is_(None), User.is_active.is_(True))
        if after is not None:
            stmt = stmt.where(tuple_(User.created_at, User.id) < tuple_(*map(literal, after)))
        stmt = stmt.order_by(User.created_at.desc(), User.id.desc()).limit(limit + 1)
        return (await self._session.scalars(stmt)).all()

    async def status_counts(self) -> dict[str, int]:
        active = and_(User.deleted_at.is_(None), User.is_active.is_(True))
        blocked = and_(User.deleted_at.is_(None), User.is_active.is_(False))
        row = (
            await self._session.execute(
                select(
                    func.count(),
                    func.count().filter(active),
                    func.count().filter(blocked),
                    func.count().filter(User.deleted_at.is_not(None)),
                ).select_from(User)
            )
        ).one()
        return {"total": row[0], "active": row[1], "blocked": row[2], "deleted": row[3]}

    async def active_superadmins_locked(self) -> list[UUID]:
        """Действующие superadmin под `FOR UPDATE` — для инварианта «хотя бы один есть»."""
        stmt = (
            select(User.id)
            .where(
                User.role == InstanceRole.SUPERADMIN,
                User.is_active.is_(True),
                User.deleted_at.is_(None),
            )
            .with_for_update()
        )
        return list((await self._session.scalars(stmt)).all())
