"""
Tests unitarios directos sobre IngestEventUseCase.
Cubren las ramas internas (emit, safe_to_auto, approval, error) sin pasar por HTTP.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from warden.domain.models.action_result import ActionResult
from warden.domain.models.decision import Action, Decision, ExecutionStatus, LLMRawDecision
from warden.domain.models.workload_history import OutcomeStatus
from warden.domain.services.ingest_event import IngestEventUseCase
from warden.infrastructure.exceptions import DuplicateEventError
from tests.fixtures.events import make_event


def make_decision(action: Action = Action.RESTART, safe_to_auto: bool = True) -> Decision:
    return Decision(
        id=uuid.uuid4(),
        event_id=uuid.uuid4(),
        action=action,
        confidence=0.85,
        reasoning="test reasoning string here",
        safe_to_auto=safe_to_auto,
        restrictions_applied=[],
        llm_raw_output={},
        execution_status=ExecutionStatus.PENDING_APPROVAL,
        created_at=datetime.now(timezone.utc),
    )


def make_use_case(
    safe_to_auto: bool = True,
    executor_success: bool = True,
    is_duplicate: bool = False,
) -> IngestEventUseCase:
    event_repo = AsyncMock()
    event_repo.find_by_dedup_key.return_value = make_event() if is_duplicate else None
    event_repo.save.return_value = None
    event_repo.update_status.return_value = None

    decision = make_decision(safe_to_auto=safe_to_auto)
    reasoning = AsyncMock()
    reasoning.decide.return_value = decision

    executor = AsyncMock()
    executor.execute.return_value = ActionResult(
        success=executor_success,
        message="ok" if executor_success else "error",
    )

    decision_repo = AsyncMock()
    approval_repo = AsyncMock()
    history_repo = AsyncMock()
    notifier = AsyncMock()

    return IngestEventUseCase(
        event_repo=event_repo,
        decision_repo=decision_repo,
        approval_repo=approval_repo,
        history_repo=history_repo,
        reasoning=reasoning,
        executor=executor,
        notifier=notifier,
    )


async def test_execute_auto_success_returns_processed():
    use_case = make_use_case(safe_to_auto=True, executor_success=True)
    result = await use_case.execute(make_event())
    assert result.status == "processed"


async def test_execute_auto_failed_still_returns_processed():
    use_case = make_use_case(safe_to_auto=True, executor_success=False)
    result = await use_case.execute(make_event())
    assert result.status == "processed"


async def test_execute_approval_required_saves_approval():
    use_case = make_use_case(safe_to_auto=False)
    result = await use_case.execute(make_event())
    use_case._approval_repo.save.assert_called_once()
    assert result.status == "processed"


async def test_execute_approval_required_notifies_oncall():
    use_case = make_use_case(safe_to_auto=False)
    await use_case.execute(make_event())
    use_case._notifier.notify_oncall.assert_called_once()


async def test_execute_duplicate_raises_duplicate_error():
    use_case = make_use_case(is_duplicate=True)
    with pytest.raises(DuplicateEventError):
        await use_case.execute(make_event())


async def test_execute_with_on_progress_emits_steps():
    use_case = make_use_case(safe_to_auto=True)
    received = []

    async def capture(data: dict) -> None:
        received.append(data["step"])

    await use_case.execute(make_event(), on_progress=capture)
    assert "event_received" in received
    assert "reasoning_started" in received
    assert "decision_made" in received


async def test_execute_approval_path_emits_approval_steps():
    use_case = make_use_case(safe_to_auto=False)
    received = []

    async def capture(data: dict) -> None:
        received.append(data["step"])

    await use_case.execute(make_event(), on_progress=capture)
    assert "approval_required" in received
    assert "approval_created" in received
    assert "oncall_notified" in received


async def test_execute_reasoning_failure_marks_event_failed():
    use_case = make_use_case()
    use_case._reasoning.decide.side_effect = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        await use_case.execute(make_event())
    use_case._event_repo.update_status.assert_called()
