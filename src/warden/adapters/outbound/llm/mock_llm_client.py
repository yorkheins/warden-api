from warden.domain.models.decision import Action, LLMRawDecision
from warden.domain.models.event import Event, Severity
from warden.domain.models.workload_history import WorkloadHistoryEntry
from warden.domain.ports.llm_client import LLMClient

_RESPONSES: dict[Severity, LLMRawDecision] = {
    Severity.CRITICAL: LLMRawDecision(
        action=Action.NOTIFY_HUMAN,
        confidence=0.5,
        reasoning="Critical severity — escalating to human for review.",
        safe_to_auto=False,
    ),
    Severity.HIGH: LLMRawDecision(
        action=Action.ROLLBACK,
        confidence=0.85,
        reasoning="High error rate after recent deploy — rollback recommended.",
        safe_to_auto=True,
    ),
    Severity.MEDIUM: LLMRawDecision(
        action=Action.RESTART,
        confidence=0.75,
        reasoning="Service degraded but recoverable — restart should resolve.",
        safe_to_auto=True,
    ),
    Severity.LOW: LLMRawDecision(
        action=Action.NO_ACTION,
        confidence=0.90,
        reasoning="Minor anomaly — monitoring, no intervention needed.",
        safe_to_auto=True,
    ),
}


class MockLLMClient(LLMClient):
    async def reason(
        self, event: Event, history: list[WorkloadHistoryEntry]
    ) -> LLMRawDecision:
        return _RESPONSES[event.severity]
