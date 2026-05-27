from abc import ABC, abstractmethod

from warden.domain.models.decision import LLMRawDecision
from warden.domain.models.event import Event
from warden.domain.models.workload_history import WorkloadHistoryEntry


class LLMClient(ABC):
    @abstractmethod
    async def reason(
        self, event: Event, history: list[WorkloadHistoryEntry]
    ) -> LLMRawDecision: ...
