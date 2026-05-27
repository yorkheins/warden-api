import pytest
import httpx

import mocks.notifier.main as notifier_module
from mocks.notifier.main import app, _received


@pytest.fixture(autouse=True)
def zero_latency_no_errors(monkeypatch):
    monkeypatch.setattr(notifier_module, "ERROR_RATE", 0.0)
    monkeypatch.setattr(notifier_module, "LATENCY_MIN", 0)
    monkeypatch.setattr(notifier_module, "LATENCY_MAX", 0)
    _received.clear()


@pytest.fixture
def client():
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "mock-notifier"}


async def test_notify_oncall_success(client):
    payload = {
        "event_id": "abc-123",
        "project_id": "payments",
        "environment_id": "prod",
        "severity": "high",
        "signal": "deployment_regression",
        "action": "rollback",
        "reasoning": "recent deploy correlates with error spike",
        "correlation_id": "corr-456",
    }
    response = await client.post("/notify/oncall", json=payload)
    assert response.status_code == 200
    assert response.json()["success"] is True


async def test_notify_oncall_stores_notification(client):
    payload = {"event_id": "xyz", "project_id": "checkout", "environment_id": "dev",
               "severity": "medium", "signal": "high_cpu", "action": "restart",
               "reasoning": "cpu above threshold", "correlation_id": "corr-1"}
    await client.post("/notify/oncall", json=payload)
    response = await client.get("/notify/received")
    data = response.json()
    assert data["count"] == 1
    assert data["notifications"][0]["project_id"] == "checkout"


async def test_get_received_empty(client):
    response = await client.get("/notify/received")
    assert response.json() == {"count": 0, "notifications": []}


async def test_clear_received(client):
    payload = {"event_id": "1", "project_id": "p", "environment_id": "e",
               "severity": "low", "signal": "s", "action": "restart",
               "reasoning": "r", "correlation_id": "c"}
    await client.post("/notify/oncall", json=payload)
    await client.delete("/notify/received")
    response = await client.get("/notify/received")
    assert response.json()["count"] == 0


async def test_error_rate_100_returns_500(client, monkeypatch):
    monkeypatch.setattr(notifier_module, "ERROR_RATE", 1.0)
    response = await client.post("/notify/oncall", json={"event_id": "x"})
    assert response.status_code == 500
    assert response.json()["success"] is False
