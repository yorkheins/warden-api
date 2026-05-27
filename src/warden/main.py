from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from warden.adapters.inbound.http.routers import approvals, events, health
from warden.infrastructure.config import get_settings
from warden.infrastructure.container import Container
from warden.infrastructure.database import init_db
from warden.infrastructure.exceptions import (
    ApprovalAlreadyResolvedError,
    ApprovalNotFoundError,
    DuplicateEventError,
    EventNotFoundError,
)
from warden.infrastructure.logging import configure_logging


async def _clear_structlog_context(request: Request, call_next):
    structlog.contextvars.clear_contextvars()
    return await call_next(request)


async def _duplicate_event_handler(_request, exc: DuplicateEventError):
    return JSONResponse(
        status_code=409,
        content={"event_id": str(exc.event_id), "message": "duplicate event"},
    )


async def _event_not_found_handler(_request, exc: EventNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


async def _approval_not_found_handler(_request, exc: ApprovalNotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


async def _approval_already_resolved_handler(_request, exc: ApprovalAlreadyResolvedError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(
        log_level=settings.LOG_LEVEL,
        json_logs=settings.APP_ENV == "production",
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        container = Container(settings)
        await init_db(container.engine)
        app.state.container = container
        yield
        await container.close()

    app = FastAPI(title="Warden", version="0.1.0", lifespan=lifespan)

    app.middleware("http")(_clear_structlog_context)

    app.add_exception_handler(DuplicateEventError, _duplicate_event_handler)
    app.add_exception_handler(EventNotFoundError, _event_not_found_handler)
    app.add_exception_handler(ApprovalNotFoundError, _approval_not_found_handler)
    app.add_exception_handler(ApprovalAlreadyResolvedError, _approval_already_resolved_handler)

    app.include_router(health.router, tags=["health"])
    app.include_router(events.router, prefix="/events", tags=["events"])
    app.include_router(approvals.router, prefix="/approvals", tags=["approvals"])

    return app


app = create_app()
