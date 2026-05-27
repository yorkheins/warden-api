#!/usr/bin/env python3
"""
demo_learning.py — Demuestra que Warden aprende de la historia de incidentes.

Fase 1 — R4 (Acumulación de incidentes):
  Envía 4 eventos al mismo proyecto/entorno staging con severidad medium.
  Los primeros son auto-ejecutados. Al 4to, Warden activa R4 y fuerza aprobación.

Fase 2 — Feedback loop:
  Envía un evento en prod → el humano lo rechaza con feedback estructurado →
  envía señal similar. El LLM incorpora el feedback en su razonamiento.
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone

import httpx

BASE_URL = "http://localhost:8000"
POLL_INTERVAL = 1.0  
POLL_TIMEOUT  = 30.0  

# ── ANSI ──────────────────────────────────────────────────────────────────────
G    = "\033[92m"
Y    = "\033[93m"
R    = "\033[91m"
B    = "\033[94m"
C    = "\033[96m"
BOLD = "\033[1m"
DIM  = "\033[2m"
RST  = "\033[0m"

W = 64

def banner(text: str) -> None:
    print(f"\n{BOLD}{C}{'═' * W}{RST}")
    print(f"{BOLD}{C}  {text}{RST}")
    print(f"{BOLD}{C}{'═' * W}{RST}\n")

def step(label: str, text: str) -> None:
    print(f"\n{BOLD}{B}[{label}]{RST} {text}")

def ok(text: str)        -> None: print(f"  {G}✓{RST} {text}")
def warn(text: str)      -> None: print(f"  {Y}⚠{RST} {text}")
def info(text: str)      -> None: print(f"  {C}→{RST} {text}")
def highlight(text: str) -> None: print(f"  {BOLD}{Y}★{RST} {text}")

def ts(offset_minutes: int) -> str:
    dt = datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Helpers HTTP ──────────────────────────────────────────────────────────────

async def send_event(client: httpx.AsyncClient, payload: dict) -> str | None:
    resp = await client.post("/events/webhook/stream", json=payload)
    if resp.status_code == 202:
        return resp.json().get("event_id")
    if resp.status_code == 409:
        warn(f"Evento duplicado: {resp.json().get('message')}")
        return None
    warn(f"Error {resp.status_code}: {resp.text}")
    return None


async def wait_for_decision(client: httpx.AsyncClient, event_id: str) -> dict | None:
    elapsed = 0.0
    print(f"  {DIM}Esperando decisión", end="", flush=True)
    while elapsed < POLL_TIMEOUT:
        await asyncio.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        print(".", end="", flush=True)
        resp = await client.get(f"/events/{event_id}")
        if resp.status_code == 200:
            data = resp.json()
            if data.get("decision"):
                print(f" listo!{RST}")
                return data
    print(f" timeout{RST}")
    return None


async def get_pending_approvals(client: httpx.AsyncClient) -> list:
    resp = await client.get("/approvals")
    return resp.json() if resp.status_code == 200 else []


async def find_approval_for_event(client: httpx.AsyncClient, event_id: str) -> dict | None:
    for a in await get_pending_approvals(client):
        if a.get("event_id") == event_id:
            return a
    return None


async def reject_approval(
    client: httpx.AsyncClient,
    approval_id: str,
    feedback_reason: str,
    alternative_action: str,
) -> bool:
    resp = await client.post(
        f"/approvals/{approval_id}/reject",
        json={
            "resolved_by": "demo-script",
            "comment": "Rechazado en demo de aprendizaje",
            "feedback_reason": feedback_reason,
            "alternative_action": alternative_action,
        },
    )
    return resp.status_code == 200


def show_decision(data: dict) -> None:
    d = data.get("decision", {})
    action       = d.get("action", "—")
    confidence   = d.get("confidence", 0)
    safe         = d.get("safe_to_auto", False)
    restrictions = d.get("restrictions_applied", [])
    reasoning    = d.get("reasoning", "—")

    info(f"Acción         : {BOLD}{action}{RST}")
    info(f"Confianza      : {confidence:.0%}")
    info(f"Auto-ejecutable: {'Sí' if safe else f'{Y}No (requiere aprobación humana){RST}'}")

    if restrictions:
        for r in restrictions:
            color = R if "R4" in r or "R_INJECTION" in r else Y
            info(f"Restricción    : {color}{r}{RST}")
    else:
        info("Restricciones  : ninguna")

    # Mostrar primeras 2 líneas del reasoning
    lines = [ln.strip() for ln in reasoning.splitlines() if ln.strip()][:2]
    for ln in lines:
        info(f"{DIM}Razonamiento   : {ln}{RST}")


# ──────────────────────────────────────────────────────────────────────────────
# FASE 1 — R4: Acumulación de incidentes
# ──────────────────────────────────────────────────────────────────────────────

async def phase1_r4(client: httpx.AsyncClient) -> None:
    banner("FASE 1 — Acumulación de incidentes (R4)")
    print(
        f"Proyecto: {BOLD}catalog-api{RST} / Entorno: {BOLD}staging{RST} / Severidad: {BOLD}medium{RST}\n\n"
        f"Los primeros eventos se auto-ejecutan (staging no es producción).\n"
        f"Al 4to evento, el historial acumula {BOLD}≥ 3 incidentes{RST} y Warden activa\n"
        f"{BOLD}{Y}R4: high_incident_frequency{RST} → fuerza aprobación humana.\n"
    )

    project     = "catalog-api"
    environment = "staging"

    events = [
        (
            "error_rate above 8% for 5 minutes",
            {"error_rate": "8.2%", "last_deploy": "v3.1.0", "duration_min": "5"},
        ),
        (
            "P95 latency degraded to 2.1s on /search",
            {"latency_p95": "2.1s", "baseline_p95": "0.4s", "endpoint": "/search"},
        ),
        (
            "database query timeout on /product-detail",
            {"timeout_ms": "5000", "query": "SELECT * FROM products WHERE id=?", "db_host": "pg-staging"},
        ),
        (
            "memory usage at 88%, GC pressure increasing",
            {"memory_used": "880MB", "memory_limit": "1GB", "gc_pause_ms": "420", "uptime_hours": "96"},
        ),
    ]

    for i, (signal, ctx) in enumerate(events, start=1):
        step(f"{i}/4", f'"{signal}"')

        payload = {
            "project_id": project,
            "environment_id": environment,
            "severity": "medium",
            "signal": signal,
            "context": ctx,
            "timestamp": ts(i * 3),
        }

        eid = await send_event(client, payload)
        if not eid:
            continue
        ok(f"event_id: {eid}")

        data = await wait_for_decision(client, eid)
        if not data:
            warn("No se obtuvo decisión a tiempo")
            continue

        show_decision(data)

        restrictions = data.get("decision", {}).get("restrictions_applied", [])
        if any("R4" in r for r in restrictions):
            highlight("¡R4 ACTIVO! Historia acumulada ≥ 3 → el humano debe aprobar esta acción")

    print()


# ──────────────────────────────────────────────────────────────────────────────
# FASE 2 — Feedback loop
# ──────────────────────────────────────────────────────────────────────────────

async def phase2_feedback(client: httpx.AsyncClient) -> None:
    banner("FASE 2 — Ciclo de feedback (Warden aprende del humano)")
    print(
        f"Proyecto: {BOLD}auth-service{RST} / Entorno: {BOLD}prod{RST}\n\n"
        f"Evento 1 → el humano {BOLD}rechaza{RST} con {Y}feedback_reason{RST} y {Y}alternative_action{RST}.\n"
        f"Evento 2 (señal similar) → el LLM recibe el historial con ese feedback\n"
        f"y lo incorpora en su razonamiento.\n"
    )

    project     = "auth-service"
    environment = "prod"

    # ── Evento 1 ─────────────────────────────────────────────────────────────
    step("1/5", "Enviando evento — login degradado tras deploy v5.0.0")
    payload1 = {
        "project_id": project,
        "environment_id": environment,
        "severity": "high",
        "signal": "Login success rate dropped to 65% after deploy v5.0.0",
        "context": {
            "deploy_version": "v5.0.0",
            "previous_stable": "v4.9.2",
            "success_rate": "65%",
            "rollback_available": "true",
            "error": "OAuth token validation failing — RSA key mismatch",
            "alert": "AUTH_SUCCESS_RATE_LOW",
        },
        "timestamp": ts(20),
    }

    eid1 = await send_event(client, payload1)
    if not eid1:
        return
    ok(f"event_id: {eid1}")

    data1 = await wait_for_decision(client, eid1)
    if not data1:
        warn("No se obtuvo decisión")
        return

    step("2/5", "Decisión del LLM (sin historial previo de este servicio)")
    show_decision(data1)

    # ── Buscar approval ───────────────────────────────────────────────────────
    step("3/5", "Buscando approval pendiente para el evento...")
    await asyncio.sleep(0.5)
    approval = await find_approval_for_event(client, eid1)
    if not approval:
        pending = await get_pending_approvals(client)
        approval = pending[0] if pending else None

    if not approval:
        warn(
            "No se generó approval (el LLM eligió una acción auto-ejecutable).\n"
            "  Para garantizar un approval en el demo asegúrate de que prod esté\n"
            "  en PRODUCTION_ENVIRONMENTS o que la decisión sea un rollback."
        )
        return

    approval_id = approval["id"]
    ok(f"Approval encontrado — id: {approval_id} — status: {approval['status']}")

    # ── Rechazar con feedback ─────────────────────────────────────────────────
    step("4/5", "Humano rechaza con feedback estructurado")

    feedback_reason    = "rollback_too_risky_without_traffic_drain"
    alternative_action = "redirect_10pct_traffic_to_v4.9.2_canary_and_monitor_5min"

    info(f"feedback_reason   : {Y}{feedback_reason}{RST}")
    info(f"alternative_action: {Y}{alternative_action}{RST}")

    rejected = await reject_approval(
        client, approval_id,
        feedback_reason=feedback_reason,
        alternative_action=alternative_action,
    )
    if rejected:
        ok("Rechazo registrado en workload_history.")
        highlight("El LLM verá este feedback la próxima vez que procese un evento de auth-service/prod")
    else:
        warn("No se pudo rechazar el approval")
        return

    await asyncio.sleep(1)

    # ── Evento 2 ──────────────────────────────────────────────────────────────
    step("5/5", "Enviando señal similar — mismo servicio, mismo entorno")
    payload2 = {
        "project_id": project,
        "environment_id": environment,
        "severity": "high",
        "signal": "Login success rate at 58% after deploy v5.0.1, same OAuth error pattern",
        "context": {
            "deploy_version": "v5.0.1",
            "previous_stable": "v4.9.2",
            "success_rate": "58%",
            "rollback_available": "true",
            "error": "OAuth token validation failing — RSA key mismatch (persists after v5.0.1)",
            "alert": "AUTH_SUCCESS_RATE_LOW",
            "previous_incident_id": eid1,
        },
        "timestamp": ts(35),
    }

    eid2 = await send_event(client, payload2)
    if not eid2:
        return
    ok(f"event_id: {eid2}")

    data2 = await wait_for_decision(client, eid2)
    if not data2:
        warn("No se obtuvo decisión")
        return

    print(f"\n  {BOLD}Decisión del LLM (con historial que incluye el feedback humano):{RST}")
    show_decision(data2)

    reasoning2 = data2.get("decision", {}).get("reasoning", "")
    keywords = ["previous", "history", "rejected", "feedback", "canary", "traffic", "drain", "alternative"]
    found = [k for k in keywords if k.lower() in reasoning2.lower()]

    if found:
        highlight(f"El LLM incorporó el historial — menciona: {', '.join(found)}")
    else:
        highlight("Historial enviado al LLM. Revisa el reasoning completo en:")

    info(f"GET {BASE_URL}/events/{eid2}")
    print()


# ──────────────────────────────────────────────────────────────────────────────
async def main() -> None:
    print(f"\n{BOLD}{'━' * W}")
    print(f"  Warden Learning Demo")
    print(f"  Target : {BASE_URL}")
    print(f"{'━' * W}{RST}\n")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60.0) as client:
        try:
            resp = await client.get("/health")
            if resp.status_code != 200:
                print(f"{R}✗ Warden no disponible en {BASE_URL}{RST}")
                sys.exit(1)
            ok(f"Warden disponible — {resp.json()}")
        except Exception as e:
            print(f"{R}✗ No se puede conectar a {BASE_URL}: {e}{RST}")
            sys.exit(1)

        await phase1_r4(client)
        await phase2_feedback(client)

    banner("Demo completado ✓")
    print(f"  {G}✓{RST} Fase 1 : R4 (alta frecuencia de incidentes)")
    print(f"  {G}✓{RST} Fase 2 : Feedback loop (LLM aprende del rechazo humano)")
    print(f"\n  {C}GET {BASE_URL}/events{RST}    → todos los eventos procesados")
    print(f"  {C}GET {BASE_URL}/approvals{RST} → approvals pendientes\n")


if __name__ == "__main__":
    asyncio.run(main())
