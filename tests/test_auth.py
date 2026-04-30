"""
Watheeq AI Service — Authentication Tests

Tests for Bearer token authentication (NFR-05).
"""

import pytest
from unittest.mock import patch

from app.services.response_service import _save_draft_to_memory


# =============================================================================
# Bearer Token Authentication Tests
# =============================================================================


@pytest.mark.asyncio
async def test_health_check_no_auth_required(client):
    """Health check endpoint does not require authentication."""
    response = await client.get("/api/v1/analysis/health")
    assert response.status_code == 200


@pytest.mark.asyncio
@patch("app.config.settings.BEARER_TOKEN", "test-secret-token")
async def test_trigger_with_valid_token(client):
    """Trigger endpoint accepts valid bearer token."""
    payload = {
        "claim_id": "CLM-AUTH-001",
        "patient_info": {
            "first_name": "Test",
            "last_name": "User",
            "date_of_birth": "1990-01-01",
        },
        "treatment_type": "Checkup",
        "policy_plan_id": "PP-001",
        "medical_report_url": "https://example.com/report.pdf",
        "policy_document_url": "https://example.com/policy.pdf",
        "examiner_id": "EX-001",
    }
    response = await client.post(
        "/api/v1/analysis/trigger",
        json=payload,
        headers={"Authorization": "Bearer test-secret-token"},
    )
    assert response.status_code == 202


@pytest.mark.asyncio
@patch("app.config.settings.BEARER_TOKEN", "test-secret-token")
async def test_trigger_with_invalid_token(client):
    """Trigger endpoint rejects invalid bearer token."""
    payload = {
        "claim_id": "CLM-AUTH-002",
        "patient_info": {
            "first_name": "Test",
            "last_name": "User",
            "date_of_birth": "1990-01-01",
        },
        "treatment_type": "Checkup",
        "policy_plan_id": "PP-001",
        "medical_report_url": "https://example.com/report.pdf",
        "policy_document_url": "https://example.com/policy.pdf",
        "examiner_id": "EX-001",
    }
    response = await client.post(
        "/api/v1/analysis/trigger",
        json=payload,
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
@patch("app.config.settings.BEARER_TOKEN", "test-secret-token")
async def test_trigger_without_token(client):
    """Trigger endpoint rejects request without token when auth is enabled."""
    payload = {
        "claim_id": "CLM-AUTH-003",
        "patient_info": {
            "first_name": "Test",
            "last_name": "User",
            "date_of_birth": "1990-01-01",
        },
        "treatment_type": "Checkup",
        "policy_plan_id": "PP-001",
        "medical_report_url": "https://example.com/report.pdf",
        "policy_document_url": "https://example.com/policy.pdf",
        "examiner_id": "EX-001",
    }
    response = await client.post(
        "/api/v1/analysis/trigger",
        json=payload,
    )
    assert response.status_code == 401


@pytest.mark.asyncio
@patch("app.config.settings.BEARER_TOKEN", "test-secret-token")
async def test_get_draft_with_valid_token(client):
    """Draft endpoint accepts valid bearer token."""
    _save_draft_to_memory("CLM-AUTH-010", {
        "claim_id": "CLM-AUTH-010",
        "original_draft": "Test draft.",
        "current_draft": "Test draft.",
        "is_edited": False,
        "generated_at": "2026-04-26T10:00:00",
    })
    response = await client.get(
        "/api/v1/responses/CLM-AUTH-010/draft",
        headers={"Authorization": "Bearer test-secret-token"},
    )
    assert response.status_code == 200
