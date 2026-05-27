"""
Tests unitarios directos sobre ApprovalService.
Cubren las ramas not-found, already-resolved y el flujo completo sin HTTP.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from warden.domain.models.action_result import ActionResult
from warden.domain.models.approval import ApprovalRequest, ApprovalStatus
from warden.domain.models.decision import Action, Decision, ExecutionStatus
from warden.domain.services.approval_service import ApprovalService
from warden.infrastructure.exceptions import ApprovalAlreadyResolvedError, ApprovalNotFoundError
from tests.fixtures.events import make_event


def make_decision() -> Decision:
    return Decision(
        id=uuid.uuid4(),
        event_id=uuid.uuid4(),
        action=Action.ROLLBACK,
        confidence=0.85,
        reasoning="rollback recommended",
        safe_to_auto=False,
        restrictions_applied=["R3:prod_env+rollback"],
        llm_raw_output={},
        execution_status=ExecutionStatus.PENDING_APPROVAL,
        created_at=datetime.now(timezone.utc),
    )


def make_pending_approval(event_id: uuid.UUID, decision_id: uuid.UUID) -> ApprovalRequest:
    return ApprovalRequest(
        id=uuid.uuid4(),
        event_id=event_id,
        decision_id=decision_id,
        status=ApprovalStatus.PENDING,
        human_comment=None,
        resolved_by=None,
        resolved_at=None,
        created_at=datetime.now(timezone.utc),
    )


def make_service(
    approval: ApprovalRequest | None = None,
    executor_success: bool = True,
) -> ApprovalService:
    approval_repo = AsyncMock()
    approval_repo.find_by_id.return_value = approval
    approval_repo.update.return_value = approval

    event = make_event()
    event_repo = AsyncMock()
    event_repo.find_by_id.return_value = event

    decision = make_decision()
    decision_repo = AsyncMock()
    decision_repo.find_by_event_id.return_value = decision
    decision_repo.update_execution_status.return_value = None

    history_repo = AsyncMock()

    executor = AsyncMock()
    executor.execute.return_value = ActionResult(
        success=executor_success,
        message="ok" if executor_success else "failed",
    )

    return ApprovalService(
        approval_repo=approval_repo,
        history_repo=history_repo,
        executor=executor,
        event_repo=event_repo,
        decision_repo=decision_repo,
    )


async def test_approve_not_found_raises():
    service = make_service(approval=None)
    with pytest.raises(ApprovalNotFoundError):
        await service.approve(uuid.uuid4(), "jorge", "lgtm")


async def test_reject_not_found_raises():
    service = make_service(approval=None)
    with pytest.raises(ApprovalNotFoundError):
        await service.reject(uuid.uuid4(), "jorge", "not safe")


async def test_approve_already_resolved_raises():
    event_id = uuid.uuid4()
    decision_id = uuid.uuid4()
    resolved = make_pending_approval(event_id, decision_id)
    resolved.status = ApprovalStatus.APPROVED
    service = make_service(approval=resolved)
    with pytest.raises(ApprovalAlreadyResolvedError):
        await service.approve(resolved.id, "jorge", "lgtm")


async def test_approve_success_calls_executor():
    event_id = uuid.uuid4()
    decision_id = uuid.uuid4()
    approval = make_pending_approval(event_id, decision_id)
    service = make_service(approval=approval, executor_success=True)
    result = await service.approve(approval.id, "jorge", "lgtm")
    assert result.success is True
    service._executor.execute.assert_called_once()


async def test_approve_executor_fails_returns_failed_result():
    event_id = uuid.uuid4()
    decision_id = uuid.uuid4()
    approval = make_pending_approval(event_id, decision_id)
    service = make_service(approval=approval, executor_success=False)
    result = await service.approve(approval.id, "jorge", "proceed anyway")
    assert result.success is False


async def test_reject_success_updates_history():
    event_id = uuid.uuid4()
    decision_id = uuid.uuid4()
    approval = make_pending_approval(event_id, decision_id)
    service = make_service(approval=approval)
    await service.reject(
        approval.id, "jorge", "too risky",
        feedback_reason="peak_hours", alternative_action="scale_up"
    )
    service._history_repo.update_outcome.assert_called_once()
    call_kwargs = service._history_repo.update_outcome.call_args
    assert call_kwargs.args[3] == "peak_hours"
    assert call_kwargs.args[4] == "scale_up"


async def test_reject_updates_approval_status():
    event_id = uuid.uuid4()
    decision_id = uuid.uuid4()
    approval = make_pending_approval(event_id, decision_id)
    service = make_service(approval=approval)
    await service.reject(approval.id, "jorge", "nope")
    service._approval_repo.update.assert_called_once()
    updated = service._approval_repo.update.call_args.args[0]
    assert updated.status == ApprovalStatus.REJECTED
