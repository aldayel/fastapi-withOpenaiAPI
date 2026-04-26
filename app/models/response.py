"""
Watheeq AI Service — Response Domain Models

Internal data models representing draft response records in the store.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class DraftResponseRecord:
    """
    Draft response record stored in the data store.

    Preserves both the original AI-generated draft and any edits
    made by the Claims Examiner, supporting audit comparison (US-24).
    """

    claim_id: str
    original_draft: str
    current_draft: str
    is_edited: bool = False
    generated_at: datetime = field(default_factory=datetime.utcnow)
    last_edited_at: Optional[datetime] = None
    last_edited_by: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "claim_id": self.claim_id,
            "original_draft": self.original_draft,
            "current_draft": self.current_draft,
            "is_edited": self.is_edited,
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "last_edited_at": self.last_edited_at.isoformat() if self.last_edited_at else None,
            "last_edited_by": self.last_edited_by,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DraftResponseRecord":
        """Create a DraftResponseRecord from a dictionary."""
        generated_at = data.get("generated_at")
        if isinstance(generated_at, str):
            generated_at = datetime.fromisoformat(generated_at)

        last_edited_at = data.get("last_edited_at")
        if isinstance(last_edited_at, str):
            last_edited_at = datetime.fromisoformat(last_edited_at)

        return cls(
            claim_id=data["claim_id"],
            original_draft=data["original_draft"],
            current_draft=data["current_draft"],
            is_edited=data.get("is_edited", False),
            generated_at=generated_at or datetime.utcnow(),
            last_edited_at=last_edited_at,
            last_edited_by=data.get("last_edited_by"),
        )
