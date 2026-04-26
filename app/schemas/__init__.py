"""Watheeq AI Service — Schema Exports."""

from app.schemas.analysis import (
    AnalysisResultResponse,
    AnalysisTriggerRequest,
    AnalysisTriggerResponse,
    ApplicableClause,
    HealthCheckResponse,
    PatientInfo,
)
from app.schemas.responses import (
    DraftResponseResult,
    EditDraftRequest,
    EditDraftResponse,
)

__all__ = [
    "AnalysisResultResponse",
    "AnalysisTriggerRequest",
    "AnalysisTriggerResponse",
    "ApplicableClause",
    "HealthCheckResponse",
    "PatientInfo",
    "DraftResponseResult",
    "EditDraftRequest",
    "EditDraftResponse",
]
