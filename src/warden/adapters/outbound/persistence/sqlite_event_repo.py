from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from warden.adapters.outbound.persistence.models import EventORM
from warden.domain.models.event import Event, EventStatus, Severity
from warden.domain.ports.event_repository import EventRepository


class SQLiteEventRepository(EventRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, event: Event) -> Event:
        self._session.add(self._to_orm(event))
        await self._session.flush()
        return event

    async def find_by_id(self, event_id: UUID) -> Event | None:
        row = await self._session.get(EventORM, str(event_id))
        return self._to_domain(row) if row else None

    async def find_all(self) -> list[Event]:
        result = await self._session.execute(
            select(EventORM).order_by(EventORM.created_at.desc())
        )
        return [self._to_domain(row) for row in result.scalars()]

    async def find_by_dedup_key(self, key: str) -> Event | None:
        result = await self._session.execute(
            select(EventORM).where(EventORM.dedup_key == key)
        )
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    async def update_status(self, event_id: UUID, status: EventStatus) -> None:
        row = await self._session.get(EventORM, str(event_id))
        if row:
            row.status = status.value
            await self._session.flush()

    def _to_orm(self, event: Event) -> EventORM:
        return EventORM(
            id=str(event.id),
            project_id=event.project_id,
            environment_id=event.environment_id,
            severity=event.severity.value,
            signal=event.signal,
            context=event.context,
            timestamp=event.timestamp,
            correlation_id=str(event.correlation_id),
            dedup_key=event.dedup_key,
            status=event.status.value,
            created_at=event.created_at,
        )

    def _to_domain(self, row: EventORM) -> Event:
        return Event(
            id=UUID(row.id),
            project_id=row.project_id,
            environment_id=row.environment_id,
            severity=Severity(row.severity),
            signal=row.signal,
            context=row.context,
            timestamp=row.timestamp,
            correlation_id=UUID(row.correlation_id),
            status=EventStatus(row.status),
            created_at=row.created_at,
        )
