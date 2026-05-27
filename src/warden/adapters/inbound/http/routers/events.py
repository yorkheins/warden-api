from uuid import UUID

from fastapi import APIRouter, Depends

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
from warden.infrastructure.exceptions import EventNotFoundError

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
