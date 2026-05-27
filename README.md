# Warden

Agente autónomo de remediación embebido en una Internal Developer Platform (IDP). Recibe señales de degradación de servicios, consulta un LLM para razonar sobre la acción más adecuada, aplica restricciones de negocio y ejecuta o escala la acción según el nivel de confianza.

---

## Arquitectura

```
HTTP (observabilidad)
        │
        ▼
┌─────────────────────────────────────────────────┐
│                   Warden API                    │
│                                                 │
│  Inbound       Domain            Outbound       │
│  ─────────     ──────────────    ────────────── │
│  /events  ──►  IngestEvent   ──► LLM (OpenAI)  │
│  /approvals    ReasoningEngine ► Orchestrator   │
│  /health       ApprovalService ► Notifier       │
│                                                 │
│  Persistence: SQLite (SQLAlchemy async)         │
└─────────────────────────────────────────────────┘
```

**Patrón:** Hexagonal Architecture (Ports & Adapters). El dominio no importa adaptadores ni infraestructura.

### Restricciones de negocio

Aplicadas en `ReasoningEngineService` **después** de recibir la respuesta del LLM, nunca en el prompt.

| Regla | Condición | Efecto |
|---|---|---|
| R1 | `severity == critical` | `safe_to_auto = false` en cualquier entorno |
| R2 | `confidence < 0.7` | `safe_to_auto = false` |
| R3 | `env ∈ PRODUCTION_ENVIRONMENTS` y acción es `rollback` o `scale_up` | `safe_to_auto = false` |
| R4 | El workload acumula ≥ 3 incidentes en el historial reciente | `safe_to_auto = false` |
| R_INJECTION | El payload contiene keywords de inyección de prompt | `confidence = 0.0` → activa R2 automáticamente; el LLM **no es consultado** |

Cuando `safe_to_auto = false` la decisión queda en `pending_approval` y se notifica al equipo on-call.  
Si se disparan múltiples reglas, todas quedan registradas en `restrictions_applied`.

### Idempotencia

Cada evento genera un `dedup_key = SHA-256(project_id:environment_id:signal:timestamp)`. Si el key ya existe, el sistema retorna 409 con el `event_id` original.

### Feedback loop (Warden aprende)

El historial de decisiones y el feedback humano (`approve`/`reject` con `feedback_reason` + `alternative_action`) se incluyen como contexto en cada llamada al LLM para el mismo workload. Con el tiempo Warden incorpora el criterio del equipo en su razonamiento.

### SQLite — soporte de alta escritura

En producción (DB en archivo) el engine se configura con:

- `pool_size=1, max_overflow=0` — un solo escritor evita contención de locks
- `PRAGMA journal_mode=WAL` — lecturas concurrentes sin bloquear escrituras
- `PRAGMA busy_timeout=5000` — reintenta hasta 5 s antes de fallar
- `PRAGMA synchronous=NORMAL` — equilibrio entre durabilidad y rendimiento

En tests (`:memory:`) se usa `StaticPool` sin esos parámetros.

---

## Requisitos

- Python 3.12
- Docker y Docker Compose
- OpenAI API key (o usar `USE_MOCK_LLM=true`)

---

## Inicio rápido

### Local

```bash
# 1. Crear entorno virtual e instalar dependencias
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 2. Crear .env
echo "OPENAI_API_KEY=sk-..." > .env

# 3. Levantar los servicios mock en terminales separadas
.venv/bin/uvicorn mocks.orchestrator.main:app --port 8001
.venv/bin/uvicorn mocks.notifier.main:app --port 8002

# 4. Levantar Warden
.venv/bin/uvicorn warden.main:app --reload --port 8000
```

Swagger UI disponible en `http://localhost:8000/docs`.

### Docker Compose

```bash
# Con OpenAI real
OPENAI_API_KEY=sk-... docker compose up --build

# Sin API key (mock LLM)
USE_MOCK_LLM=true docker compose up --build
```

Los mocks arrancan primero (healthcheck). Warden espera a que estén listos.

> **Nota — cambios de esquema**: SQLAlchemy usa `create_all` que no altera tablas existentes. Si el esquema cambió desde la última vez que levantaste el servicio, destruye el volumen antes de relanzar:
> ```bash
> docker compose down -v
> docker compose up --build
> ```

---

## API

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/health` | Estado del servicio |
| `POST` | `/events/webhook` | Ingestar evento (202 inmediato) |
| `POST` | `/events/webhook/stream` | Ingestar evento con progreso en tiempo real (SSE) |
| `GET` | `/events` | Listar todos los eventos procesados |
| `GET` | `/events/:id` | Detalle de evento con decisión del LLM |
| `GET` | `/approvals` | Listar approval requests **pendientes** |
| `GET` | `/approvals/:id` | Detalle de un approval por ID (cualquier estado) |
| `POST` | `/approvals/:id/approve` | Aprobar y ejecutar acción |
| `POST` | `/approvals/:id/reject` | Rechazar acción pendiente |

### Ejemplo de evento

```bash
curl -X POST http://localhost:8000/events/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "checkout-service",
    "environment_id": "prod",
    "severity": "high",
    "signal": "deployment_regression",
    "context": {"error_rate": "0.75", "recent_deploy": "true", "version": "v8.1.0"},
    "timestamp": "2026-05-27T10:00:00Z"
  }'
```

- `severity`: `low`, `medium`, `high`, `critical` (case-insensitive)
- `context`: objeto JSON libre — acepta cualquier clave/valor; es extensible por diseño

### Endpoint streaming (SSE)

```bash
curl -N -X POST http://localhost:8000/events/webhook/stream \
  -H "Content-Type: application/json" \
  -d '{...}'
```

Retorna Server-Sent Events paso a paso:

```
data: {"step": "event_received", "project_id": "...", "severity": "high"}
data: {"step": "reasoning_started", "workload": "..."}
data: {"step": "decision_made", "action": "rollback", "confidence": 0.88, "safe_to_auto": false, "restrictions_applied": ["R3:prod_env+rollback"]}
data: {"step": "approval_required", "action": "rollback"}
data: {"step": "approval_created", "approval_id": "..."}
data: {"step": "oncall_notified"}
data: {"step": "done", "event_id": "...", "status": "processed"}
```

### Rechazar con feedback estructurado

```bash
curl -X POST http://localhost:8000/approvals/{id}/reject \
  -H "Content-Type: application/json" \
  -d '{
    "resolved_by": "plataforma-team",
    "comment": "Rollback no es viable en este momento",
    "feedback_reason": "rollback_risky_due_to_partial_db_migration",
    "alternative_action": "apply_hotfix_and_redeploy_v3.0.1"
  }'
```

El feedback queda en `workload_history` y el LLM lo recibe en el siguiente evento del mismo workload.

---

## Tests

### Unitarios e integración

```bash
# Correr todos (unit + integration)
pytest tests/ -v

# Solo unitarios
pytest tests/unit/ -v

# Solo integración
pytest tests/integration/ -v

# Con cobertura
pytest tests/ --cov=warden --cov-report=term-missing
```

No requieren servicios externos — usan SQLite in-memory y `MockLLMClient`.

### Suite E2E

Valida el sistema completo contra el servicio corriendo en Docker.  
Dominio de prueba: plataforma de analítica, data engineering y observabilidad.

```bash
# 1. Levantar el servicio
docker compose down -v && docker compose up --build

# 2. En otra terminal
pytest tests/e2e/ -v
```

Los tests se **saltan automáticamente** si el servicio no está disponible (no fallan).

| Test E2E | Qué valida |
|---|---|
| `test_e2e_health` | `GET /health` retorna `{"status": "ok"}` |
| `test_e2e_auto_execute_non_prod` | Entorno dev + severity low → auto-ejecución posible |
| `test_e2e_r1_critical_severity_any_env` | R1: critical bloquea en cualquier entorno |
| `test_e2e_r2_injection_gives_zero_confidence` | R_INJECTION en context → `confidence=0.0` → R2 |
| `test_e2e_r3_rollback_blocked_in_prod` | R3: rollback en prod → `safe_to_auto=false` |
| `test_e2e_r3_scale_up_blocked_in_prod` | R3: scale_up en prod → `safe_to_auto=false` |
| `test_e2e_r_injection_in_signal_field` | R_INJECTION en campo `signal` → `confidence=0.0` |
| `test_e2e_r4_high_incident_frequency` | 4 eventos al mismo workload → R4 se activa en el 4to |
| `test_e2e_feedback_loop_persists_in_history` | Rechazo con feedback → estado `rejected` + reasoning en evento B |
| `test_e2e_list_approvals_returns_only_pending` | `GET /approvals` retorna solo `status=pending` |
| `test_e2e_get_approval_by_id_any_status` | `GET /approvals/{id}` retorna approval aprobado (no 404) |
| `test_e2e_get_event_with_decision` | `GET /events/{id}` retorna decisión con `reasoning` |
| `test_e2e_list_events_includes_processed` | `GET /events` retorna lista no vacía |
| `test_e2e_duplicate_event_rejected` | Mismo payload dos veces → segundo recibe `code=duplicate` |

### Cobertura de tests unitarios

| Suite | Qué valida |
|---|---|
| `test_restrictions` | R1, R2, R3, R4 y sus condiciones límite (boundary 0.70) |
| `test_payload_validation` | Contrato HTTP, severity case-insensitive, timestamp con timezone |
| `test_reasoning_engine` | Fallback LLM ante error, decisión sin historial |
| `test_feedback_loop` | Approve/reject actualizan historial, doble-aprobación 409 |
| `test_full_flow` | Auto-ejecución, flujo de aprobación, idempotencia, fallback E2E |

### Demo interactivo

Ejecuta todos los escenarios en secuencia con output con colores en la terminal:

```bash
# Requiere el servicio corriendo
python scripts/demo_learning.py
```

Cubre: auto-ejecución, R1, R3 (rollback + scale_up), R_INJECTION+R2, R4 (4 eventos acumulados) y el feedback loop completo.

---

## Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| `OPENAI_API_KEY` | `""` | API key de OpenAI |
| `LLM_MODEL` | `gpt-4o-mini` | Modelo a usar |
| `USE_MOCK_LLM` | `false` | Usar mock en lugar de OpenAI |
| `APP_ENV` | `development` | `production` activa logs en JSON |
| `DATABASE_URL` | `sqlite+aiosqlite:///./warden.db` | URL de la base de datos |
| `PRODUCTION_ENVIRONMENTS` | `["prod"]` | Entornos que activan R3 |
| `WORKLOAD_HISTORY_LIMIT` | `5` | Entradas de historial enviadas al LLM |
| `ORCHESTRATOR_MOCK_URL` | `http://mock-orchestrator:8001` | URL del orquestador |
| `NOTIFIER_MOCK_URL` | `http://mock-notifier:8002` | URL del notificador |

---

## Decisiones de diseño

- **Hexagonal Architecture**: el dominio es independiente de frameworks, bases de datos y proveedores LLM. Se puede cambiar OpenAI por cualquier otro modelo sin tocar servicios de dominio.
- **Idempotencia por dedup_key**: SHA-256 del contenido del evento. El sistema puede recibir el mismo webhook múltiples veces sin efectos secundarios.
- **Restricciones fuera del prompt**: R1/R2/R3/R4 se aplican en código después de recibir la respuesta del LLM. El prompt le pide al LLM su evaluación técnica honesta; las restricciones de negocio las enforcea el sistema.
- **R_INJECTION antes del LLM**: la detección de keywords de inyección ocurre antes de llamar a OpenAI, evitando que el payload manipulado llegue al modelo.
- **Feedback loop**: el historial de decisiones y el feedback humano se incluyen como contexto en cada llamada al LLM para el mismo workload.
- **CQRS para historial**: `workload_history` es un modelo de lectura desnormalizado. Evita JOINs al consultar contexto para el LLM.
- **Fallback LLM**: ante cualquier error del LLM, la decisión es `notify_human` con `confidence=0.0` y `safe_to_auto=false`. El sistema nunca se queda sin respuesta.
- **`context` extensible**: el campo acepta cualquier objeto JSON; no hay esquema fijo. El LLM recibe el contexto completo como parte del prompt.

---

## Acciones de mejora

Esta entrega asume **red interna de confianza** (típico de un MVP de prueba técnica). Para un despliegue en producción, las mejoras prioritarias serían:

### Seguridad y acceso

| Prioridad | Mejora | Motivo |
|---|---|---|
| Alta | Autenticación y autorización en toda la API (API key, JWT o mTLS) | Hoy cualquier cliente puede ingestar eventos, listar datos y aprobar acciones que ejecutan rollback/restart/scale en el orquestador |
| Alta | Firma HMAC del webhook (`X-Signature` + timestamp, ventana anti-replay) | Sin integridad del payload, un actor en la red puede inyectar eventos falsos |
| Alta | Validar `environment_id` contra el IDP (no confiar solo en el body) | Un emisor malicioso puede enviar `staging` para un workload en `prod` y eludir R3 |
| Media | Roles separados: emisor de webhooks, operador de approvals, solo lectura | Principio de mínimo privilegio en un servicio con impacto en infraestructura |
| Media | Desactivar `/docs` y `/openapi.json` cuando `APP_ENV=production` | Reduce superficie de exposición del contrato interno |
| Baja | No exponer mocks (`8001`, `8002`) fuera de desarrollo; quitar `GET /notify/received` en prod | El mock de notifier acumula payloads con datos operativos sin auth |

### Abuso, datos y LLM

| Prioridad | Mejora | Motivo |
|---|---|---|
| Media | Límite de tamaño en `context` y `max_length` en `project_id` / `signal` | Payloads enormes pueden saturar SQLite, inflar prompts y aumentar coste/latencia de OpenAI |
| Media | Defensas adicionales frente a prompt injection en `context` (delimitación, esquema opcional, truncado) | R_INJECTION detecta keywords conocidos pero no cubre variantes creativas |
| Media | Errores genéricos en SSE (`/events/webhook/stream`); detalle solo en logs | Hoy `str(exception)` puede filtrar detalles internos al cliente |
| Baja | Rate limiting en `POST /events/webhook` | Mitiga spam de eventos y coste de LLM |

### Robustez operativa

| Prioridad | Mejora | Motivo |
|---|---|---|
| Media | Migrar a PostgreSQL para entornos con múltiples réplicas | SQLite WAL soporta alta escritura en un solo proceso, pero no escala horizontalmente |
| Baja | Manejar condición de carrera en dedup (UNIQUE en `dedup_key` → 409, no 500) | Dos webhooks idénticos concurrentes pueden chocar en la restricción única |
| Baja | Rotación y gestión de secretos (`OPENAI_API_KEY`) vía vault o variables del runtime | La key no debe versionarse; conviene política de rotación si hubo exposición |

### Lo que ya está bien

- **SQL injection**: consultas vía SQLAlchemy ORM con parámetros enlazados; no hay SQL dinámico concatenado.
- **Validación HTTP**: Pydantic con `extra="forbid"`, enums y tipos estrictos en la respuesta del LLM.
- **Restricciones de negocio**: R1/R2/R3/R4/R_INJECTION en código de dominio, no delegadas al prompt.
- **Alta escritura SQLite**: WAL mode + busy_timeout + pool de un solo escritor evitan `database is locked`.
