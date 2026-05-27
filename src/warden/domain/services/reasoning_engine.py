import uuid
from datetime import datetime, timezone

import structlog

from warden.domain.models.decision import Action, Decision, ExecutionStatus, LLMRawDecision
from warden.domain.models.event import Event, Severity
from warden.domain.ports.history_repository import HistoryRepository
from warden.domain.ports.llm_client import LLMClient
from warden.infrastructure.config import Settings
from warden.infrastructure.exceptions import LLMResponseMalformedError, LLMUnavailableError

log = structlog.get_logger(__name__)

_FALLBACK = LLMRawDecision(
    action=Action.NOTIFY_HUMAN,
    confidence=0.0,
    reasoning="LLM unavailable. Escalating to human.",
    safe_to_auto=False,
)

_INJECTION_FALLBACK = LLMRawDecision(
    action=Action.NOTIFY_HUMAN,
    confidence=0.0,
    reasoning="Suspicious input detected in event payload. Escalating to human.",
    safe_to_auto=False,
)

_INJECTION_PATTERNS = [
    "ignore previous",
    "ignore instructions",
    "override",
    "disable approval",
    "bypass",
    "execute immediately",
    "skip approval",
    "forget instructions",
]

_PROD_RESTRICTED_ACTIONS = {Action.ROLLBACK, Action.SCALE_UP}
_HIGH_INCIDENT_THRESHOLD = 3


class ReasoningEngineService:
    def __init__(
        self,
        llm: LLMClient,
        history_repo: HistoryRepository,
        settings: Settings,
    ) -> None:
        self._llm = llm
        self._history_repo = history_repo
        self._settings = settings

    async def decide(self, event: Event) -> Decision:
        history = await self._history_repo.find_by_workload(
            event.project_id,
            event.environment_id,
            self._settings.WORKLOAD_HISTORY_LIMIT,
        )
        log.info(
            "llm_invoked",
            event_id=str(event.id),
            model=self._settings.LLM_MODEL,
            history_entries_count=len(history),
            correlation_id=str(event.correlation_id),
        )
        if self._detect_prompt_injection(event):
            log.warning(
                "prompt_injection_detected",
                event_id=str(event.id),
                signal=event.signal,
                correlation_id=str(event.correlation_id),
            )
            raw = _INJECTION_FALLBACK
        else:
            raw = await self._reason_with_fallback(event, history)
        return self._apply_restrictions(event, raw, history)

    async def _reason_with_fallback(self, event: Event, history: list) -> LLMRawDecision:
        try:
            raw = await self._llm.reason(event, history)
            log.info(
                "llm_decision",
                event_id=str(event.id),
                action=raw.action.value,
                confidence=raw.confidence,
                safe_to_auto_llm=raw.safe_to_auto,
                correlation_id=str(event.correlation_id),
            )
            return raw
        except (LLMUnavailableError, LLMResponseMalformedError) as e:
            log.warning(
                "llm_fallback",
                event_id=str(event.id),
                error=str(e),
                correlation_id=str(event.correlation_id),
            )
            return _FALLBACK

    def _detect_prompt_injection(self, event: Event) -> bool:
        text = event.signal.lower()
        for value in event.context.values():
            if isinstance(value, str):
                text += " " + value.lower()
        return any(pattern in text for pattern in _INJECTION_PATTERNS)

    def _apply_restrictions(self, event: Event, raw: LLMRawDecision, history: list | None = None) -> Decision:
        history = history or []
        safe_to_auto = raw.safe_to_auto
        restrictions: list[str] = []

        if event.severity == Severity.CRITICAL:
            safe_to_auto = False
            restrictions.append("R1:critical_severity")
            log.info(
                "restriction_applied",
                event_id=str(event.id),
                restriction="R1",
                original_safe_to_auto=raw.safe_to_auto,
                final_safe_to_auto=False,
                correlation_id=str(event.correlation_id),
            )

        if raw.confidence < 0.7:
            safe_to_auto = False
            restrictions.append(f"R2:low_confidence({raw.confidence:.2f})")
            log.info(
                "restriction_applied",
                event_id=str(event.id),
                restriction="R2",
                original_safe_to_auto=raw.safe_to_auto,
                final_safe_to_auto=False,
                correlation_id=str(event.correlation_id),
            )

        if (
            event.environment_id in self._settings.PRODUCTION_ENVIRONMENTS
            and raw.action in _PROD_RESTRICTED_ACTIONS
        ):
            safe_to_auto = False
            restrictions.append(f"R3:prod_env+{raw.action.value}")
            log.info(
                "restriction_applied",
                event_id=str(event.id),
                restriction="R3",
                original_safe_to_auto=raw.safe_to_auto,
                final_safe_to_auto=False,
                correlation_id=str(event.correlation_id),
            )

        if len(history) >= _HIGH_INCIDENT_THRESHOLD:
            safe_to_auto = False
            restrictions.append(f"R4:high_incident_frequency({len(history)})")
            log.info(
                "restriction_applied",
                event_id=str(event.id),
                restriction="R4",
                incident_count=len(history),
                original_safe_to_auto=raw.safe_to_auto,
                final_safe_to_auto=False,
                correlation_id=str(event.correlation_id),
            )

        return Decision(
            id=uuid.uuid4(),
            event_id=event.id,
            action=raw.action,
            confidence=raw.confidence,
            reasoning=raw.reasoning,
            safe_to_auto=safe_to_auto,
            restrictions_applied=restrictions,
            llm_raw_output={
                "action": raw.action.value,
                "confidence": raw.confidence,
                "reasoning": raw.reasoning,
                "safe_to_auto": raw.safe_to_auto,
            },
            execution_status=ExecutionStatus.PENDING_APPROVAL,
            created_at=datetime.now(timezone.utc),
        )
