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

    @app.middleware("http")
    async def clear_structlog_context(request: Request, call_next):
        structlog.contextvars.clear_contextvars()
        return await call_next(request)

    @app.exception_handler(DuplicateEventError)
    async def duplicate_event_handler(request: Request, exc: DuplicateEventError):
        return JSONResponse(
            status_code=409,
            content={"event_id": str(exc.event_id), "message": "duplicate event"},
        )

    @app.exception_handler(EventNotFoundError)
    async def event_not_found_handler(request: Request, exc: EventNotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ApprovalNotFoundError)
    async def approval_not_found_handler(request: Request, exc: ApprovalNotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ApprovalAlreadyResolvedError)
    async def approval_already_resolved_handler(
        request: Request, exc: ApprovalAlreadyResolvedError
    ):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    app.include_router(health.router, tags=["health"])
    app.include_router(events.router, prefix="/events", tags=["events"])
    app.include_router(approvals.router, prefix="/approvals", tags=["approvals"])

    return app


app = create_app()
