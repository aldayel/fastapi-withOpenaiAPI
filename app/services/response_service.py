"""
Watheeq AI Service — Response Service

Handles draft response generation (US-23) and editing (US-24).
Generates professional response messages for claimants based on AI analysis results.
"""

import logging
from datetime import datetime
from typing import Optional

from app.models.response import DraftResponseRecord
from app.services import llm_service
from app.services.store import get_draft, save_draft
from app.utils.exceptions import DraftNotFoundError
from app.utils.prompts import (
    DRAFT_RESPONSE_SYSTEM_PROMPT,
    build_draft_response_prompt,
)

logger = logging.getLogger(__name__)


async def generate_draft(
    claim_id: str,
    patient_info: dict,
    treatment_type: str,
    coverage_decision: str,
    reasoning: str,
    applicable_clauses: list,
    flags: list,
) -> str:
    """
    Generate an AI draft response message for the claimant (US-23).

    This is called automatically after the AI analysis completes.
    The draft is stored and can be retrieved/edited by the Claims Examiner.

    Args:
        claim_id: The claim this draft is for.
        patient_info: Patient demographics dict.
        treatment_type: Type of treatment.
        coverage_decision: AI coverage determination.
        reasoning: AI reasoning for the decision.
        applicable_clauses: List of cited policy clauses.
        flags: List of concerns flagged by the AI.

    Returns:
        The generated draft response text.
    """
    logger.info(f"Generating draft response for claim {claim_id}")

    # Build the prompt for draft generation
    user_prompt = build_draft_response_prompt(
        patient_info=patient_info,
        treatment_type=treatment_type,
        coverage_decision=coverage_decision,
        reasoning=reasoning,
        applicable_clauses=applicable_clauses,
        flags=flags,
    )

    # Call LLM to generate the draft
    draft_text = await llm_service.generate_text(
        user_prompt=user_prompt,
        system_prompt=DRAFT_RESPONSE_SYSTEM_PROMPT,
    )

    # Store the draft
    now = datetime.utcnow()
    draft_record = DraftResponseRecord(
        claim_id=claim_id,
        original_draft=draft_text,
        current_draft=draft_text,
        is_edited=False,
        generated_at=now,
    )
    save_draft(claim_id, draft_record.to_dict())

    logger.info(f"Draft response generated and stored for claim {claim_id}")
    return draft_text


def get_draft_response(claim_id: str) -> dict:
    """
    Retrieve the draft response for a claim (US-23).

    Args:
        claim_id: The claim to retrieve the draft for.

    Returns:
        Draft response data dictionary.

    Raises:
        DraftNotFoundError: If no draft exists for the claim.
    """
    draft_data = get_draft(claim_id)
    if draft_data is None:
        raise DraftNotFoundError(claim_id)
    return draft_data


def edit_draft_response(
    claim_id: str,
    edited_response: str,
    examiner_id: str,
) -> dict:
    """
    Edit the draft response for a claim (US-24).

    Preserves the original AI draft for audit comparison.
    Updates the current_draft with the examiner's edits.

    Args:
        claim_id: The claim whose draft is being edited.
        edited_response: The new response text from the examiner.
        examiner_id: ID of the examiner making the edit.

    Returns:
        Updated draft response data dictionary.

    Raises:
        DraftNotFoundError: If no draft exists for the claim.
    """
    draft_data = get_draft(claim_id)
    if draft_data is None:
        raise DraftNotFoundError(claim_id)

    now = datetime.utcnow()

    # Update the draft — original_draft is preserved for audit
    draft_data["current_draft"] = edited_response
    draft_data["is_edited"] = True
    draft_data["last_edited_at"] = now.isoformat()
    draft_data["last_edited_by"] = examiner_id

    save_draft(claim_id, draft_data)

    logger.info(
        f"Draft response edited for claim {claim_id} by examiner {examiner_id}"
    )

    return draft_data
