from datetime import datetime, timezone
from uuid import UUID

import structlog

from warden.domain.models.approval import ApprovalRequest, ApprovalStatus
from warden.domain.models.action_result import ActionResult
from warden.domain.models.workload_history import OutcomeStatus
from warden.domain.ports.approval_repository import ApprovalRepository
from warden.domain.ports.decision_repository import DecisionRepository
from warden.domain.ports.event_repository import EventRepository
from warden.domain.ports.history_repository import HistoryRepository
from warden.domain.services.action_executor import ActionExecutorService
from warden.infrastructure.exceptions import ApprovalAlreadyResolvedError, ApprovalNotFoundError

log = structlog.get_logger(__name__)


class ApprovalService:
    def __init__(
        self,
        approval_repo: ApprovalRepository,
        history_repo: HistoryRepository,
        executor: ActionExecutorService,
        event_repo: EventRepository,
        decision_repo: DecisionRepository,
    ) -> None:
        self._approval_repo = approval_repo
        self._history_repo = history_repo
        self._executor = executor
        self._event_repo = event_repo
        self._decision_repo = decision_repo

    async def approve(
        self, approval_id: UUID, resolved_by: str | None, comment: str | None
    ) -> ActionResult:
        approval, event, decision = await self._load_and_validate(approval_id)

        result = await self._executor.execute(event, decision)
        outcome = OutcomeStatus.APPROVED_BY_HUMAN if result.success else OutcomeStatus.FAILED

        approval.status = ApprovalStatus.APPROVED
        approval.human_comment = comment
        approval.resolved_by = resolved_by
        approval.resolved_at = datetime.now(timezone.utc)
        await self._approval_repo.update(approval)
        await self._history_repo.update_outcome(event.id, outcome, comment or "approved")

        log.info(
            "approval_resolved",
            approval_id=str(approval_id),
            resolution="approved",
            resolved_by=resolved_by,
            correlation_id=str(event.correlation_id),
        )
        return result

    async def reject(
        self, approval_id: UUID, resolved_by: str | None, comment: str | None
    ) -> None:
        approval, event, _ = await self._load_and_validate(approval_id)

        approval.status = ApprovalStatus.REJECTED
        approval.human_comment = comment
        approval.resolved_by = resolved_by
        approval.resolved_at = datetime.now(timezone.utc)
        await self._approval_repo.update(approval)
        await self._history_repo.update_outcome(
            event.id, OutcomeStatus.REJECTED_BY_HUMAN, comment or "rejected"
        )

        log.info(
            "approval_resolved",
            approval_id=str(approval_id),
            resolution="rejected",
            resolved_by=resolved_by,
            correlation_id=str(event.correlation_id),
        )

    async def _load_and_validate(
        self, approval_id: UUID
    ) -> tuple[ApprovalRequest, object, object]:
        approval = await self._approval_repo.find_by_id(approval_id)
        if not approval:
            raise ApprovalNotFoundError(f"Approval {approval_id} not found")
        if approval.status != ApprovalStatus.PENDING:
            raise ApprovalAlreadyResolvedError(
                f"Approval {approval_id} already {approval.status.value}"
            )
        event = await self._event_repo.find_by_id(approval.event_id)
        decision = await self._decision_repo.find_by_event_id(approval.event_id)
        return approval, event, decision
