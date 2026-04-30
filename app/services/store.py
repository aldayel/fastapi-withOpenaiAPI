"""
Watheeq AI Service — Data Store (Firestore + In-Memory Fallback)

STATELESS architecture — the AI service does NOT persist analysis results or drafts.
It only writes 2 fields to the existing claim document in Firestore:
  - aiDecision: "covered" | "not_covered"
  - aiMessage: The AI's main reasoning/justification

The service reads from:
  - 'claims' collection: to get claim data (medical report URL, policy name)
  - 'policies' collection: to get policy document URL

Firebase credentials can be loaded from:
  1. FIREBASE_CREDENTIALS_JSON env var (JSON string — for Render/Cloud Run)
  2. FIREBASE_CREDENTIALS_PATH file path (for local dev)
"""

import json
import logging
import os
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
                cred = _load_firebase_credentials()
                if cred is None:
                    logger.error("No Firebase credentials found")
                    _firebase_initialized = True
                    return None
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


def _load_firebase_credentials():
    """
    Load Firebase credentials from environment variable or file.

    Priority:
    1. FIREBASE_CREDENTIALS_JSON env var (JSON string)
    2. FIREBASE_CREDENTIALS_PATH file path
    """
    # Option 1: JSON string in env var (for Render, Cloud Run, etc.)
    creds_json = os.environ.get("FIREBASE_CREDENTIALS_JSON", "")
    if creds_json:
        try:
            creds_dict = json.loads(creds_json)
            logger.info("Loaded Firebase credentials from FIREBASE_CREDENTIALS_JSON env var")
            return credentials.Certificate(creds_dict)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse FIREBASE_CREDENTIALS_JSON: {e}")

    # Option 2: File path
    creds_path = settings.FIREBASE_CREDENTIALS_PATH
    if creds_path and os.path.exists(creds_path):
        logger.info(f"Loaded Firebase credentials from file: {creds_path}")
        return credentials.Certificate(creds_path)

    logger.error("No Firebase credentials found (checked FIREBASE_CREDENTIALS_JSON env var and file path)")
    return None


# =============================================================================
# In-Memory Fallback Store (for dev/test mode when Firebase is disabled)
# =============================================================================

_memory_store: Dict[str, dict] = {}
_memory_lock = threading.Lock()


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

    Writes two fields:
      - aiDecision: "covered" | "not_covered"
      - aiMessage: The AI's main reasoning/justification (NOT the draft letter)

    Args:
        claim_id: The Firestore document ID in the 'claims' collection.
        ai_decision: The AI coverage decision.
        ai_message: The AI reasoning/justification text.

    Returns:
        True if the update succeeded, False otherwise.
    """
    db = _get_db()
    if db is None:
        logger.warning(
            f"Firebase not enabled — cannot update claim {claim_id}. "
            "aiDecision and aiMessage stored in memory only."
        )
        with _memory_lock:
            _memory_store[f"claim_{claim_id}"] = {
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
    Tries multiple matching strategies:
      1. Exact match on 'policy_name' field
      2. Lowercase match on 'policy_name' field
      3. Scan all policies for case-insensitive partial match
    """
    db = _get_db()
    if db is None:
        return None

    try:
        # Strategy 1: Exact match
        docs = (
            db.collection("policies")
            .where("policy_name", "==", policy_name)
            .limit(1)
            .get()
        )
        if docs:
            return docs[0].to_dict()

        # Strategy 2: Lowercase match
        docs = (
            db.collection("policies")
            .where("policy_name", "==", policy_name.lower())
            .limit(1)
            .get()
        )
        if docs:
            return docs[0].to_dict()

        # Strategy 3: Scan all policies for partial/case-insensitive match
        all_docs = db.collection("policies").stream()
        search_lower = policy_name.lower()
        for doc in all_docs:
            data = doc.to_dict()
            doc_name = data.get("policy_name", "").lower()
            if doc_name == search_lower or search_lower in doc_name or doc_name in search_lower:
                logger.info(f"Found policy via partial match: '{data.get('policy_name')}'")
                return data

        logger.warning(f"No policy found matching '{policy_name}'")
        return None

    except Exception as e:
        logger.error(f"Failed to get policy '{policy_name}': {e}")
        return None


# =============================================================================
# In-Memory Analysis Cache (for GET endpoint — temporary within session)
# =============================================================================


def save_analysis_to_memory(analysis_id: str, data: dict) -> None:
    """
    Save analysis result to in-memory cache for retrieval via GET endpoint.
    This is NOT persisted to Firestore — it's only for the current session.
    """
    with _memory_lock:
        claim_id = data.get("claim_id", analysis_id)
        _memory_store[f"analysis_{claim_id}"] = data


def get_analysis_from_memory(claim_id: str) -> Optional[dict]:
    """
    Retrieve analysis result from in-memory cache.
    Returns None if not found (analysis not yet completed or service restarted).
    """
    with _memory_lock:
        return _memory_store.get(f"analysis_{claim_id}")


# =============================================================================
# Utility — Clear stores (for testing only)
# =============================================================================


def clear_all_stores() -> None:
    """Clear all in-memory stores. Used in tests only."""
    with _memory_lock:
        _memory_store.clear()
