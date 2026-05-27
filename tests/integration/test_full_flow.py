"""
Flujos de extremo a extremo usando MockLLMClient.

MockLLMClient responses:
  CRITICAL → notify_human, 0.5  → R1+R2 → approval required
  HIGH     → rollback,     0.85 → R3 in prod → approval required
  MEDIUM   → restart,      0.75 → no restrictions in dev → auto-execute
  LOW      → no_action,    0.90 → no restrictions → auto-execute
"""

_TS = "2026-05-27T20:{:02d}:00Z"


async def test_auto_execution_medium_dev(client):
    """MEDIUM en dev → restart auto-ejecutado (sin restricciones)."""
    resp = await client.post("/events/webhook", json={
        "project_id": "checkout",
        "environment_id": "dev",
        "severity": "medium",
        "signal": "error_spike",
        "context": {"error_rate": 0.4},
        "timestamp": _TS.format(0),
    })
    assert resp.status_code == 202
    event_id = resp.json()["event_id"]

    detail = await client.get(f"/events/{event_id}")
    assert detail.status_code == 200
    decision = detail.json()["decision"]
    assert decision["action"] == "restart"
    assert decision["restrictions_applied"] == []
    assert decision["execution_status"] in ("executed", "failed")  # falla si orchestrator no está


async def test_approval_required_high_prod(client):
    """HIGH en prod → R3 → pending_approval → approve → resuelto."""
    resp = await client.post("/events/webhook", json={
        "project_id": "payment",
        "environment_id": "prod",
        "severity": "high",
        "signal": "latency_spike",
        "context": {},
        "timestamp": _TS.format(1),
    })
    assert resp.status_code == 202
    event_id = resp.json()["event_id"]

    detail = await client.get(f"/events/{event_id}")
    decision = detail.json()["decision"]
    assert decision["execution_status"] == "pending_approval"
    assert any("R3" in r for r in decision["restrictions_applied"])

    approvals = await client.get("/approvals")
    approval_id = next(a["id"] for a in approvals.json() if a["status"] == "pending")

    approve_resp = await client.post(
        f"/approvals/{approval_id}/approve",
        json={"resolved_by": "jorge", "comment": "approved"},
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"


async def test_idempotency_duplicate_event(client):
    """El mismo evento enviado dos veces → segundo recibe 409."""
    payload = {
        "project_id": "api-gw",
        "environment_id": "dev",
        "severity": "low",
        "signal": "timeout",
        "context": {},
        "timestamp": _TS.format(2),
    }
    first = await client.post("/events/webhook", json=payload)
    assert first.status_code == 202

    second = await client.post("/events/webhook", json=payload)
    assert second.status_code == 409
    body = second.json()
    assert body["message"] == "duplicate event"
    assert body["event_id"] == first.json()["event_id"]


async def test_llm_fallback_produces_notify_human(client, monkeypatch):
    """Cuando el LLM falla → fallback a notify_human con confidence=0.0."""
    from warden.adapters.outbound.llm.mock_llm_client import MockLLMClient
    from warden.infrastructure.exceptions import LLMUnavailableError

    async def broken_reason(self, event, history):
        raise LLMUnavailableError("simulated failure")

    monkeypatch.setattr(MockLLMClient, "reason", broken_reason)

    resp = await client.post("/events/webhook", json={
        "project_id": "broken-svc",
        "environment_id": "dev",
        "severity": "medium",
        "signal": "anomaly",
        "context": {},
        "timestamp": _TS.format(3),
    })
    assert resp.status_code == 202
    event_id = resp.json()["event_id"]

    detail = await client.get(f"/events/{event_id}")
    decision = detail.json()["decision"]
    assert decision["action"] == "notify_human"
    assert decision["confidence"] == 0.0
    assert decision["safe_to_auto"] is False
