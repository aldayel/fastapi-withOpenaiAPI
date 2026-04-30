"""
Watheeq AI Service — Analysis Endpoint Tests

Tests for US-20 (Trigger Analysis), US-21 + US-22 (Get Analysis Results),
and the health check endpoint.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.store import save_analysis_to_memory


# =============================================================================
# Health Check Tests
# =============================================================================


@pytest.mark.asyncio
async def test_health_check(client):
    """Test that the health check endpoint returns correct status."""
    response = await client.get("/api/v1/analysis/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == "1.0.0"
    assert data["llm_provider"] == "google-gemini"
    assert "llm_model" in data


# =============================================================================
# US-20: Trigger Analysis Tests
# =============================================================================


VALID_TRIGGER_PAYLOAD = {
    "claim_id": "CLM-001",
    "patient_info": {
        "first_name": "Mohammed",
        "last_name": "Al-Qahtani",
        "date_of_birth": "1990-01-15",
    },
    "treatment_type": "Physiotherapy",
    "policy_plan_id": "PP-BASIC",
    "medical_report_url": "https://example.com/reports/medical-report.pdf",
    "policy_document_url": "https://example.com/policies/basic-plan.pdf",
    "examiner_id": "EX-001",
}


@pytest.mark.asyncio
async def test_trigger_analysis_returns_202(client):
    """US-20: Triggering analysis returns HTTP 202 Accepted."""
    response = await client.post(
        "/api/v1/analysis/trigger", json=VALID_TRIGGER_PAYLOAD
    )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "pending"
    assert data["claim_id"] == "CLM-001"
    assert "analysis_id" in data
    assert data["message"] == "AI analysis has been triggered successfully"


@pytest.mark.asyncio
async def test_trigger_analysis_missing_fields(client):
    """US-20: Triggering analysis with missing fields returns 422."""
    incomplete_payload = {
        "claim_id": "CLM-001",
        # Missing required fields
    }
    response = await client.post(
        "/api/v1/analysis/trigger", json=incomplete_payload
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_trigger_analysis_generates_unique_ids(client):
    """US-20: Each trigger generates a unique analysis_id."""
    response1 = await client.post(
        "/api/v1/analysis/trigger", json=VALID_TRIGGER_PAYLOAD
    )
    response2 = await client.post(
        "/api/v1/analysis/trigger", json=VALID_TRIGGER_PAYLOAD
    )
    assert response1.json()["analysis_id"] != response2.json()["analysis_id"]


# =============================================================================
# US-21 + US-22: Get Analysis Results Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_analysis_not_found(client):
    """US-22: Requesting analysis for non-existent claim returns 404."""
    response = await client.get("/api/v1/analysis/CLM-NONEXISTENT")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_analysis_pending(client):
    """US-22: Requesting analysis that is pending returns pending status."""
    # Manually insert a pending analysis record into memory
    save_analysis_to_memory("test-analysis-id", {
        "analysis_id": "test-analysis-id",
        "claim_id": "CLM-002",
        "status": "pending",
        "created_at": "2026-04-26T10:00:00",
    })

    response = await client.get("/api/v1/analysis/CLM-002")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"
    assert data["claim_id"] == "CLM-002"
    assert data["coverage_decision"] is None


@pytest.mark.asyncio
async def test_get_analysis_completed(client):
    """US-21 + US-22: Completed analysis returns full results with clauses."""
    save_analysis_to_memory("test-analysis-completed", {
        "analysis_id": "test-analysis-completed",
        "claim_id": "CLM-003",
        "status": "completed",
        "coverage_decision": "covered",
        "confidence_score": 0.92,
        "applicable_clauses": [
            {
                "clause_id": "Section 4.2.1",
                "clause_text": "Physiotherapy is covered under the basic plan.",
                "relevance": "Directly covers the treatment type requested.",
            }
        ],
        "reasoning": "The treatment is explicitly covered under Section 4.2.1.",
        "flags": [],
        "draft_response": "Dear patient, your claim has been approved...",
        "ai_model_used": "gemini-3.1-flash-lite-preview",
        "processing_time_seconds": 12.5,
        "created_at": "2026-04-26T10:00:00",
        "completed_at": "2026-04-26T10:00:12",
    })

    response = await client.get("/api/v1/analysis/CLM-003")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["coverage_decision"] == "covered"
    assert data["confidence_score"] == 0.92
    assert len(data["applicable_clauses"]) == 1
    assert data["applicable_clauses"][0]["clause_id"] == "Section 4.2.1"
    assert data["reasoning"] is not None
    assert data["draft_response"] is not None
    assert "disclaimer" in data
    assert "AI-assisted" in data["disclaimer"]


@pytest.mark.asyncio
async def test_get_analysis_failed(client):
    """US-22: Failed analysis returns error details."""
    save_analysis_to_memory("test-analysis-failed", {
        "analysis_id": "test-analysis-failed",
        "claim_id": "CLM-004",
        "status": "failed",
        "error_message": "PDF extraction failed: file not found",
        "created_at": "2026-04-26T10:00:00",
        "completed_at": "2026-04-26T10:00:05",
    })

    response = await client.get("/api/v1/analysis/CLM-004")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert data["error_message"] is not None


# =============================================================================
# Root Endpoint Test
# =============================================================================


@pytest.mark.asyncio
async def test_root_endpoint(client):
    """Test the root endpoint returns service information."""
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Watheeq AI Analysis Service"
    assert "docs" in data
