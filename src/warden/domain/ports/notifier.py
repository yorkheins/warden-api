from abc import ABC, abstractmethod

from warden.domain.models.decision import Decision
from warden.domain.models.event import Event


class NotificationClient(ABC):
    @abstractmethod
    async def notify_oncall(self, event: Event, decision: Decision) -> None: ...
