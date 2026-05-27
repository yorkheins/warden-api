import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from warden.adapters.outbound.notifier.http_notifier import HttpNotifierClient
from warden.adapters.outbound.orchestrator.http_orchestrator import HttpOrchestratorClient
from warden.domain.models.decision import Action, Decision, ExecutionStatus
from warden.infrastructure.config import Settings
from tests.fixtures.events import make_event


def make_settings() -> Settings:
    return Settings(
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        USE_MOCK_LLM=True,
        ORCHESTRATOR_MOCK_URL="http://mock-orchestrator:8001",
        NOTIFIER_MOCK_URL="http://mock-notifier:8002",
    )


def make_decision(action: Action = Action.RESTART) -> Decision:
    return Decision(
        id=uuid.uuid4(),
        event_id=uuid.uuid4(),
        action=action,
        confidence=0.85,
        reasoning="test reasoning",
        safe_to_auto=True,
        restrictions_applied=[],
        llm_raw_output={},
        execution_status=ExecutionStatus.PENDING_APPROVAL,
        created_at=datetime.now(timezone.utc),
    )


def mock_http_client(status_code: int = 200, json_body: dict | None = None) -> AsyncMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_body or {"success": True, "message": "ok"}
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=response
        )
    else:
        response.raise_for_status = MagicMock()
    client = AsyncMock()
    client.post.return_value = response
    return client


# --- HttpOrchestratorClient ---

async def test_orchestrator_rollback_calls_correct_endpoint():
    client = mock_http_client()
    orch = HttpOrchestratorClient(client, make_settings())
    result = await orch.rollback("checkout", "prod")
    client.post.assert_called_once_with(
        "http://mock-orchestrator:8001/rollback",
        json={"project_id": "checkout", "environment_id": "prod"},
    )
    assert result.success is True


async def test_orchestrator_restart_calls_correct_endpoint():
    client = mock_http_client()
    orch = HttpOrchestratorClient(client, make_settings())
    result = await orch.restart("api-gateway", "staging")
    client.post.assert_called_once_with(
        "http://mock-orchestrator:8001/restart",
        json={"project_id": "api-gateway", "environment_id": "staging"},
    )
    assert result.success is True


async def test_orchestrator_scale_up_calls_correct_endpoint():
    client = mock_http_client()
    orch = HttpOrchestratorClient(client, make_settings())
    result = await orch.scale_up("payments", "prod")
    client.post.assert_called_once_with(
        "http://mock-orchestrator:8001/scale",
        json={"project_id": "payments", "environment_id": "prod"},
    )
    assert result.success is True


async def test_orchestrator_http_500_returns_failed_result():
    client = mock_http_client(status_code=500)
    orch = HttpOrchestratorClient(client, make_settings())
    result = await orch.rollback("checkout", "prod")
    assert result.success is False
    assert "500" in result.message


async def test_orchestrator_connection_error_returns_failed_result():
    http_client = AsyncMock()
    http_client.post.side_effect = httpx.RequestError("connection refused")
    orch = HttpOrchestratorClient(http_client, make_settings())
    result = await orch.restart("checkout", "dev")
    assert result.success is False
    assert result.message == "connection refused"


# --- HttpNotifierClient ---

async def test_notifier_oncall_calls_correct_endpoint():
    client = mock_http_client()
    notifier = HttpNotifierClient(client, make_settings())
    event = make_event(project_id="payments", environment_id="prod")
    decision = make_decision(action=Action.ROLLBACK)
    await notifier.notify_oncall(event, decision)
    client.post.assert_called_once()
    call_args = client.post.call_args
    assert call_args[0][0] == "http://mock-notifier:8002/notify/oncall"
    payload = call_args[1]["json"]
    assert payload["project_id"] == "payments"
    assert payload["environment_id"] == "prod"
    assert payload["action"] == "rollback"


async def test_notifier_http_500_does_not_raise():
    client = mock_http_client(status_code=500)
    notifier = HttpNotifierClient(client, make_settings())
    await notifier.notify_oncall(make_event(), make_decision())


async def test_notifier_connection_error_does_not_raise():
    http_client = AsyncMock()
    http_client.post.side_effect = httpx.RequestError("unreachable")
    notifier = HttpNotifierClient(http_client, make_settings())
    await notifier.notify_oncall(make_event(), make_decision())
