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

### Restricciones de negocio (aplicadas en `ReasoningEngineService`, nunca en el prompt)

| Regla | Condición | Efecto |
|---|---|---|
| R1 | `severity == CRITICAL` | `safe_to_auto = false` |
| R2 | `confidence < 0.7` | `safe_to_auto = false` |
| R3 | `env in PRODUCTION_ENVIRONMENTS` y acción es `rollback` o `scale_up` | `safe_to_auto = false` |

Cuando `safe_to_auto = false`, la decisión queda en `pending_approval` y se notifica al equipo on-call.

### Idempotencia

Cada evento genera un `dedup_key = SHA-256(project_id:environment_id:signal:timestamp)`. Si el key ya existe, el sistema retorna 409 con el `event_id` original.

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

Los mocks arrancan primero (healthcheck). Warden espera a que estén listos antes de iniciar.

---

## API

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/health` | Estado del servicio |
| `POST` | `/events/webhook` | Ingestar evento (202 inmediato) |
| `POST` | `/events/webhook/stream` | Ingestar evento con progreso en tiempo real (SSE) |
| `GET` | `/events` | Listar eventos y su estado |
| `GET` | `/events/:id` | Detalle de evento con decisión del LLM |
| `GET` | `/approvals` | Listar aprobaciones pendientes |
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
    "context": {"error_rate": 0.75, "recent_deploy": true},
    "timestamp": "2026-05-27T10:00:00Z"
  }'
```

El campo `severity` acepta `low`, `medium`, `high`, `critical` (case-insensitive).  
El campo `context` acepta cualquier objeto JSON válido.

### Endpoint streaming

```bash
curl -N -X POST http://localhost:8000/events/webhook/stream \
  -H "Content-Type: application/json" \
  -d '{...}'
```

Retorna Server-Sent Events con el progreso paso a paso antes de la respuesta final:

```
data: {"step": "event_received", ...}
data: {"step": "reasoning_started", ...}
data: {"step": "decision_made", "action": "rollback", "confidence": 0.88, ...}
data: {"step": "approval_required", ...}
data: {"step": "approval_created", "approval_id": "..."}
data: {"step": "oncall_notified"}
data: {"step": "done", "event_id": "...", "status": "processed"}
```

---

## Tests

```bash
# Correr todos los tests
pytest tests/ -v

# Solo unitarios
pytest tests/unit/ -v

# Solo integración
pytest tests/integration/ -v

# Con cobertura
pytest tests/ --cov=warden --cov-report=term-missing
```

### Cobertura de tests

| Suite | Qué valida |
|---|---|
| `test_restrictions` | R1, R2, R3 y sus condiciones límite (boundary 0.70) |
| `test_payload_validation` | Validación del contrato HTTP, severity case-insensitive, timestamp con timezone |
| `test_reasoning_engine` | Fallback LLM ante error, decisión sin historial |
| `test_feedback_loop` | Approve/reject actualizan historial, doble-aprobación 409 |
| `test_full_flow` | Auto-ejecución, flujo de aprobación, idempotencia, fallback E2E |

Los tests usan SQLite in-memory y `MockLLMClient` — no requieren servicios externos.

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
- **Restricciones fuera del prompt**: R1/R2/R3 se aplican en código después de recibir la respuesta del LLM. El prompt le pide al LLM su evaluación técnica honesta; las restricciones de negocio las enforcea el sistema.
- **Feedback loop**: el historial de decisiones y el feedback humano (approve/reject con comentario) se incluyen como contexto en cada llamada al LLM para el mismo workload.
- **CQRS para historial**: `workload_history` es un modelo de lectura desnormalizado. Evita JOINs al consultar contexto para el LLM.
- **Fallback LLM**: ante cualquier error del LLM, la decisión es `notify_human` con `confidence=0.0` y `safe_to_auto=false`. El sistema nunca se queda sin respuesta.

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
| Media | Defensas frente a prompt injection en `context` (delimitación, esquema opcional, truncado) | El contenido del webhook se serializa tal cual al prompt del LLM; R1/R2/R3 limitan auto-ejecución pero no el abuso operativo |
| Media | Errores genéricos en SSE (`/events/webhook/stream`); detalle solo en logs | Hoy `str(exception)` puede filtrar detalles internos al cliente |
| Baja | Rate limiting en `POST /events/webhook` | Mitiga spam de eventos y coste de LLM |

### Robustez operativa

| Prioridad | Mejora | Motivo |
|---|---|---|
| Baja | Manejar condición de carrera en dedup (UNIQUE en `dedup_key` → 409, no 500) | Dos webhooks idénticos concurrentes pueden chocar en la restricción única |
| Baja | Rotación y gestión de secretos (`OPENAI_API_KEY`) vía vault o variables del runtime | La key no debe versionarse; conviene política de rotación si hubo exposición |

### Lo que ya está bien

- **SQL injection**: consultas vía SQLAlchemy ORM con parámetros enlazados; no hay SQL dinámico concatenado.
- **Validación HTTP**: Pydantic con `extra="forbid"`, enums y tipos estrictos en la respuesta del LLM.
- **Restricciones de negocio**: R1/R2/R3 en código de dominio, no delegadas al prompt.
