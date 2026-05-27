from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from warden.adapters.outbound.persistence.models import DecisionORM
from warden.domain.models.decision import Action, Decision, ExecutionStatus
from warden.domain.ports.decision_repository import DecisionRepository


class SQLiteDecisionRepository(DecisionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, decision: Decision) -> Decision:
        self._session.add(self._to_orm(decision))
        await self._session.flush()
        return decision

    async def update_execution_status(self, decision_id: UUID, status: ExecutionStatus) -> None:
        await self._session.execute(
            update(DecisionORM)
            .where(DecisionORM.id == str(decision_id))
            .values(execution_status=status.value)
        )
        await self._session.flush()

    async def find_by_event_id(self, event_id: UUID) -> Decision | None:
        result = await self._session.execute(
            select(DecisionORM).where(DecisionORM.event_id == str(event_id))
        )
        row = result.scalar_one_or_none()
        return self._to_domain(row) if row else None

    def _to_orm(self, decision: Decision) -> DecisionORM:
        return DecisionORM(
            id=str(decision.id),
            event_id=str(decision.event_id),
            action=decision.action.value,
            confidence=decision.confidence,
            reasoning=decision.reasoning,
            safe_to_auto=decision.safe_to_auto,
            restrictions_applied=decision.restrictions_applied,
            llm_raw_output=decision.llm_raw_output,
            execution_status=decision.execution_status.value,
            created_at=decision.created_at,
        )

    def _to_domain(self, row: DecisionORM) -> Decision:
        return Decision(
            id=UUID(row.id),
            event_id=UUID(row.event_id),
            action=Action(row.action),
            confidence=row.confidence,
            reasoning=row.reasoning,
            safe_to_auto=row.safe_to_auto,
            restrictions_applied=row.restrictions_applied,
            llm_raw_output=row.llm_raw_output,
            execution_status=ExecutionStatus(row.execution_status),
            created_at=row.created_at,
        )
