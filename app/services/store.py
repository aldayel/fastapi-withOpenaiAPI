"""
Watheeq AI Service — Data Store (Firestore + In-Memory Fallback)

Provides persistence for AI analysis results and draft responses.
When Firebase is enabled, writes directly to Firestore collections:
  - 'claims' collection: updates existing claim docs with aiDecision + aiMessage
  - 'ai_analyses' collection: stores full AI analysis records (keyed by claim_id)
  - 'ai_drafts' collection: stores draft response records (keyed by claim_id)

When Firebase is disabled, falls back to in-memory storage (dev/test mode).

Design note: We use claim_id as the document ID for ai_analyses and ai_drafts
to avoid needing Firestore composite indexes and to simplify lookups.
"""

import logging
import threading
from typing import Dict, Optional

import firebase_admin
from firebase_admin import credentials, firestore

from app.config import settings

logger = logging.getLogger(__name__)

# =============================================================================
# Firebase Initialization
# =============================================================================

_db = None
_firebase_initialized = False


def _get_db():
    """Get or initialize the Firestore client."""
    global _db, _firebase_initialized

    if _db is not None:
        return _db

    if not _firebase_initialized and settings.FIREBASE_ENABLED:
        try:
            # Check if already initialized
            try:
                firebase_admin.get_app()
            except ValueError:
                cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
                firebase_admin.initialize_app(cred, {
                    "projectId": settings.FIREBASE_PROJECT_ID,
                })
            _db = firestore.client()
            _firebase_initialized = True
            logger.info("Firestore client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Firestore: {e}")
            logger.warning("Falling back to in-memory storage")
            _firebase_initialized = True  # Don't retry
            _db = None

    return _db


# =============================================================================
# In-Memory Fallback Stores
# =============================================================================

_analysis_store: Dict[str, dict] = {}
_analysis_lock = threading.Lock()

_draft_store: Dict[str, dict] = {}
_draft_lock = threading.Lock()


# =============================================================================
# Analysis Store — Full AI analysis records
# =============================================================================


def save_analysis(analysis_id: str, data: dict) -> None:
    """
    Save or update an analysis record.

    Uses the claim_id from the data as the Firestore document ID
    so we can look up by claim_id without a composite index.
    Also stores the analysis_id inside the document for reference.
    """
    db = _get_db()
    claim_id = data.get("claim_id", analysis_id)

    if db is not None:
        try:
            # Use claim_id as doc ID for easy lookup; store analysis_id inside
            db.collection("ai_analyses").document(claim_id).set(data, merge=True)
            logger.debug(f"Analysis {analysis_id} for claim {claim_id} saved to Firestore")
            return
        except Exception as e:
            logger.error(f"Firestore save_analysis failed: {e}, falling back to memory")

    # In-memory fallback
    with _analysis_lock:
        if analysis_id in _analysis_store:
            _analysis_store[analysis_id].update(data)
        else:
            _analysis_store[analysis_id] = data


def get_analysis(analysis_id: str) -> Optional[dict]:
    """Retrieve an analysis record by its analysis ID."""
    db = _get_db()
    if db is not None:
        try:
            # Try direct lookup first (analysis_id might be claim_id)
            doc = db.collection("ai_analyses").document(analysis_id).get()
            if doc.exists:
                return doc.to_dict()
            return None
        except Exception as e:
            logger.error(f"Firestore get_analysis failed: {e}")

    return _analysis_store.get(analysis_id)


def get_analysis_by_claim(claim_id: str) -> Optional[dict]:
    """
    Retrieve the analysis record for a given claim ID.

    Since we use claim_id as the document ID, this is a simple
    document get — no composite index needed.
    """
    db = _get_db()
    if db is not None:
        try:
            doc = db.collection("ai_analyses").document(claim_id).get()
            if doc.exists:
                return doc.to_dict()
            return None
        except Exception as e:
            logger.error(f"Firestore get_analysis_by_claim failed: {e}")

    # In-memory fallback
    matching = [
        data
        for data in _analysis_store.values()
        if data.get("claim_id") == claim_id
    ]
    if not matching:
        return None
    matching.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return matching[0]


# =============================================================================
# Claims Collection — Write aiDecision + aiMessage to existing claim docs
# =============================================================================


def update_claim_with_ai_result(
    claim_id: str,
    ai_decision: str,
    ai_message: str,
) -> bool:
    """
    Update the existing claim document in the 'claims' collection
    with the AI analysis results.

    Writes two new fields:
      - aiDecision: "covered" | "not_covered" | "partial"
      - aiMessage: The AI-generated draft response message

    Args:
        claim_id: The Firestore document ID in the 'claims' collection.
        ai_decision: The AI coverage decision.
        ai_message: The AI-generated draft response text.

    Returns:
        True if the update succeeded, False otherwise.
    """
    db = _get_db()
    if db is None:
        logger.warning(
            f"Firebase not enabled — cannot update claim {claim_id}. "
            "aiDecision and aiMessage stored in memory only."
        )
        # Store in memory as a fallback
        with _analysis_lock:
            key = f"claim_update_{claim_id}"
            _analysis_store[key] = {
                "claim_id": claim_id,
                "aiDecision": ai_decision,
                "aiMessage": ai_message,
            }
        return False

    try:
        claim_ref = db.collection("claims").document(claim_id)
        claim_doc = claim_ref.get()

        if not claim_doc.exists:
            logger.error(f"Claim document {claim_id} not found in Firestore")
            return False

        claim_ref.update({
            "aiDecision": ai_decision,
            "aiMessage": ai_message,
        })

        logger.info(
            f"Claim {claim_id} updated with aiDecision='{ai_decision}' "
            f"and aiMessage (length={len(ai_message)})"
        )
        return True

    except Exception as e:
        logger.error(f"Failed to update claim {claim_id} in Firestore: {e}")
        return False


def get_claim(claim_id: str) -> Optional[dict]:
    """
    Retrieve a claim document from the 'claims' collection.

    Used to read claim data (patient info, medical report URL, policy name)
    when triggering analysis.
    """
    db = _get_db()
    if db is None:
        return None

    try:
        doc = db.collection("claims").document(claim_id).get()
        if doc.exists:
            return doc.to_dict()
        return None
    except Exception as e:
        logger.error(f"Failed to get claim {claim_id}: {e}")
        return None


def get_policy_by_name(policy_name: str) -> Optional[dict]:
    """
    Retrieve a policy document from the 'policies' collection by name.

    Used to find the policy PDF URL for a given claim's policyName.
    """
    db = _get_db()
    if db is None:
        return None

    try:
        docs = (
            db.collection("policies")
            .where("policy_name", "==", policy_name.lower())
            .limit(1)
            .get()
        )
        if docs:
            return docs[0].to_dict()
        return None
    except Exception as e:
        logger.error(f"Failed to get policy '{policy_name}': {e}")
        return None


# =============================================================================
# Draft Response Store
# =============================================================================


def save_draft(claim_id: str, data: dict) -> None:
    """Save or update a draft response record (keyed by claim_id)."""
    db = _get_db()
    if db is not None:
        try:
            db.collection("ai_drafts").document(claim_id).set(data, merge=True)
            logger.debug(f"Draft for claim {claim_id} saved to Firestore")
            return
        except Exception as e:
            logger.error(f"Firestore save_draft failed: {e}")

    # In-memory fallback
    with _draft_lock:
        if claim_id in _draft_store:
            _draft_store[claim_id].update(data)
        else:
            _draft_store[claim_id] = data


def get_draft(claim_id: str) -> Optional[dict]:
    """Retrieve a draft response record for a given claim ID."""
    db = _get_db()
    if db is not None:
        try:
            doc = db.collection("ai_drafts").document(claim_id).get()
            if doc.exists:
                return doc.to_dict()
            return None
        except Exception as e:
            logger.error(f"Firestore get_draft failed: {e}")

    return _draft_store.get(claim_id)


# =============================================================================
# Utility — Clear stores (for testing only)
# =============================================================================


def clear_all_stores() -> None:
    """Clear all in-memory stores. Used in tests only."""
    with _analysis_lock:
        _analysis_store.clear()
    with _draft_lock:
        _draft_store.clear()
