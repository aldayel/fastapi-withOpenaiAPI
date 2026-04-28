"""
Watheeq AI Service — Analysis Domain Models

Internal data models representing analysis records in the store.
These are NOT Pydantic schemas — they define the shape of stored data.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class StoredClause:
    """A policy clause stored as part of an analysis result."""

    clause_id: str
    clause_text: str
    relevance: str


@dataclass
class AnalysisRecord:
    """
    Complete analysis record stored in the data store.

    This represents the full lifecycle of a single AI analysis run,
    from trigger through completion or failure.
    """

    analysis_id: str
    claim_id: str
    examiner_id: str
    status: str = "pending"  # pending | processing | completed | failed

    # Input data (stored for audit trail)
    patient_info: Optional[dict] = None
    treatment_type: Optional[str] = None
    policy_plan_id: Optional[str] = None

    # AI results (populated on completion)
    coverage_decision: Optional[str] = None  # covered | not_covered
    confidence_score: Optional[float] = None
    applicable_clauses: Optional[List[StoredClause]] = None
    reasoning: Optional[str] = None
    flags: Optional[List[str]] = None

    # Draft response
    draft_response: Optional[str] = None

    # Metadata
    ai_model_used: Optional[str] = None
    processing_time_seconds: Optional[float] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        clauses = None
        if self.applicable_clauses:
            clauses = [
                {
                    "clause_id": c.clause_id,
                    "clause_text": c.clause_text,
                    "relevance": c.relevance,
                }
                for c in self.applicable_clauses
            ]

        return {
            "analysis_id": self.analysis_id,
            "claim_id": self.claim_id,
            "examiner_id": self.examiner_id,
            "status": self.status,
            "patient_info": self.patient_info,
            "treatment_type": self.treatment_type,
            "policy_plan_id": self.policy_plan_id,
            "coverage_decision": self.coverage_decision,
            "confidence_score": self.confidence_score,
            "applicable_clauses": clauses,
            "reasoning": self.reasoning,
            "flags": self.flags,
            "draft_response": self.draft_response,
            "ai_model_used": self.ai_model_used,
            "processing_time_seconds": self.processing_time_seconds,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AnalysisRecord":
        """Create an AnalysisRecord from a dictionary."""
        clauses = None
        if data.get("applicable_clauses"):
            clauses = [
                StoredClause(
                    clause_id=c["clause_id"],
                    clause_text=c["clause_text"],
                    relevance=c["relevance"],
                )
                for c in data["applicable_clauses"]
            ]

        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        completed_at = data.get("completed_at")
        if isinstance(completed_at, str):
            completed_at = datetime.fromisoformat(completed_at)

        return cls(
            analysis_id=data["analysis_id"],
            claim_id=data["claim_id"],
            examiner_id=data.get("examiner_id", ""),
            status=data.get("status", "pending"),
            patient_info=data.get("patient_info"),
            treatment_type=data.get("treatment_type"),
            policy_plan_id=data.get("policy_plan_id"),
            coverage_decision=data.get("coverage_decision"),
            confidence_score=data.get("confidence_score"),
            applicable_clauses=clauses,
            reasoning=data.get("reasoning"),
            flags=data.get("flags"),
            draft_response=data.get("draft_response"),
            ai_model_used=data.get("ai_model_used"),
            processing_time_seconds=data.get("processing_time_seconds"),
            created_at=created_at or datetime.utcnow(),
            completed_at=completed_at,
            error_message=data.get("error_message"),
        )
