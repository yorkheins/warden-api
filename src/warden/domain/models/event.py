import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EventStatus(str, Enum):
    RECEIVED = "received"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


@dataclass
class Event:
    id: UUID
    project_id: str
    environment_id: str
    severity: Severity
    signal: str
    context: dict
    timestamp: datetime
    correlation_id: UUID
    status: EventStatus
    created_at: datetime

    @property
    def workload_key(self) -> str:
        return f"{self.project_id}:{self.environment_id}"

    @property
    def dedup_key(self) -> str:
        raw = f"{self.project_id}:{self.environment_id}:{self.signal}:{self.timestamp.isoformat()}"
        return hashlib.sha256(raw.encode()).hexdigest()
