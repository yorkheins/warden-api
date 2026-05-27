from abc import ABC, abstractmethod
from uuid import UUID

from warden.domain.models.approval import ApprovalRequest


class ApprovalRepository(ABC):
    @abstractmethod
    async def save(self, approval: ApprovalRequest) -> ApprovalRequest: ...

    @abstractmethod
    async def find_by_id(self, approval_id: UUID) -> ApprovalRequest | None: ...

    @abstractmethod
    async def find_pending(self) -> list[ApprovalRequest]: ...

    @abstractmethod
    async def find_all(self) -> list[ApprovalRequest]: ...

    @abstractmethod
    async def update(self, approval: ApprovalRequest) -> ApprovalRequest: ...
