from abc import ABC, abstractmethod
from uuid import UUID

from warden.domain.models.workload_history import OutcomeStatus, WorkloadHistoryEntry


class HistoryRepository(ABC):
    @abstractmethod
    async def save(self, entry: WorkloadHistoryEntry) -> WorkloadHistoryEntry: ...

    @abstractmethod
    async def find_by_workload(
        self, project_id: str, environment_id: str, limit: int
    ) -> list[WorkloadHistoryEntry]: ...

    @abstractmethod
    async def update_outcome(
        self,
        event_id: UUID,
        outcome: OutcomeStatus,
        human_feedback: str | None,
        feedback_reason: str | None = None,
        alternative_action: str | None = None,
    ) -> None: ...
