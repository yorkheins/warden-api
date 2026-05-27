import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from warden.adapters.inbound.http.schemas.event_schemas import (
    EventDetailResponse,
    EventListItem,
    EventWebhookRequest,
    EventWebhookResponse,
)
from warden.domain.services.ingest_event import IngestEventUseCase
from warden.infrastructure.container import (
    get_decision_repo,
    get_event_repo,
    get_ingest_use_case,
)
from warden.infrastructure.exceptions import DuplicateEventError, EventNotFoundError

router = APIRouter()


@router.post("/webhook", status_code=202, response_model=EventWebhookResponse)
async def ingest_webhook(
    payload: EventWebhookRequest,
    use_case: IngestEventUseCase = Depends(get_ingest_use_case),
):
    result = await use_case.execute(payload.to_domain())
    return EventWebhookResponse(
        event_id=result.event_id,
        correlation_id=result.correlation_id,
        status=result.status,
    )


@router.post("/webhook/stream")
async def ingest_webhook_stream(
    payload: EventWebhookRequest,
    use_case: IngestEventUseCase = Depends(get_ingest_use_case),
):
    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    async def on_progress(data: dict) -> None:
        await queue.put(data)

    async def run() -> None:
        try:
            result = await use_case.execute(payload.to_domain(), on_progress)
            await queue.put({
                "step": "done",
                "event_id": str(result.event_id),
                "correlation_id": str(result.correlation_id),
                "status": result.status,
            })
        except DuplicateEventError as e:
            await queue.put({"step": "error", "code": "duplicate", "event_id": str(e.event_id)})
        except Exception as e:
            await queue.put({"step": "error", "message": str(e)})
        finally:
            await queue.put(None)

    async def generate():
        task = asyncio.create_task(run())
        while True:
            item = await queue.get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"
        await task

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("", response_model=list[EventListItem])
async def list_events(event_repo=Depends(get_event_repo)):
    events = await event_repo.find_all()
    return [EventListItem.from_domain(e) for e in events]


@router.get("/{event_id}", response_model=EventDetailResponse)
async def get_event(
    event_id: UUID,
    event_repo=Depends(get_event_repo),
    decision_repo=Depends(get_decision_repo),
):
    event = await event_repo.find_by_id(event_id)
    if not event:
        raise EventNotFoundError(f"Event {event_id} not found")
    decision = await decision_repo.find_by_event_id(event_id)
    return EventDetailResponse.from_domain(event, decision)
