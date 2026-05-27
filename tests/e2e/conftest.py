"""
Fixtures compartidas para la suite E2E de Warden.
Requiere el servicio corriendo en WARDEN_URL (default: http://localhost:8000).
Si el servicio no está disponible todos los tests de este directorio se saltan.

"""
import json
import os

import httpx
import pytest

BASE_URL = os.getenv("WARDEN_URL", "http://localhost:8000")

_service_available: bool | None = None

def _check_service_sync() -> bool:
    try:
        with httpx.Client(timeout=5.0) as c:
            resp = c.get(f"{BASE_URL}/health")
            return resp.status_code == 200
    except Exception:
        return False


#Fixture de skip automático

@pytest.fixture(autouse=True)
def require_service():
    global _service_available
    if _service_available is None:
        _service_available = _check_service_sync()
    if not _service_available:
        pytest.skip(
            f"Warden no disponible en {BASE_URL}. "
            "Ejecuta 'docker compose up --build' primero."
        )


#HTTP Client

@pytest.fixture
async def client():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=90.0) as c:
        yield c


#  Stream Event

async def stream_event(client: httpx.AsyncClient, payload: dict) -> dict:
    collected: dict = {
        "event_id": None,
        "approval_id": None,
        "decision": None,
        "error": None,
    }
    async with client.stream(
        "POST", "/events/webhook/stream",
        json=payload, timeout=90.0,
    ) as resp:
        assert resp.status_code == 200, f"Stream devolvió {resp.status_code}"
        async for raw in resp.aiter_lines():
            if not raw.startswith("data:"):
                continue
            try:
                data = json.loads(raw[5:].strip())
            except json.JSONDecodeError:
                continue
            step = data.get("step")
            if step == "done":
                collected["event_id"] = data.get("event_id")
            elif step == "approval_created":
                collected["approval_id"] = data.get("approval_id")
            elif step == "decision_made":
                collected["decision"] = data
            elif step == "error":
                collected["error"] = data
    return collected


#Helper cleanup

async def cleanup_approval(client: httpx.AsyncClient, approval_id: str | None) -> None:
    if approval_id:
        await client.post(
            f"/approvals/{approval_id}/approve",
            json={"resolved_by": "e2e-cleanup"},
        )
