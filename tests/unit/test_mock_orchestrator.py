import pytest
import httpx

import mocks.orchestrator.main as orch_module
from mocks.orchestrator.main import app


@pytest.fixture(autouse=True)
def zero_latency_no_errors(monkeypatch):
    monkeypatch.setattr(orch_module, "ERROR_RATE", 0.0)
    monkeypatch.setattr(orch_module, "LATENCY_MIN", 0)
    monkeypatch.setattr(orch_module, "LATENCY_MAX", 0)


@pytest.fixture
def client():
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "mock-orchestrator"}


async def test_rollback_success(client):
    response = await client.post(
        "/rollback", json={"project_id": "checkout", "environment_id": "prod"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["project_id"] == "checkout"
    assert data["environment_id"] == "prod"


async def test_restart_success(client):
    response = await client.post(
        "/restart", json={"project_id": "api-gateway", "environment_id": "staging"}
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


async def test_scale_success(client):
    response = await client.post(
        "/scale", json={"project_id": "payments", "environment_id": "prod"}
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


async def test_error_rate_100_returns_500(client, monkeypatch):
    monkeypatch.setattr(orch_module, "ERROR_RATE", 1.0)
    response = await client.post(
        "/rollback", json={"project_id": "checkout", "environment_id": "prod"}
    )
    assert response.status_code == 500
    assert response.json()["success"] is False
