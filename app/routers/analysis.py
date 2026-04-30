"""
Watheeq AI Service — Analysis Router

THIN endpoint layer — handles HTTP concerns ONLY (validation, status codes, auth).
ALL business logic lives in the service layer (analysis_service.py).

Endpoints:
  POST /trigger     — US-20: Trigger AI analysis for a claim
  GET  /{claim_id}  — US-21 + US-22: Get analysis results
  GET  /health      — Health check
"""

from http import HTTPStatus
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.config import settings
from app.dependencies import verify_bearer_token
from app.schemas.analysis import (
    AnalysisResultResponse,
    AnalysisTriggerRequest,
    AnalysisTriggerResponse,
    HealthCheckResponse,
)
from app.services import analysis_service
from app.utils.exceptions import AnalysisNotFoundError

router = APIRouter()


# =============================================================================
# POST /trigger — US-20: Trigger AI Analysis
# =============================================================================


@router.post(
    "/trigger",
    response_model=AnalysisTriggerResponse,
    status_code=HTTPStatus.ACCEPTED,
    summary="Trigger AI analysis for a claim",
    description=(
        "Initiates asynchronous AI analysis when a Claims Examiner picks a claim. "
        "Returns immediately with HTTP 202 and an analysis_id for tracking. "
        "The analysis runs in the background and results can be polled via GET /{claim_id}."
    ),
    dependencies=[Depends(verify_bearer_token)],
)
async def trigger_analysis(
    data: AnalysisTriggerRequest,
    background_tasks: BackgroundTasks,
) -> AnalysisTriggerResponse:
    """
    Trigger AI analysis for a claim (US-20).

    This endpoint:
    1. Validates the incoming request data (via Pydantic schema)
    2. Generates a unique analysis_id
    3. Queues the analysis as a background task
    4. Returns HTTP 202 immediately
    """
    analysis_id = str(uuid4())

    # Queue the analysis as a background task
    background_tasks.add_task(
        analysis_service.process_claim_analysis,
        analysis_id=analysis_id,
        claim_data=data,
    )

    return AnalysisTriggerResponse(
        analysis_id=analysis_id,
        claim_id=data.claim_id,
        status="pending",
        message="AI analysis has been triggered successfully",
    )


# =============================================================================
# GET /health -- Health Check
# =============================================================================


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    summary="Service health check",
    description="Returns the service health status and configuration.",
)
async def health_check() -> HealthCheckResponse:
    """Health check endpoint -- no authentication required."""
    return HealthCheckResponse(
        status="healthy",
        version="1.0.0",
        llm_provider="google-gemini",
        llm_model=settings.LLM_MODEL,
    )


# =============================================================================
# GET /{claim_id} — US-21 + US-22: Get Analysis Results
# =============================================================================


@router.get(
    "/{claim_id}",
    response_model=AnalysisResultResponse,
    summary="Get AI analysis results for a claim",
    description=(
        "Returns the AI analysis results including coverage decision, "
        "applicable policy clauses with citations, reasoning, and draft response. "
        "Results are cached in memory only (stateless architecture). "
        "If the service has restarted, results may not be available — "
        "use the aiDecision/aiMessage fields on the claim document instead."
    ),
    dependencies=[Depends(verify_bearer_token)],
)
async def get_analysis_results(claim_id: str) -> AnalysisResultResponse:
    """
    Get AI analysis results for a claim (US-21 + US-22).

    Results are retrieved from in-memory cache (stateless — no Firestore).
    """
    try:
        data = analysis_service.get_analysis_result(claim_id)
    except AnalysisNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=e.message,
        )

    # Build the response from cached data
    applicable_clauses = None
    if data.get("applicable_clauses"):
        from app.schemas.analysis import ApplicableClause

        applicable_clauses = [
            ApplicableClause(
                clause_id=c.get("clause_id", ""),
                clause_text=c.get("clause_text", ""),
                relevance=c.get("relevance", ""),
            )
            for c in data["applicable_clauses"]
        ]

    return AnalysisResultResponse(
        analysis_id=data.get("analysis_id", ""),
        claim_id=data.get("claim_id", claim_id),
        status=data.get("status", "unknown"),
        coverage_decision=data.get("coverage_decision"),
        confidence_score=data.get("confidence_score"),
        applicable_clauses=applicable_clauses,
        reasoning=data.get("reasoning"),
        flags=data.get("flags"),
        draft_response=data.get("draft_response"),
        ai_model_used=data.get("ai_model_used"),
        processing_time_seconds=data.get("processing_time_seconds"),
        created_at=data.get("created_at"),
        completed_at=data.get("completed_at"),
        error_message=data.get("error_message"),
    )
