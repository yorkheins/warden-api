from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from warden.adapters.outbound.persistence.models import WorkloadHistoryORM
from warden.domain.models.decision import Action
from warden.domain.models.workload_history import OutcomeStatus, WorkloadHistoryEntry
from warden.domain.ports.history_repository import HistoryRepository


class SQLiteHistoryRepository(HistoryRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, entry: WorkloadHistoryEntry) -> WorkloadHistoryEntry:
        self._session.add(self._to_orm(entry))
        await self._session.flush()
        return entry

    async def find_by_workload(
        self, project_id: str, environment_id: str, limit: int
    ) -> list[WorkloadHistoryEntry]:
        result = await self._session.execute(
            select(WorkloadHistoryORM)
            .where(
                WorkloadHistoryORM.project_id == project_id,
                WorkloadHistoryORM.environment_id == environment_id,
            )
            .order_by(WorkloadHistoryORM.created_at.desc())
            .limit(limit)
        )
        return [self._to_domain(row) for row in result.scalars()]

    async def update_outcome(
        self,
        event_id: UUID,
        outcome: OutcomeStatus,
        human_feedback: str | None,
        feedback_reason: str | None = None,
        alternative_action: str | None = None,
    ) -> None:
        result = await self._session.execute(
            select(WorkloadHistoryORM).where(
                WorkloadHistoryORM.event_id == str(event_id)
            )
        )
        row = result.scalar_one_or_none()
        if row:
            row.outcome = outcome.value
            row.human_feedback = human_feedback
            row.feedback_reason = feedback_reason
            row.alternative_action = alternative_action
            await self._session.flush()

    def _to_orm(self, entry: WorkloadHistoryEntry) -> WorkloadHistoryORM:
        return WorkloadHistoryORM(
            id=str(entry.id),
            project_id=entry.project_id,
            environment_id=entry.environment_id,
            event_id=str(entry.event_id),
            signal=entry.signal,
            action_decided=entry.action_decided.value,
            was_auto=entry.was_auto,
            outcome=entry.outcome.value,
            human_feedback=entry.human_feedback,
            feedback_reason=entry.feedback_reason,
            alternative_action=entry.alternative_action,
            created_at=entry.created_at,
        )

    def _to_domain(self, row: WorkloadHistoryORM) -> WorkloadHistoryEntry:
        return WorkloadHistoryEntry(
            id=UUID(row.id),
            project_id=row.project_id,
            environment_id=row.environment_id,
            event_id=UUID(row.event_id),
            signal=row.signal,
            action_decided=Action(row.action_decided),
            was_auto=row.was_auto,
            outcome=OutcomeStatus(row.outcome),
            human_feedback=row.human_feedback,
            feedback_reason=row.feedback_reason,
            alternative_action=row.alternative_action,
            created_at=row.created_at,
        )
