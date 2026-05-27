import structlog

from warden.domain.models.action_result import ActionResult
from warden.domain.models.decision import Action, Decision
from warden.domain.models.event import Event
from warden.domain.ports.notifier import NotificationClient
from warden.domain.ports.orchestrator import OrchestratorClient

log = structlog.get_logger(__name__)


class ActionExecutorService:
    def __init__(
        self,
        orchestrator: OrchestratorClient,
        notifier: NotificationClient,
    ) -> None:
        self._orchestrator = orchestrator
        self._notifier = notifier
        self._handlers = {
            Action.ROLLBACK: self._rollback,
            Action.RESTART: self._restart,
            Action.SCALE_UP: self._scale_up,
            Action.NOTIFY_HUMAN: self._notify_human,
            Action.NO_ACTION: self._no_action,
        }

    async def execute(self, event: Event, decision: Decision) -> ActionResult:
        log.info(
            "action_executing",
            event_id=str(event.id),
            action=decision.action.value,
            correlation_id=str(event.correlation_id),
        )
        try:
            result = await self._handlers[decision.action](event, decision)
        except Exception as e:
            log.error(
                "action_failed",
                event_id=str(event.id),
                action=decision.action.value,
                error=str(e),
                correlation_id=str(event.correlation_id),
            )
            result = ActionResult(success=False, message=str(e))

        log.info(
            "action_executed",
            event_id=str(event.id),
            action=decision.action.value,
            outcome="success" if result.success else "failed",
            correlation_id=str(event.correlation_id),
        )
        return result

    async def _rollback(self, event: Event, _: Decision) -> ActionResult:
        return await self._orchestrator.rollback(event.project_id, event.environment_id)

    async def _restart(self, event: Event, _: Decision) -> ActionResult:
        return await self._orchestrator.restart(event.project_id, event.environment_id)

    async def _scale_up(self, event: Event, _: Decision) -> ActionResult:
        return await self._orchestrator.scale_up(event.project_id, event.environment_id)

    async def _notify_human(self, event: Event, decision: Decision) -> ActionResult:
        await self._notifier.notify_oncall(event, decision)
        return ActionResult(success=True, message="on-call notified")

    async def _no_action(self, event: Event, _: Decision) -> ActionResult:
        return ActionResult(success=True, message="no action required")
