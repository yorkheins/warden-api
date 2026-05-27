import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from warden.adapters.inbound.http.routers import approvals, events, health
from warden.adapters.outbound.persistence.models import Base
from warden.infrastructure.config import Settings
from warden.infrastructure.container import Container, get_container
from warden.infrastructure.exceptions import (
    ApprovalAlreadyResolvedError,
    ApprovalNotFoundError,
    DuplicateEventError,
    EventNotFoundError,
)


def build_test_app(container: Container) -> FastAPI:
    app = FastAPI()

    @app.exception_handler(DuplicateEventError)
    async def dup(req: Request, exc: DuplicateEventError):
        return JSONResponse(status_code=409, content={"event_id": str(exc.event_id), "message": "duplicate event"})

    @app.exception_handler(EventNotFoundError)
    async def enf(req: Request, exc: EventNotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ApprovalNotFoundError)
    async def anf(req: Request, exc: ApprovalNotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ApprovalAlreadyResolvedError)
    async def aar(req: Request, exc: ApprovalAlreadyResolvedError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    app.dependency_overrides[get_container] = lambda: container
    app.include_router(health.router, tags=["health"])
    app.include_router(events.router, prefix="/events", tags=["events"])
    app.include_router(approvals.router, prefix="/approvals", tags=["approvals"])

    return app


@pytest_asyncio.fixture
async def container():
    settings = Settings(
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        USE_MOCK_LLM=True,
        NOTIFIER_MOCK_URL="http://localhost:9999",
        ORCHESTRATOR_MOCK_URL="http://localhost:9998",
    )
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    c = Container(settings)
    await c.engine.dispose()
    c.engine = engine
    c.session_factory = async_sessionmaker(engine, expire_on_commit=False)

    yield c

    await c._http_client.aclose()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(container):
    app = build_test_app(container)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
