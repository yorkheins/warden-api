from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID

from warden.domain.models.decision import Action


class OutcomeStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    APPROVED_BY_HUMAN = "approved_by_human"
    REJECTED_BY_HUMAN = "rejected_by_human"
    PENDING = "pending"


@dataclass
class WorkloadHistoryEntry:
    id: UUID
    project_id: str
    environment_id: str
    event_id: UUID
    signal: str
    action_decided: Action
    was_auto: bool
    outcome: OutcomeStatus
    human_feedback: str | None
    created_at: datetime
    feedback_reason: str | None = None
    alternative_action: str | None = None
