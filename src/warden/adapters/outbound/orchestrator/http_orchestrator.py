import structlog
import httpx

from warden.domain.models.action_result import ActionResult
from warden.domain.ports.orchestrator import OrchestratorClient
from warden.infrastructure.config import Settings

log = structlog.get_logger(__name__)


class HttpOrchestratorClient(OrchestratorClient):
    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self._client = client
        self._base_url = settings.ORCHESTRATOR_MOCK_URL

    async def rollback(self, project_id: str, environment_id: str) -> ActionResult:
        return await self._call("rollback", project_id, environment_id)

    async def restart(self, project_id: str, environment_id: str) -> ActionResult:
        return await self._call("restart", project_id, environment_id)

    async def scale_up(self, project_id: str, environment_id: str) -> ActionResult:
        return await self._call("scale", project_id, environment_id)

    async def _call(self, action: str, project_id: str, environment_id: str) -> ActionResult:
        url = f"{self._base_url}/{action}"
        payload = {"project_id": project_id, "environment_id": environment_id}
        try:
            response = await self._client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return ActionResult(
                success=data.get("success", True),
                message=data.get("message", "ok"),
                details=data,
            )
        except httpx.HTTPStatusError as e:
            log.error("orchestrator_error", action=action, status=e.response.status_code)
            return ActionResult(success=False, message=f"HTTP {e.response.status_code}", details={})
        except httpx.RequestError as e:
            log.error("orchestrator_unreachable", action=action, error=str(e))
            return ActionResult(success=False, message=str(e), details={})
