import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

import structlog

from warden.domain.models.approval import ApprovalRequest, ApprovalStatus
from warden.domain.models.decision import ExecutionStatus
from warden.domain.models.event import Event, EventStatus
from warden.domain.models.workload_history import OutcomeStatus, WorkloadHistoryEntry
from warden.domain.ports.approval_repository import ApprovalRepository
from warden.domain.ports.decision_repository import DecisionRepository
from warden.domain.ports.event_repository import EventRepository
from warden.domain.ports.history_repository import HistoryRepository
from warden.domain.ports.notifier import NotificationClient
from warden.domain.services.action_executor import ActionExecutorService
from warden.domain.services.reasoning_engine import ReasoningEngineService
from warden.infrastructure.exceptions import DuplicateEventError

log = structlog.get_logger(__name__)


@dataclass
class EventIngestionResult:
    event_id: UUID
    correlation_id: UUID
    status: str


class IngestEventUseCase:
    def __init__(
        self,
        event_repo: EventRepository,
        decision_repo: DecisionRepository,
        approval_repo: ApprovalRepository,
        history_repo: HistoryRepository,
        reasoning: ReasoningEngineService,
        executor: ActionExecutorService,
        notifier: NotificationClient,
    ) -> None:
        self._event_repo = event_repo
        self._decision_repo = decision_repo
        self._approval_repo = approval_repo
        self._history_repo = history_repo
        self._reasoning = reasoning
        self._executor = executor
        self._notifier = notifier

    async def execute(
        self,
        event: Event,
        on_progress: Callable[[dict], Awaitable[None]] | None = None,
    ) -> EventIngestionResult:
        async def emit(data: dict) -> None:
            if on_progress:
                await on_progress(data)

        existing = await self._event_repo.find_by_dedup_key(event.dedup_key)
        if existing:
            raise DuplicateEventError(existing.id)

        structlog.contextvars.bind_contextvars(
            correlation_id=str(event.correlation_id),
            event_id=str(event.id),
        )
        log.info(
            "event_received",
            project_id=event.project_id,
            environment_id=event.environment_id,
            severity=event.severity.value,
        )
        await emit({
            "step": "event_received",
            "project_id": event.project_id,
            "environment_id": event.environment_id,
            "severity": event.severity.value,
        })

        await self._event_repo.save(event)
        await self._event_repo.update_status(event.id, EventStatus.PROCESSING)

        try:
            await emit({"step": "reasoning_started", "workload": event.workload_key})
            decision = await self._reasoning.decide(event)
            await emit({
                "step": "decision_made",
                "action": decision.action.value,
                "confidence": decision.confidence,
                "safe_to_auto": decision.safe_to_auto,
                "restrictions_applied": decision.restrictions_applied,
            })

            if decision.safe_to_auto:
                await emit({"step": "executing", "action": decision.action.value})
                result = await self._executor.execute(event, decision)
                decision.execution_status = (
                    ExecutionStatus.EXECUTED if result.success else ExecutionStatus.FAILED
                )
                await self._decision_repo.save(decision)
                await self._save_history(
                    event, decision,
                    was_auto=True,
                    outcome=OutcomeStatus.SUCCESS if result.success else OutcomeStatus.FAILED,
                )
            else:
                await emit({"step": "approval_required", "action": decision.action.value})
                decision.execution_status = ExecutionStatus.PENDING_APPROVAL
                await self._decision_repo.save(decision)
                await self._handle_approval_required(event, decision, emit)

            await self._event_repo.update_status(event.id, EventStatus.PROCESSED)

        except DuplicateEventError:
            raise
        except Exception as e:
            log.error("event_processing_failed", error=str(e))
            await self._event_repo.update_status(event.id, EventStatus.FAILED)
            raise

        return EventIngestionResult(
            event_id=event.id,
            correlation_id=event.correlation_id,
            status="processed",
        )

    async def _handle_approval_required(self, event: Event, decision, emit) -> None:
        approval = ApprovalRequest(
            id=uuid.uuid4(),
            event_id=event.id,
            decision_id=decision.id,
            status=ApprovalStatus.PENDING,
            human_comment=None,
            resolved_by=None,
            resolved_at=None,
            created_at=datetime.now(timezone.utc),
        )
        await self._approval_repo.save(approval)
        log.info("approval_created", approval_id=str(approval.id))
        await emit({"step": "approval_created", "approval_id": str(approval.id)})

        await self._notifier.notify_oncall(event, decision)
        await emit({"step": "oncall_notified"})

        await self._save_history(
            event, decision, was_auto=False, outcome=OutcomeStatus.PENDING
        )

    async def _save_history(self, event: Event, decision, was_auto: bool, outcome: OutcomeStatus) -> None:
        await self._history_repo.save(
            WorkloadHistoryEntry(
                id=uuid.uuid4(),
                project_id=event.project_id,
                environment_id=event.environment_id,
                event_id=event.id,
                signal=event.signal,
                action_decided=decision.action,
                was_auto=was_auto,
                outcome=outcome,
                human_feedback=None,
                created_at=datetime.now(timezone.utc),
            )
        )
