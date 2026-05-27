from abc import ABC, abstractmethod

from warden.domain.models.action_result import ActionResult


class OrchestratorClient(ABC):
    @abstractmethod
    async def rollback(self, project_id: str, environment_id: str) -> ActionResult: ...

    @abstractmethod
    async def restart(self, project_id: str, environment_id: str) -> ActionResult: ...

    @abstractmethod
    async def scale_up(self, project_id: str, environment_id: str) -> ActionResult: ...
