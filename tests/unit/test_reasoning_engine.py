from unittest.mock import AsyncMock

from warden.domain.models.decision import Action, LLMRawDecision
from warden.domain.services.reasoning_engine import ReasoningEngineService
from warden.infrastructure.config import Settings
from warden.infrastructure.exceptions import LLMResponseMalformedError, LLMUnavailableError
from tests.fixtures.events import make_event


def make_engine(llm=None) -> ReasoningEngineService:
    settings = Settings(DATABASE_URL="sqlite+aiosqlite:///:memory:", USE_MOCK_LLM=True)
    history_repo = AsyncMock()
    history_repo.find_by_workload.return_value = []
    return ReasoningEngineService(llm=llm or AsyncMock(), history_repo=history_repo, settings=settings)


async def test_llm_unavailable_returns_notify_human_fallback():
    llm = AsyncMock()
    llm.reason.side_effect = LLMUnavailableError("timeout")
    decision = await make_engine(llm).decide(make_event())
    assert decision.action == Action.NOTIFY_HUMAN
    assert decision.confidence == 0.0
    assert decision.safe_to_auto is False


async def test_llm_malformed_returns_notify_human_fallback():
    llm = AsyncMock()
    llm.reason.side_effect = LLMResponseMalformedError("bad json")
    decision = await make_engine(llm).decide(make_event())
    assert decision.action == Action.NOTIFY_HUMAN
    assert decision.confidence == 0.0


async def test_decide_without_history_still_produces_decision():
    llm = AsyncMock()
    llm.reason.return_value = LLMRawDecision(
        action=Action.RESTART, confidence=0.8, reasoning="restart needed", safe_to_auto=True
    )
    event = make_event()
    decision = await make_engine(llm).decide(event)
    assert decision.action == Action.RESTART
    assert decision.event_id == event.id
    assert decision.restrictions_applied == []
