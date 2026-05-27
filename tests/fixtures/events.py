import uuid
from datetime import datetime, timezone

from warden.domain.models.event import Event, EventStatus, Severity


def make_event(
    project_id: str = "test-service",
    environment_id: str = "dev",
    severity: Severity = Severity.MEDIUM,
    signal: str = "high_error_rate",
    context: dict | None = None,
    timestamp: datetime | None = None,
) -> Event:
    return Event(
        id=uuid.uuid4(),
        project_id=project_id,
        environment_id=environment_id,
        severity=severity,
        signal=signal,
        context=context or {"error_rate": 0.5},
        timestamp=timestamp or datetime.now(timezone.utc),
        correlation_id=uuid.uuid4(),
        status=EventStatus.RECEIVED,
        created_at=datetime.now(timezone.utc),
    )
