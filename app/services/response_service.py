"""
Watheeq AI Service — Response Service

Handles draft response generation (US-23) and editing (US-24).

LOGIC:
  - covered → Returns a hardcoded approval statement (no AI generation needed)
  - not_covered → AI generates a draft rejection message for the examiner to review/edit

STATELESS: Drafts are cached in memory only, NOT stored in Firestore.
The draft is returned directly to the examiner's response box in the frontend.
"""

import logging
from datetime import datetime
from typing import Optional

from app.services import llm_service
from app.services.store import save_analysis_to_memory, get_analysis_from_memory
from app.utils.exceptions import DraftNotFoundError
from app.utils.prompts import (
    DRAFT_RESPONSE_SYSTEM_PROMPT,
    build_draft_response_prompt,
)

logger = logging.getLogger(__name__)

# =============================================================================
# Hardcoded approval statement for covered claims
# =============================================================================

APPROVAL_STATEMENT = (
    "Your claim has been reviewed and approved. "
    "The treatment is covered under your insurance policy. "
    "No further action is required from your side. "
    "Thank you for choosing Watheeq."
)


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
    Generate a draft response message for the examiner (US-23).

    Logic:
      - covered → Return hardcoded approval statement (no AI call)
      - not_covered → AI generates draft rejection for examiner to review/edit

    The draft is cached in memory for retrieval via GET endpoint.
    It is NOT stored in Firestore.

    Args:
        claim_id: The claim this draft is for.
        patient_info: Patient demographics dict.
        treatment_type: Type of treatment.
        coverage_decision: AI coverage determination.
        reasoning: AI reasoning for the decision.
        applicable_clauses: List of cited policy clauses.
        flags: List of concerns flagged by the AI.

    Returns:
        The draft response text.
    """
    logger.info(f"Generating draft response for claim {claim_id} (decision: {coverage_decision})")

    if coverage_decision == "covered":
        # Hardcoded approval — no AI generation needed
        draft_text = APPROVAL_STATEMENT
        logger.info(f"Draft for claim {claim_id}: hardcoded approval statement")
    else:
        # AI-generated rejection draft for examiner to review/edit
        user_prompt = build_draft_response_prompt(
            patient_info=patient_info,
            treatment_type=treatment_type,
            coverage_decision=coverage_decision,
            reasoning=reasoning,
            applicable_clauses=applicable_clauses,
            flags=flags,
        )

        draft_text = await llm_service.generate_text(
            user_prompt=user_prompt,
            system_prompt=DRAFT_RESPONSE_SYSTEM_PROMPT,
        )
        logger.info(f"Draft for claim {claim_id}: AI-generated rejection ({len(draft_text)} chars)")

    # Cache the draft in memory for GET/PUT endpoints
    now = datetime.utcnow().isoformat()
    draft_record = {
        "claim_id": claim_id,
        "original_draft": draft_text,
        "current_draft": draft_text,
        "is_edited": False,
        "generated_at": now,
        "coverage_decision": coverage_decision,
    }
    _save_draft_to_memory(claim_id, draft_record)

    return draft_text


def get_draft_response(claim_id: str) -> dict:
    """
    Retrieve the draft response for a claim (US-23).

    Drafts are stored in memory only (stateless architecture).

    Args:
        claim_id: The claim to retrieve the draft for.

    Returns:
        Draft response data dictionary.

    Raises:
        DraftNotFoundError: If no draft exists for the claim.
    """
    draft_data = _get_draft_from_memory(claim_id)
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
    draft_data = _get_draft_from_memory(claim_id)
    if draft_data is None:
        raise DraftNotFoundError(claim_id)

    now = datetime.utcnow().isoformat()

    # Update the draft — original_draft is preserved for audit
    draft_data["current_draft"] = edited_response
    draft_data["is_edited"] = True
    draft_data["last_edited_at"] = now
    draft_data["last_edited_by"] = examiner_id

    _save_draft_to_memory(claim_id, draft_data)

    logger.info(
        f"Draft response edited for claim {claim_id} by examiner {examiner_id}"
    )

    return draft_data


# =============================================================================
# In-Memory Draft Cache (private helpers)
# =============================================================================

import threading

_draft_store: dict = {}
_draft_lock = threading.Lock()


def _save_draft_to_memory(claim_id: str, data: dict) -> None:
    """Save draft to in-memory cache."""
    with _draft_lock:
        _draft_store[claim_id] = data


def _get_draft_from_memory(claim_id: str) -> Optional[dict]:
    """Get draft from in-memory cache."""
    with _draft_lock:
        return _draft_store.get(claim_id)


def clear_draft_store() -> None:
    """Clear draft store. Used in tests only."""
    with _draft_lock:
        _draft_store.clear()
