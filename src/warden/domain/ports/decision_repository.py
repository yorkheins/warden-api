from abc import ABC, abstractmethod
from uuid import UUID

from warden.domain.models.decision import Decision


class DecisionRepository(ABC):
    @abstractmethod
    async def save(self, decision: Decision) -> Decision: ...

    @abstractmethod
    async def find_by_event_id(self, event_id: UUID) -> Decision | None: ...
