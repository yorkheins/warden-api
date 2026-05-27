from unittest.mock import AsyncMock

from warden.domain.models.decision import Action, LLMRawDecision
from warden.domain.models.event import Severity
from warden.domain.services.reasoning_engine import ReasoningEngineService
from warden.infrastructure.config import Settings
from tests.fixtures.events import make_event


def make_engine(prod_envs: list[str] | None = None) -> ReasoningEngineService:
    settings = Settings(
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        USE_MOCK_LLM=True,
        PRODUCTION_ENVIRONMENTS=prod_envs or ["prod"],
    )
    return ReasoningEngineService(llm=AsyncMock(), history_repo=AsyncMock(), settings=settings)


def make_raw(
    action: Action = Action.RESTART,
    confidence: float = 0.85,
    safe_to_auto: bool = True,
) -> LLMRawDecision:
    return LLMRawDecision(action=action, confidence=confidence, reasoning="test", safe_to_auto=safe_to_auto)


def test_r1_critical_forces_safe_to_auto_false():
    decision = make_engine()._apply_restrictions(make_event(severity=Severity.CRITICAL), make_raw())
    assert decision.safe_to_auto is False
    assert "R1:critical_severity" in decision.restrictions_applied


def test_r1_not_applied_below_critical():
    decision = make_engine()._apply_restrictions(make_event(severity=Severity.HIGH), make_raw())
    assert not any("R1" in r for r in decision.restrictions_applied)


def test_r2_low_confidence_forces_safe_to_auto_false():
    decision = make_engine()._apply_restrictions(make_event(), make_raw(confidence=0.69))
    assert decision.safe_to_auto is False
    assert any("R2" in r for r in decision.restrictions_applied)


def test_r2_boundary_070_is_safe():
    decision = make_engine()._apply_restrictions(make_event(), make_raw(confidence=0.70))
    assert decision.safe_to_auto is True
    assert not any("R2" in r for r in decision.restrictions_applied)


def test_r3_prod_rollback_requires_approval():
    decision = make_engine()._apply_restrictions(
        make_event(environment_id="prod"), make_raw(action=Action.ROLLBACK)
    )
    assert decision.safe_to_auto is False
    assert any("R3" in r for r in decision.restrictions_applied)


def test_r3_prod_scale_up_requires_approval():
    decision = make_engine()._apply_restrictions(
        make_event(environment_id="prod"), make_raw(action=Action.SCALE_UP)
    )
    assert decision.safe_to_auto is False
    assert any("R3" in r for r in decision.restrictions_applied)


def test_r3_not_applied_in_staging():
    decision = make_engine(prod_envs=["prod"])._apply_restrictions(
        make_event(environment_id="staging"), make_raw(action=Action.ROLLBACK)
    )
    assert decision.safe_to_auto is True
    assert not any("R3" in r for r in decision.restrictions_applied)


def test_r3_restart_in_prod_not_restricted():
    decision = make_engine()._apply_restrictions(
        make_event(environment_id="prod"), make_raw(action=Action.RESTART)
    )
    assert not any("R3" in r for r in decision.restrictions_applied)


def test_all_three_restrictions_stack():
    event = make_event(severity=Severity.CRITICAL, environment_id="prod")
    raw = make_raw(action=Action.ROLLBACK, confidence=0.5, safe_to_auto=True)
    decision = make_engine()._apply_restrictions(event, raw)
    assert decision.safe_to_auto is False
    assert "R1:critical_severity" in decision.restrictions_applied
    assert any("R2" in r for r in decision.restrictions_applied)
    assert any("R3" in r for r in decision.restrictions_applied)
    assert len(decision.restrictions_applied) == 3
