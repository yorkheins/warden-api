import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

_TS = "2026-05-27T22:{:02d}:00Z"

_BASE_PAYLOAD = {
    "project_id": "routes-svc",
    "environment_id": "dev",
    "severity": "medium",
    "signal": "high_error_rate",
    "context": {},
}


#GET /events 

async def test_list_events_empty(client):
    resp = await client.get("/events")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_events_after_ingestion(client):
    await client.post("/events/webhook", json={**_BASE_PAYLOAD, "timestamp": _TS.format(0)})
    resp = await client.get("/events")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


#GET /events/{id} → 404 

async def test_get_event_not_found(client):
    resp = await client.get(f"/events/{uuid.uuid4()}")
    assert resp.status_code == 404


#POST /events/webhook/stream 

async def test_stream_returns_sse_events(client):
    resp = await client.post(
        "/events/webhook/stream",
        json={**_BASE_PAYLOAD, "timestamp": _TS.format(1)},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    lines = [l for l in resp.text.splitlines() if l.startswith("data:")]
    steps = [__import__("json").loads(l[5:])["step"] for l in lines]
    assert "event_received" in steps
    assert "done" in steps


async def test_stream_duplicate_returns_error_step(client):
    payload = {**_BASE_PAYLOAD, "timestamp": _TS.format(2)}
    await client.post("/events/webhook/stream", json=payload)
    resp = await client.post("/events/webhook/stream", json=payload)
    assert resp.status_code == 200
    lines = [l for l in resp.text.splitlines() if l.startswith("data:")]
    steps = [__import__("json").loads(l[5:]) for l in lines]
    error = next(s for s in steps if s["step"] == "error")
    assert error["code"] == "duplicate"


#Approval not found

async def test_approve_nonexistent_returns_404(client):
    resp = await client.post(
        f"/approvals/{uuid.uuid4()}/approve",
        json={"resolved_by": "jorge"},
    )
    assert resp.status_code == 404


async def test_reject_nonexistent_returns_404(client):
    resp = await client.post(
        f"/approvals/{uuid.uuid4()}/reject",
        json={"resolved_by": "jorge"},
    )
    assert resp.status_code == 404


#GET /health

async def test_health_returns_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


#create_app

@pytest_asyncio.fixture
async def main_client(tmp_path, monkeypatch):
    db_url = f"sqlite+aiosqlite:///{tmp_path}/warden_test.db"
    monkeypatch.setenv("USE_MOCK_LLM", "true")
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("NOTIFIER_MOCK_URL", "http://localhost:9999")
    monkeypatch.setenv("ORCHESTRATOR_MOCK_URL", "http://localhost:9998")

    from warden.infrastructure.config import get_settings
    from warden.infrastructure.container import Container
    from warden.infrastructure.database import init_db
    from warden.main import create_app

    get_settings.cache_clear()
    app = create_app()

    settings = get_settings()
    container = Container(settings)
    await init_db(container.engine)
    app.state.container = container

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    await container.close()
    get_settings.cache_clear()


async def test_main_app_health(main_client):
    resp = await main_client.get("/health")
    assert resp.status_code == 200


async def test_main_app_duplicate_event_returns_409(main_client):
    payload = {
        "project_id": "main-svc",
        "environment_id": "dev",
        "severity": "low",
        "signal": "timeout",
        "context": {},
        "timestamp": "2026-05-27T09:00:00Z",
    }
    first = await main_client.post("/events/webhook", json=payload)
    assert first.status_code == 202
    second = await main_client.post("/events/webhook", json=payload)
    assert second.status_code == 409
    assert second.json()["message"] == "duplicate event"


async def test_main_app_event_not_found_returns_404(main_client):
    resp = await main_client.get(f"/events/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_main_app_approval_not_found_returns_404(main_client):
    resp = await main_client.post(
        f"/approvals/{uuid.uuid4()}/approve",
        json={"resolved_by": "jorge"},
    )
    assert resp.status_code == 404
