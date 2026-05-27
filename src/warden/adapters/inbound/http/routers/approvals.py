from uuid import UUID

from fastapi import APIRouter, Depends

from warden.adapters.inbound.http.schemas.approval_schemas import (
    ApprovalApproveRequest,
    ApprovalRejectRequest,
    ApprovalActionResponse,
    ApprovalListItem,
)
from warden.domain.services.approval_service import ApprovalService
from warden.infrastructure.container import get_approval_repo, get_approval_service

router = APIRouter()


@router.get("", response_model=list[ApprovalListItem])
async def list_approvals(approval_repo=Depends(get_approval_repo)):
    approvals = await approval_repo.find_pending()
    return [ApprovalListItem.from_domain(a) for a in approvals]


@router.post("/{approval_id}/approve", response_model=ApprovalActionResponse)
async def approve(
    approval_id: UUID,
    body: ApprovalApproveRequest,
    approval_service: ApprovalService = Depends(get_approval_service),
):
    result = await approval_service.approve(approval_id, body.resolved_by, body.comment)
    return ApprovalActionResponse(
        approval_id=approval_id,
        status="approved",
        action_executed=str(result.message),
        outcome="success" if result.success else "failed",
    )


@router.post("/{approval_id}/reject", response_model=ApprovalActionResponse)
async def reject(
    approval_id: UUID,
    body: ApprovalRejectRequest,
    approval_service: ApprovalService = Depends(get_approval_service),
):
    await approval_service.reject(
        approval_id, body.resolved_by, body.comment,
        body.feedback_reason, body.alternative_action,
    )
    return ApprovalActionResponse(
        approval_id=approval_id,
        status="rejected",
    )
