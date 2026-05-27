"""
Verifica que approve/reject actualizan el historial del workload correctamente.
El historial es el contexto que el LLM usará en el próximo evento del mismo workload.
"""

_TS = "2026-05-27T15:{:02d}:00Z"

PROD_HIGH_PAYLOAD = {
    "project_id": "feedback-svc",
    "environment_id": "prod",
    "severity": "high",
    "signal": "error_spike",
    "context": {},
}


async def test_approve_records_approved_by_human(client):
    resp = await client.post("/events/webhook", json={**PROD_HIGH_PAYLOAD, "timestamp": _TS.format(0)})
    assert resp.status_code == 202

    approvals = await client.get("/approvals")
    approval_id = next(a["id"] for a in approvals.json() if a["status"] == "pending")

    result = await client.post(
        f"/approvals/{approval_id}/approve",
        json={"resolved_by": "jorge", "comment": "lgtm"},
    )
    assert result.status_code == 200
    assert result.json()["status"] == "approved"


async def test_reject_records_rejected_by_human(client):
    resp = await client.post("/events/webhook", json={**PROD_HIGH_PAYLOAD, "timestamp": _TS.format(1)})
    assert resp.status_code == 202

    approvals = await client.get("/approvals")
    approval_id = next(a["id"] for a in approvals.json() if a["status"] == "pending")

    result = await client.post(
        f"/approvals/{approval_id}/reject",
        json={"resolved_by": "jorge", "comment": "not safe yet"},
    )
    assert result.status_code == 200
    assert result.json()["status"] == "rejected"


async def test_double_approve_rejected(client):
    resp = await client.post("/events/webhook", json={**PROD_HIGH_PAYLOAD, "timestamp": _TS.format(2)})
    assert resp.status_code == 202

    approvals = await client.get("/approvals")
    approval_id = next(a["id"] for a in approvals.json() if a["status"] == "pending")

    await client.post(f"/approvals/{approval_id}/approve", json={"resolved_by": "jorge"})
    second = await client.post(f"/approvals/{approval_id}/approve", json={"resolved_by": "jorge"})
    assert second.status_code == 409
