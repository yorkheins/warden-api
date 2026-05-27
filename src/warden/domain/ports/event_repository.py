from abc import ABC, abstractmethod
from uuid import UUID

from warden.domain.models.event import Event, EventStatus


class EventRepository(ABC):
    @abstractmethod
    async def save(self, event: Event) -> Event: ...

    @abstractmethod
    async def find_by_id(self, event_id: UUID) -> Event | None: ...

    @abstractmethod
    async def find_all(self) -> list[Event]: ...

    @abstractmethod
    async def find_by_dedup_key(self, key: str) -> Event | None: ...

    @abstractmethod
    async def update_status(self, event_id: UUID, status: EventStatus) -> None: ...
