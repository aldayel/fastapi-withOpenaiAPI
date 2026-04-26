"""
Watheeq AI Service — Responses Router

THIN endpoint layer — handles HTTP concerns ONLY (validation, status codes, auth).
ALL business logic lives in the service layer (response_service.py).

Endpoints:
  GET  /{claim_id}/draft  — US-23: Get AI draft response
  PUT  /{claim_id}/draft  — US-24: Edit AI draft response
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import verify_bearer_token
from app.schemas.responses import (
    DraftResponseResult,
    EditDraftRequest,
    EditDraftResponse,
)
from app.services import response_service
from app.utils.exceptions import DraftNotFoundError

router = APIRouter()


# =============================================================================
# GET /{claim_id}/draft — US-23: Get AI Draft Response
# =============================================================================


@router.get(
    "/{claim_id}/draft",
    response_model=DraftResponseResult,
    summary="Get AI draft response for a claim",
    description=(
        "Returns the AI-generated draft response message for a claim. "
        "If the examiner has edited the draft, both the original and "
        "current (edited) versions are returned for audit comparison."
    ),
    dependencies=[Depends(verify_bearer_token)],
)
async def get_draft_response(claim_id: str) -> DraftResponseResult:
    """
    Get AI draft response for a claim (US-23).

    This endpoint:
    1. Looks up the draft response by claim_id
    2. Returns both original and current (possibly edited) drafts
    3. Returns 404 if no draft exists for this claim
    """
    try:
        data = response_service.get_draft_response(claim_id)
    except DraftNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message,
        )

    return DraftResponseResult(
        claim_id=data.get("claim_id", claim_id),
        original_draft=data.get("original_draft", ""),
        current_draft=data.get("current_draft", ""),
        is_edited=data.get("is_edited", False),
        generated_at=data.get("generated_at"),
        last_edited_at=data.get("last_edited_at"),
        last_edited_by=data.get("last_edited_by"),
    )


# =============================================================================
# PUT /{claim_id}/draft — US-24: Edit AI Draft Response
# =============================================================================


@router.put(
    "/{claim_id}/draft",
    response_model=EditDraftResponse,
    summary="Edit AI draft response for a claim",
    description=(
        "Allows a Claims Examiner to edit the AI-generated draft response "
        "before sending it to the claimant. The original AI draft is "
        "preserved for audit comparison. The edited version becomes the "
        "current draft that will be sent upon approval."
    ),
    dependencies=[Depends(verify_bearer_token)],
)
async def edit_draft_response(
    claim_id: str,
    data: EditDraftRequest,
) -> EditDraftResponse:
    """
    Edit AI draft response for a claim (US-24).

    This endpoint:
    1. Validates the edit request
    2. Updates the current_draft while preserving the original
    3. Returns the updated draft with edit metadata
    4. Returns 404 if no draft exists for this claim
    """
    try:
        updated = response_service.edit_draft_response(
            claim_id=claim_id,
            edited_response=data.edited_response,
            examiner_id=data.examiner_id,
        )
    except DraftNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message,
        )

    # Parse the last_edited_at from the stored data
    last_edited_at = updated.get("last_edited_at")
    if isinstance(last_edited_at, str):
        last_edited_at = datetime.fromisoformat(last_edited_at)

    return EditDraftResponse(
        claim_id=claim_id,
        current_draft=updated.get("current_draft", ""),
        is_edited=True,
        last_edited_at=last_edited_at or datetime.utcnow(),
        last_edited_by=updated.get("last_edited_by", data.examiner_id),
    )
