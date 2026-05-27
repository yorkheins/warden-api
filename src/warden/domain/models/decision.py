from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID


class Action(str, Enum):
    ROLLBACK = "rollback"
    RESTART = "restart"
    SCALE_UP = "scale_up"
    NOTIFY_HUMAN = "notify_human"
    NO_ACTION = "no_action"


class ExecutionStatus(str, Enum):
    EXECUTED = "executed"
    PENDING_APPROVAL = "pending_approval"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class LLMRawDecision:
    action: Action
    confidence: float
    reasoning: str
    safe_to_auto: bool


@dataclass
class Decision:
    id: UUID
    event_id: UUID
    action: Action
    confidence: float
    reasoning: str
    safe_to_auto: bool
    restrictions_applied: list[str]
    llm_raw_output: dict
    execution_status: ExecutionStatus
    created_at: datetime
