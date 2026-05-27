import httpx
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from warden.adapters.outbound.llm.mock_llm_client import MockLLMClient
from warden.adapters.outbound.llm.openai_client import OpenAIClient
from warden.adapters.outbound.notifier.http_notifier import HttpNotifierClient
from warden.adapters.outbound.orchestrator.http_orchestrator import HttpOrchestratorClient
from warden.adapters.outbound.persistence.sqlite_approval_repo import SQLiteApprovalRepository
from warden.adapters.outbound.persistence.sqlite_decision_repo import SQLiteDecisionRepository
from warden.adapters.outbound.persistence.sqlite_event_repo import SQLiteEventRepository
from warden.adapters.outbound.persistence.sqlite_history_repo import SQLiteHistoryRepository
from warden.domain.ports.llm_client import LLMClient
from warden.domain.services.action_executor import ActionExecutorService
from warden.domain.services.approval_service import ApprovalService
from warden.domain.services.ingest_event import IngestEventUseCase
from warden.domain.services.reasoning_engine import ReasoningEngineService
from warden.infrastructure.config import Settings
from warden.infrastructure.database import build_engine, build_session_factory


class Container:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine: AsyncEngine = build_engine(settings.DATABASE_URL)
        self.session_factory: async_sessionmaker[AsyncSession] = build_session_factory(
            self.engine
        )
        self._http_client = httpx.AsyncClient(timeout=30.0)
        self._orchestrator = HttpOrchestratorClient(self._http_client, settings)
        self._notifier = HttpNotifierClient(self._http_client, settings)
        self._llm: LLMClient = (
            MockLLMClient() if settings.USE_MOCK_LLM else OpenAIClient(settings)
        )

    async def close(self) -> None:
        await self._http_client.aclose()
        await self.engine.dispose()

    def build_ingest_use_case(self, session: AsyncSession) -> IngestEventUseCase:
        event_repo = SQLiteEventRepository(session)
        decision_repo = SQLiteDecisionRepository(session)
        approval_repo = SQLiteApprovalRepository(session)
        history_repo = SQLiteHistoryRepository(session)
        reasoning = ReasoningEngineService(self._llm, history_repo, self.settings)
        executor = ActionExecutorService(self._orchestrator, self._notifier)
        return IngestEventUseCase(
            event_repo, decision_repo, approval_repo, history_repo,
            reasoning, executor, self._notifier,
        )

    def build_approval_service(self, session: AsyncSession) -> ApprovalService:
        event_repo = SQLiteEventRepository(session)
        decision_repo = SQLiteDecisionRepository(session)
        approval_repo = SQLiteApprovalRepository(session)
        history_repo = SQLiteHistoryRepository(session)
        executor = ActionExecutorService(self._orchestrator, self._notifier)
        return ApprovalService(approval_repo, history_repo, executor, event_repo, decision_repo)

    def get_event_repo(self, session: AsyncSession) -> SQLiteEventRepository:
        return SQLiteEventRepository(session)

    def get_decision_repo(self, session: AsyncSession) -> SQLiteDecisionRepository:
        return SQLiteDecisionRepository(session)

    def get_approval_repo(self, session: AsyncSession) -> SQLiteApprovalRepository:
        return SQLiteApprovalRepository(session)


def get_container(request: Request) -> Container:
    return request.app.state.container


async def get_session(container: Container = Depends(get_container)):
    async with container.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_ingest_use_case(
    container: Container = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> IngestEventUseCase:
    return container.build_ingest_use_case(session)


def get_approval_service(
    container: Container = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> ApprovalService:
    return container.build_approval_service(session)


def get_event_repo(
    container: Container = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> SQLiteEventRepository:
    return container.get_event_repo(session)


def get_decision_repo(
    container: Container = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> SQLiteDecisionRepository:
    return container.get_decision_repo(session)


def get_approval_repo(
    container: Container = Depends(get_container),
    session: AsyncSession = Depends(get_session),
) -> SQLiteApprovalRepository:
    return container.get_approval_repo(session)
