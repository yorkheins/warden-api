from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from warden.domain.models.approval import ApprovalRequest, ApprovalStatus


class ApprovalListItem(BaseModel):
    id: UUID
    event_id: UUID
    decision_id: UUID
    status: ApprovalStatus
    human_comment: str | None
    resolved_by: str | None
    created_at: datetime

    @classmethod
    def from_domain(cls, approval: ApprovalRequest) -> "ApprovalListItem":
        return cls(
            id=approval.id,
            event_id=approval.event_id,
            decision_id=approval.decision_id,
            status=approval.status,
            human_comment=approval.human_comment,
            resolved_by=approval.resolved_by,
            created_at=approval.created_at,
        )


class ApprovalApproveRequest(BaseModel):
    comment: str | None = None
    resolved_by: str | None = None


class ApprovalRejectRequest(BaseModel):
    comment: str | None = None
    resolved_by: str | None = None
    feedback_reason: str | None = None
    alternative_action: str | None = None


class ApprovalActionResponse(BaseModel):
    approval_id: UUID
    status: str
    action_executed: str | None = None
    outcome: str | None = None
