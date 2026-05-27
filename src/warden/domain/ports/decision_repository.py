from abc import ABC, abstractmethod
from uuid import UUID

from warden.domain.models.decision import Decision, ExecutionStatus


class DecisionRepository(ABC):
    @abstractmethod
    async def save(self, decision: Decision) -> Decision: ...

    @abstractmethod
    async def find_by_event_id(self, event_id: UUID) -> Decision | None: ...

    @abstractmethod
    async def update_execution_status(self, decision_id: UUID, status: ExecutionStatus) -> None: ...
