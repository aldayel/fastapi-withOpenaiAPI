"""
Watheeq AI Service — Response Endpoint Tests

Tests for US-23 (Get Draft Response) and US-24 (Edit Draft Response).
Drafts are stored in memory only (stateless architecture).
"""

import pytest
from datetime import datetime

from app.services.response_service import _save_draft_to_memory


# =============================================================================
# US-23: Get Draft Response Tests
# =============================================================================


@pytest.mark.asyncio
async def test_get_draft_not_found(client):
    """US-23: Requesting draft for non-existent claim returns 404."""
    response = await client.get("/api/v1/responses/CLM-NONEXISTENT/draft")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_draft_success(client):
    """US-23: Retrieving an existing draft returns full data."""
    _save_draft_to_memory("CLM-010", {
        "claim_id": "CLM-010",
        "original_draft": "Dear patient, your claim for Physiotherapy has been reviewed...",
        "current_draft": "Dear patient, your claim for Physiotherapy has been reviewed...",
        "is_edited": False,
        "generated_at": "2026-04-26T10:00:00",
        "last_edited_at": None,
        "last_edited_by": None,
    })

    response = await client.get("/api/v1/responses/CLM-010/draft")
    assert response.status_code == 200
    data = response.json()
    assert data["claim_id"] == "CLM-010"
    assert data["original_draft"] == data["current_draft"]
    assert data["is_edited"] is False
    assert "disclaimer" in data


@pytest.mark.asyncio
async def test_get_draft_edited(client):
    """US-23: Retrieving an edited draft shows both original and current."""
    _save_draft_to_memory("CLM-011", {
        "claim_id": "CLM-011",
        "original_draft": "Original AI draft text here.",
        "current_draft": "Edited version by examiner.",
        "is_edited": True,
        "generated_at": "2026-04-26T10:00:00",
        "last_edited_at": "2026-04-26T11:00:00",
        "last_edited_by": "EX-001",
    })

    response = await client.get("/api/v1/responses/CLM-011/draft")
    assert response.status_code == 200
    data = response.json()
    assert data["is_edited"] is True
    assert data["original_draft"] != data["current_draft"]
    assert data["current_draft"] == "Edited version by examiner."
    assert data["last_edited_by"] == "EX-001"


# =============================================================================
# US-24: Edit Draft Response Tests
# =============================================================================


@pytest.mark.asyncio
async def test_edit_draft_not_found(client):
    """US-24: Editing draft for non-existent claim returns 404."""
    response = await client.put(
        "/api/v1/responses/CLM-NONEXISTENT/draft",
        json={
            "edited_response": "New text",
            "examiner_id": "EX-001",
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_edit_draft_success(client):
    """US-24: Successfully editing a draft updates current_draft."""
    _save_draft_to_memory("CLM-020", {
        "claim_id": "CLM-020",
        "original_draft": "Original AI draft for CLM-020.",
        "current_draft": "Original AI draft for CLM-020.",
        "is_edited": False,
        "generated_at": "2026-04-26T10:00:00",
        "last_edited_at": None,
        "last_edited_by": None,
    })

    response = await client.put(
        "/api/v1/responses/CLM-020/draft",
        json={
            "edited_response": "Examiner's revised response text.",
            "examiner_id": "EX-002",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["claim_id"] == "CLM-020"
    assert data["current_draft"] == "Examiner's revised response text."
    assert data["is_edited"] is True
    assert data["last_edited_by"] == "EX-002"
    assert data["last_edited_at"] is not None


@pytest.mark.asyncio
async def test_edit_draft_preserves_original(client):
    """US-24: Editing preserves the original AI draft for audit."""
    _save_draft_to_memory("CLM-021", {
        "claim_id": "CLM-021",
        "original_draft": "Original AI draft that should be preserved.",
        "current_draft": "Original AI draft that should be preserved.",
        "is_edited": False,
        "generated_at": "2026-04-26T10:00:00",
        "last_edited_at": None,
        "last_edited_by": None,
    })

    # Edit the draft
    await client.put(
        "/api/v1/responses/CLM-021/draft",
        json={
            "edited_response": "Completely new text.",
            "examiner_id": "EX-003",
        },
    )

    # Retrieve and verify original is preserved
    response = await client.get("/api/v1/responses/CLM-021/draft")
    data = response.json()
    assert data["original_draft"] == "Original AI draft that should be preserved."
    assert data["current_draft"] == "Completely new text."


@pytest.mark.asyncio
async def test_edit_draft_missing_fields(client):
    """US-24: Editing with missing fields returns 422."""
    response = await client.put(
        "/api/v1/responses/CLM-020/draft",
        json={
            # Missing examiner_id
            "edited_response": "Some text",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_edit_draft_multiple_times(client):
    """US-24: Draft can be edited multiple times, always preserving original."""
    _save_draft_to_memory("CLM-022", {
        "claim_id": "CLM-022",
        "original_draft": "First AI draft.",
        "current_draft": "First AI draft.",
        "is_edited": False,
        "generated_at": "2026-04-26T10:00:00",
        "last_edited_at": None,
        "last_edited_by": None,
    })

    # First edit
    await client.put(
        "/api/v1/responses/CLM-022/draft",
        json={"edited_response": "Second version.", "examiner_id": "EX-001"},
    )

    # Second edit
    response = await client.put(
        "/api/v1/responses/CLM-022/draft",
        json={"edited_response": "Third version.", "examiner_id": "EX-002"},
    )
    data = response.json()
    assert data["current_draft"] == "Third version."
    assert data["last_edited_by"] == "EX-002"

    # Verify original is still preserved
    get_response = await client.get("/api/v1/responses/CLM-022/draft")
    get_data = get_response.json()
    assert get_data["original_draft"] == "First AI draft."
