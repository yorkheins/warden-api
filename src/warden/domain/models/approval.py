from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class ApprovalRequest:
    id: UUID
    event_id: UUID
    decision_id: UUID
    status: ApprovalStatus
    human_comment: str | None
    resolved_by: str | None
    resolved_at: datetime | None
    created_at: datetime
