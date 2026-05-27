import structlog
import httpx

from warden.domain.models.decision import Decision
from warden.domain.models.event import Event
from warden.domain.ports.notifier import NotificationClient
from warden.infrastructure.config import Settings

log = structlog.get_logger(__name__)


class HttpNotifierClient(NotificationClient):
    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self._client = client
        self._base_url = settings.NOTIFIER_MOCK_URL

    async def notify_oncall(self, event: Event, decision: Decision) -> None:
        url = f"{self._base_url}/notify/oncall"
        payload = {
            "event_id": str(event.id),
            "project_id": event.project_id,
            "environment_id": event.environment_id,
            "severity": event.severity.value,
            "signal": event.signal,
            "action": decision.action.value,
            "reasoning": decision.reasoning,
            "correlation_id": str(event.correlation_id),
        }
        try:
            response = await self._client.post(url, json=payload)
            response.raise_for_status()
            log.info(
                "oncall_notified",
                event_id=str(event.id),
                correlation_id=str(event.correlation_id),
            )
        except httpx.HTTPStatusError as e:
            log.error("notifier_error", status=e.response.status_code, event_id=str(event.id))
        except httpx.RequestError as e:
            log.error("notifier_unreachable", error=str(e), event_id=str(event.id))
