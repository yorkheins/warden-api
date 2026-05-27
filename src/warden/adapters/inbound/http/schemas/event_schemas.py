import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from warden.domain.models.decision import Action, Decision, ExecutionStatus
from warden.domain.models.event import Event, EventStatus, Severity


class EventWebhookRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(..., min_length=1)
    environment_id: str = Field(..., min_length=1)
    severity: Severity
    signal: str = Field(..., min_length=1)

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_severity(cls, v: object) -> object:
        return v.lower() if isinstance(v, str) else v
    context: dict[str, Any] = Field(default_factory=dict)
    timestamp: AwareDatetime

    def to_domain(self) -> Event:
        return Event(
            id=uuid.uuid4(),
            project_id=self.project_id,
            environment_id=self.environment_id,
            severity=self.severity,
            signal=self.signal,
            context=self.context,
            timestamp=self.timestamp,
            correlation_id=uuid.uuid4(),
            status=EventStatus.RECEIVED,
            created_at=datetime.now(timezone.utc),
        )


class EventWebhookResponse(BaseModel):
    event_id: UUID
    correlation_id: UUID
    status: str


class EventListItem(BaseModel):
    id: UUID
    project_id: str
    environment_id: str
    severity: Severity
    signal: str
    status: EventStatus
    created_at: datetime

    @classmethod
    def from_domain(cls, event: Event) -> "EventListItem":
        return cls(
            id=event.id,
            project_id=event.project_id,
            environment_id=event.environment_id,
            severity=event.severity,
            signal=event.signal,
            status=event.status,
            created_at=event.created_at,
        )


class DecisionSummary(BaseModel):
    id: UUID
    action: Action
    confidence: float
    reasoning: str
    safe_to_auto: bool
    restrictions_applied: list[str]
    execution_status: ExecutionStatus
    created_at: datetime

    @classmethod
    def from_domain(cls, decision: Decision) -> "DecisionSummary":
        return cls(
            id=decision.id,
            action=decision.action,
            confidence=decision.confidence,
            reasoning=decision.reasoning,
            safe_to_auto=decision.safe_to_auto,
            restrictions_applied=decision.restrictions_applied,
            execution_status=decision.execution_status,
            created_at=decision.created_at,
        )


class EventDetailResponse(BaseModel):
    event: EventListItem
    decision: DecisionSummary | None

    @classmethod
    def from_domain(cls, event: Event, decision: Decision | None) -> "EventDetailResponse":
        return cls(
            event=EventListItem.from_domain(event),
            decision=DecisionSummary.from_domain(decision) if decision else None,
        )
