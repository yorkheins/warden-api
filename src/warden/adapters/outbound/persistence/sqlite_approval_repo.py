from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from warden.adapters.outbound.persistence.models import ApprovalRequestORM
from warden.domain.models.approval import ApprovalRequest, ApprovalStatus
from warden.domain.ports.approval_repository import ApprovalRepository


class SQLiteApprovalRepository(ApprovalRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, approval: ApprovalRequest) -> ApprovalRequest:
        self._session.add(self._to_orm(approval))
        await self._session.flush()
        return approval

    async def find_by_id(self, approval_id: UUID) -> ApprovalRequest | None:
        row = await self._session.get(ApprovalRequestORM, str(approval_id))
        return self._to_domain(row) if row else None

    async def find_pending(self) -> list[ApprovalRequest]:
        result = await self._session.execute(
            select(ApprovalRequestORM)
            .where(ApprovalRequestORM.status == ApprovalStatus.PENDING.value)
            .order_by(ApprovalRequestORM.created_at.desc())
        )
        return [self._to_domain(row) for row in result.scalars()]

    async def update(self, approval: ApprovalRequest) -> ApprovalRequest:
        row = await self._session.get(ApprovalRequestORM, str(approval.id))
        if row:
            row.status = approval.status.value
            row.human_comment = approval.human_comment
            row.resolved_by = approval.resolved_by
            row.resolved_at = approval.resolved_at
            await self._session.flush()
        return approval

    def _to_orm(self, approval: ApprovalRequest) -> ApprovalRequestORM:
        return ApprovalRequestORM(
            id=str(approval.id),
            event_id=str(approval.event_id),
            decision_id=str(approval.decision_id),
            status=approval.status.value,
            human_comment=approval.human_comment,
            resolved_by=approval.resolved_by,
            resolved_at=approval.resolved_at,
            created_at=approval.created_at,
        )

    def _to_domain(self, row: ApprovalRequestORM) -> ApprovalRequest:
        return ApprovalRequest(
            id=UUID(row.id),
            event_id=UUID(row.event_id),
            decision_id=UUID(row.decision_id),
            status=ApprovalStatus(row.status),
            human_comment=row.human_comment,
            resolved_by=row.resolved_by,
            resolved_at=row.resolved_at,
            created_at=row.created_at,
        )
