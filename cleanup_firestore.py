"""
Cleanup script: Delete ai_analyses and ai_drafts collections from Firestore.
Also clears the aiMessage field from claim documents (since it currently contains
the draft letter instead of the reasoning).

Run once to clean up test data.
"""

import firebase_admin
from firebase_admin import credentials, firestore


def delete_collection(db, collection_name, batch_size=100):
    """Delete all documents in a Firestore collection."""
    coll_ref = db.collection(collection_name)
    docs = coll_ref.limit(batch_size).stream()
    
    deleted = 0
    for doc in docs:
        doc.reference.delete()
        deleted += 1
    
    if deleted >= batch_size:
        # Recurse if there might be more
        return deleted + delete_collection(db, collection_name, batch_size)
    
    return deleted


def clear_ai_fields_from_claims(db):
    """Remove aiMessage from claims (will be re-written with correct reasoning on next analysis)."""
    claims_ref = db.collection("claims")
    docs = claims_ref.stream()
    
    updated = 0
    for doc in docs:
        data = doc.to_dict()
        if "aiMessage" in data or "aiDecision" in data:
            # Delete the fields so they can be re-written correctly
            doc.reference.update({
                "aiDecision": firestore.DELETE_FIELD,
                "aiMessage": firestore.DELETE_FIELD,
            })
            updated += 1
            print(f"  Cleared aiDecision/aiMessage from claim: {doc.id}")
    
    return updated


def main():
    # Initialize Firebase
    cred = credentials.Certificate("firebase-credentials.json")
    firebase_admin.initialize_app(cred, {"projectId": "watheeqai-2"})
    db = firestore.client()
    
    print("=" * 60)
    print("Watheeq AI — Firestore Cleanup")
    print("=" * 60)
    
    # Delete ai_analyses collection
    print("\n1. Deleting 'ai_analyses' collection...")
    count = delete_collection(db, "ai_analyses")
    print(f"   Deleted {count} documents from ai_analyses")
    
    # Delete ai_drafts collection
    print("\n2. Deleting 'ai_drafts' collection...")
    count = delete_collection(db, "ai_drafts")
    print(f"   Deleted {count} documents from ai_drafts")
    
    # Clear AI fields from claims (they contain wrong data — draft letter instead of reasoning)
    print("\n3. Clearing incorrect aiDecision/aiMessage from claims...")
    count = clear_ai_fields_from_claims(db)
    print(f"   Cleared AI fields from {count} claim documents")
    
    print("\n" + "=" * 60)
    print("Cleanup complete!")
    print("The ai_analyses and ai_drafts collections have been removed.")
    print("AI fields on claims have been cleared (will be re-written correctly on next analysis).")
    print("=" * 60)


if __name__ == "__main__":
    main()
