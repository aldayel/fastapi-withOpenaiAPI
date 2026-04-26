"""
Watheeq AI Service — Data Store

In-memory store for analysis results and draft responses (Mode B — Stateless Default).
This allows the microservice to operate without direct database access.

PRODUCTION UPGRADE — To use Firestore (Mode A):
    1. pip install firebase-admin
    2. Set FIREBASE_ENABLED=true in .env
    3. Provide FIREBASE_CREDENTIALS_PATH in .env
    4. Replace the in-memory operations below with Firestore calls:

        from firebase_admin import firestore
        db = firestore.client()

        # Save:
        db.collection('analyses').document(analysis_id).set(data)

        # Get by ID:
        doc = db.collection('analyses').document(analysis_id).get()

        # Query by claim_id:
        docs = db.collection('analyses').where('claim_id', '==', claim_id).get()

    5. Similarly for draft responses:
        db.collection('draft_responses').document(claim_id).set(data)

NOTE: The in-memory store is NOT persistent across service restarts.
      This is acceptable for the MVP / development / testing.
      For production, always use Firestore or another persistent store.
"""

import threading
from typing import Dict, Optional


# =============================================================================
# Analysis Store
# =============================================================================

_analysis_store: Dict[str, dict] = {}
_analysis_lock = threading.Lock()


def save_analysis(analysis_id: str, data: dict) -> None:
    """
    Save or update an analysis record.

    Firestore equivalent:
        db.collection('analyses').document(analysis_id).set(data, merge=True)
    """
    with _analysis_lock:
        if analysis_id in _analysis_store:
            _analysis_store[analysis_id].update(data)
        else:
            _analysis_store[analysis_id] = data


def get_analysis(analysis_id: str) -> Optional[dict]:
    """
    Retrieve an analysis record by its ID.

    Firestore equivalent:
        doc = db.collection('analyses').document(analysis_id).get()
        return doc.to_dict() if doc.exists else None
    """
    return _analysis_store.get(analysis_id)


def get_analysis_by_claim(claim_id: str) -> Optional[dict]:
    """
    Retrieve the most recent analysis record for a given claim ID.

    Firestore equivalent:
        docs = (db.collection('analyses')
                  .where('claim_id', '==', claim_id)
                  .order_by('created_at', direction=firestore.Query.DESCENDING)
                  .limit(1)
                  .get())
        return docs[0].to_dict() if docs else None
    """
    # Return the most recently created analysis for this claim
    matching = [
        data
        for data in _analysis_store.values()
        if data.get("claim_id") == claim_id
    ]
    if not matching:
        return None
    # Sort by created_at descending and return the latest
    matching.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return matching[0]


# =============================================================================
# Draft Response Store
# =============================================================================

_draft_store: Dict[str, dict] = {}
_draft_lock = threading.Lock()


def save_draft(claim_id: str, data: dict) -> None:
    """
    Save or update a draft response record.

    Firestore equivalent:
        db.collection('draft_responses').document(claim_id).set(data, merge=True)
    """
    with _draft_lock:
        if claim_id in _draft_store:
            _draft_store[claim_id].update(data)
        else:
            _draft_store[claim_id] = data


def get_draft(claim_id: str) -> Optional[dict]:
    """
    Retrieve a draft response record for a given claim ID.

    Firestore equivalent:
        doc = db.collection('draft_responses').document(claim_id).get()
        return doc.to_dict() if doc.exists else None
    """
    return _draft_store.get(claim_id)


# =============================================================================
# Utility — Clear stores (for testing)
# =============================================================================

def clear_all_stores() -> None:
    """Clear all in-memory stores. Used in tests only."""
    with _analysis_lock:
        _analysis_store.clear()
    with _draft_lock:
        _draft_store.clear()
