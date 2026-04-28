"""
Watheeq AI Service — Analysis Schemas

Pydantic models for request validation and response serialization
for the analysis endpoints (US-20, US-21, US-22).
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# =============================================================================
# Request Schemas
# =============================================================================


class PatientInfo(BaseModel):
    """Patient information included in a claim."""

    first_name: str = Field(..., description="Patient's first name")
    last_name: str = Field(..., description="Patient's last name")
    date_of_birth: str = Field(
        ..., description="Patient's date of birth (YYYY-MM-DD)"
    )


class AnalysisTriggerRequest(BaseModel):
    """
    Request body for POST /api/v1/analysis/trigger (US-20).

    Sent by the main Watheeq application when a Claims Examiner
    picks a claim for review, triggering AI analysis.
    """

    claim_id: str = Field(..., description="Unique identifier of the claim")
    patient_info: PatientInfo = Field(..., description="Patient demographics")
    treatment_type: str = Field(
        ..., description="Type of treatment (e.g., Physiotherapy, Surgery)"
    )
    policy_plan_id: str = Field(..., description="ID of the insurance policy plan")
    medical_report_url: str = Field(
        ...,
        description="URL to the medical report PDF (Firebase Storage URL or base64)",
    )
    policy_document_url: str = Field(
        ...,
        description="URL to the policy document PDF (Firebase Storage URL or base64)",
    )
    examiner_id: str = Field(
        ..., description="ID of the Claims Examiner who triggered the analysis"
    )


# =============================================================================
# Response Schemas
# =============================================================================


class AnalysisTriggerResponse(BaseModel):
    """
    Response for POST /api/v1/analysis/trigger (US-20).

    Returned immediately (HTTP 202) to confirm the analysis has been queued.
    """

    analysis_id: str = Field(..., description="Unique ID for this analysis run")
    claim_id: str = Field(..., description="The claim being analyzed")
    status: str = Field(
        default="pending",
        description="Current analysis status: pending | processing | completed | failed",
    )
    message: str = Field(
        default="AI analysis has been triggered successfully",
        description="Human-readable status message",
    )


class ApplicableClause(BaseModel):
    """A single policy clause identified as relevant to the claim."""

    clause_id: str = Field(
        ..., description="Clause identifier (e.g., Section 4.2.1)"
    )
    clause_text: str = Field(
        ..., description="Exact quoted text from the policy document"
    )
    relevance: str = Field(
        ..., description="Explanation of why this clause applies"
    )


class AnalysisResultResponse(BaseModel):
    """
    Response for GET /api/v1/analysis/{claim_id} (US-21 + US-22).

    Contains the full AI analysis results including coverage decision,
    cited policy clauses, reasoning, and the draft response.
    """

    analysis_id: str = Field(..., description="Unique ID for this analysis run")
    claim_id: str = Field(..., description="The claim that was analyzed")
    status: str = Field(
        ...,
        description="Analysis status: pending | processing | completed | failed",
    )
    coverage_decision: Optional[str] = Field(
        default=None,
        description="AI coverage determination: covered | not_covered",
    )
    confidence_score: Optional[float] = Field(
        default=None, description="AI confidence score (0.0 to 1.0)"
    )
    applicable_clauses: Optional[List[ApplicableClause]] = Field(
        default=None, description="Policy clauses cited by the AI"
    )
    reasoning: Optional[str] = Field(
        default=None, description="AI justification for the coverage decision"
    )
    flags: Optional[List[str]] = Field(
        default=None,
        description="Concerns or items flagged for manual review",
    )
    draft_response: Optional[str] = Field(
        default=None, description="AI-generated draft response message for the claimant"
    )
    ai_model_used: Optional[str] = Field(
        default=None, description="LLM model used for analysis"
    )
    processing_time_seconds: Optional[float] = Field(
        default=None, description="Total processing time in seconds"
    )
    created_at: Optional[datetime] = Field(
        default=None, description="Timestamp when analysis was triggered"
    )
    completed_at: Optional[datetime] = Field(
        default=None, description="Timestamp when analysis completed"
    )
    error_message: Optional[str] = Field(
        default=None, description="Error details if analysis failed"
    )
    disclaimer: str = Field(
        default="This is an AI-assisted analysis. Final decision requires human review.",
        description="HITL disclaimer — all AI outputs are recommendations only",
    )


class HealthCheckResponse(BaseModel):
    """Response for GET /api/v1/health."""

    status: str = Field(default="healthy")
    version: str = Field(default="1.0.0")
    llm_provider: str = Field(default="openai")
    llm_model: str
