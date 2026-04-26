"""
Watheeq AI Service — Response Schemas

Pydantic models for request validation and response serialization
for the draft response endpoints (US-23, US-24).
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# =============================================================================
# Request Schemas
# =============================================================================


class EditDraftRequest(BaseModel):
    """
    Request body for PUT /api/v1/responses/{claim_id}/draft (US-24).

    Allows a Claims Examiner to edit the AI-generated draft response
    before sending it to the claimant.
    """

    edited_response: str = Field(
        ..., description="The edited response text from the Claims Examiner"
    )
    examiner_id: str = Field(
        ..., description="ID of the Claims Examiner making the edit"
    )


# =============================================================================
# Response Schemas
# =============================================================================


class DraftResponseResult(BaseModel):
    """
    Response for GET /api/v1/responses/{claim_id}/draft (US-23).

    Returns the AI-generated draft and any edits made by the examiner.
    """

    claim_id: str = Field(..., description="The claim this draft belongs to")
    original_draft: str = Field(
        ..., description="The original AI-generated draft response"
    )
    current_draft: str = Field(
        ...,
        description="Current version of the draft (edited or same as original)",
    )
    is_edited: bool = Field(
        default=False,
        description="Whether the draft has been edited by an examiner",
    )
    generated_at: Optional[datetime] = Field(
        default=None, description="When the AI draft was generated"
    )
    last_edited_at: Optional[datetime] = Field(
        default=None, description="When the draft was last edited"
    )
    last_edited_by: Optional[str] = Field(
        default=None, description="Examiner ID who last edited the draft"
    )
    disclaimer: str = Field(
        default="This is an AI-assisted draft. Review and edit before sending to the claimant.",
        description="HITL disclaimer",
    )


class EditDraftResponse(BaseModel):
    """
    Response for PUT /api/v1/responses/{claim_id}/draft (US-24).

    Confirms the draft has been updated.
    """

    claim_id: str = Field(..., description="The claim this draft belongs to")
    current_draft: str = Field(
        ..., description="The updated draft text"
    )
    is_edited: bool = Field(
        default=True, description="Always true after editing"
    )
    last_edited_at: datetime = Field(
        ..., description="Timestamp of this edit"
    )
    last_edited_by: str = Field(
        ..., description="Examiner ID who made the edit"
    )
