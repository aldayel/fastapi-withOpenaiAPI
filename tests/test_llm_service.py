"""
Watheeq AI Service — LLM and PDF Service Tests

Unit tests for the service layer including LLM response parsing,
PDF text extraction, and in-memory store logic.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.analysis_service import _parse_llm_response
from app.utils.prompts import build_analysis_prompt, build_draft_response_prompt
from app.utils.exceptions import LLMResponseParsingError


# =============================================================================
# LLM Response Parsing Tests
# =============================================================================


class TestParseLLMResponse:
    """Tests for the _parse_llm_response validation function."""

    def test_valid_covered_response(self):
        """Valid LLM response with 'covered' decision parses correctly."""
        response = {
            "coverage_decision": "covered",
            "confidence_score": 0.95,
            "applicable_clauses": [
                {
                    "clause_id": "Section 4.2.1",
                    "clause_text": "Physiotherapy is covered.",
                    "relevance": "Directly applicable.",
                }
            ],
            "reasoning": "The treatment is covered under the basic plan.",
            "flags": [],
        }
        result = _parse_llm_response(response)
        assert result["coverage_decision"] == "covered"
        assert result["confidence_score"] == 0.95
        assert len(result["applicable_clauses"]) == 1
        assert "recommended_action" not in result

    def test_valid_not_covered_response(self):
        """Valid LLM response with 'not_covered' decision parses correctly."""
        response = {
            "coverage_decision": "not_covered",
            "confidence_score": 0.88,
            "applicable_clauses": [],
            "reasoning": "Treatment not listed in policy.",
            "flags": ["Treatment type not found in policy"],
        }
        result = _parse_llm_response(response)
        assert result["coverage_decision"] == "not_covered"
        assert "recommended_action" not in result

    def test_partial_is_now_invalid(self):
        """'partial' is no longer a valid decision — only covered/not_covered."""
        response = {
            "coverage_decision": "partial",
            "confidence_score": 0.65,
            "applicable_clauses": [],
            "reasoning": "Partially covered.",
            "flags": [],
        }
        with pytest.raises(LLMResponseParsingError):
            _parse_llm_response(response)

    def test_invalid_coverage_decision(self):
        """Invalid coverage_decision raises LLMResponseParsingError."""
        response = {
            "coverage_decision": "maybe",
            "confidence_score": 0.5,
            "applicable_clauses": [],
            "reasoning": "Uncertain.",
        }
        with pytest.raises(LLMResponseParsingError):
            _parse_llm_response(response)

    def test_confidence_score_clamped(self):
        """Confidence score outside 0-1 range is clamped."""
        response = {
            "coverage_decision": "covered",
            "confidence_score": 1.5,
            "applicable_clauses": [],
            "reasoning": "High confidence.",
        }
        result = _parse_llm_response(response)
        assert result["confidence_score"] == 1.0

    def test_confidence_score_negative_clamped(self):
        """Negative confidence score is clamped to 0."""
        response = {
            "coverage_decision": "covered",
            "confidence_score": -0.5,
            "applicable_clauses": [],
            "reasoning": "Low confidence.",
        }
        result = _parse_llm_response(response)
        assert result["confidence_score"] == 0.0

    def test_missing_optional_fields_have_defaults(self):
        """Missing optional fields get sensible defaults."""
        response = {
            "coverage_decision": "covered",
        }
        result = _parse_llm_response(response)
        assert result["confidence_score"] is None
        assert result["applicable_clauses"] == []
        assert result["reasoning"] == "No reasoning provided"
        assert result["flags"] == []

    def test_recommended_action_in_llm_output_is_ignored(self):
        """Even if the LLM returns recommended_action, it is not in the parsed result."""
        response = {
            "coverage_decision": "covered",
            "confidence_score": 0.9,
            "applicable_clauses": [],
            "reasoning": "Covered.",
            "flags": [],
            "recommended_action": "approve",
        }
        result = _parse_llm_response(response)
        assert "recommended_action" not in result


# =============================================================================
# Prompt Building Tests
# =============================================================================


class TestPromptBuilding:
    """Tests for prompt template functions."""

    def test_build_analysis_prompt(self):
        """Analysis prompt includes all patient and document data."""
        prompt = build_analysis_prompt(
            claim_id="CLM-TEST-001",
            patient_info={
                "first_name": "Mohammed",
                "last_name": "Al-Qahtani",
                "date_of_birth": "1990-01-15",
            },
            treatment_type="Physiotherapy",
            medical_report_text="Patient requires 10 sessions of physiotherapy.",
            policy_document_text="Section 4.2: Physiotherapy is covered up to 20 sessions.",
        )
        assert "CLM-TEST-001" in prompt
        assert "Mohammed" in prompt
        assert "Al-Qahtani" in prompt
        assert "1990-01-15" in prompt
        assert "Physiotherapy" in prompt
        assert "10 sessions" in prompt
        assert "Section 4.2" in prompt

    def test_build_analysis_prompt_missing_data(self):
        """Analysis prompt handles missing data gracefully."""
        prompt = build_analysis_prompt(
            claim_id="CLM-MISSING-001",
            patient_info={},
            treatment_type="Surgery",
            medical_report_text="",
            policy_document_text="",
        )
        assert "N/A" in prompt
        assert "Surgery" in prompt
        assert "No medical report text available" in prompt

    def test_build_draft_response_prompt(self):
        """Draft response prompt includes analysis results."""
        prompt = build_draft_response_prompt(
            patient_info={"first_name": "Ahmed", "last_name": "Hassan"},
            treatment_type="Dental",
            coverage_decision="covered",
            reasoning="Dental care is covered under the premium plan.",
            applicable_clauses=[
                {
                    "clause_id": "Section 5.1",
                    "clause_text": "Dental procedures covered.",
                    "relevance": "Directly applicable.",
                }
            ],
            flags=[],
        )
        assert "Ahmed" in prompt
        assert "Dental" in prompt
        assert "covered" in prompt
        assert "Section 5.1" in prompt

    def test_build_draft_response_prompt_no_clauses(self):
        """Draft response prompt handles empty clauses list."""
        prompt = build_draft_response_prompt(
            patient_info={"first_name": "Sara", "last_name": "Ali"},
            treatment_type="MRI",
            coverage_decision="not_covered",
            reasoning="MRI not in policy.",
            applicable_clauses=[],
            flags=["No matching clauses found"],
        )
        assert "No specific clauses identified" in prompt
        assert "No matching clauses found" in prompt


# =============================================================================
# PDF Service Tests (Unit)
# =============================================================================


class TestPDFService:
    """Unit tests for PDF service text extraction."""

    @pytest.mark.asyncio
    async def test_extract_text_from_local_file(self, tmp_path):
        """PDF extraction from a local file works correctly."""
        import fitz

        # Create a simple test PDF
        pdf_path = tmp_path / "test.pdf"
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "This is a test medical report.")
        doc.save(str(pdf_path))
        doc.close()

        from app.services.pdf_service import extract_text

        text = await extract_text(str(pdf_path))
        assert "test medical report" in text

    @pytest.mark.asyncio
    async def test_extract_text_file_not_found(self):
        """PDF extraction raises error for non-existent file."""
        from app.services.pdf_service import extract_text
        from app.utils.exceptions import PDFExtractionError

        with pytest.raises(PDFExtractionError):
            await extract_text("/nonexistent/path/to/file.pdf")

    @pytest.mark.asyncio
    async def test_extract_text_from_base64(self):
        """PDF extraction from base64-encoded string works."""
        import fitz
        import base64
        from io import BytesIO

        # Create a PDF in memory and encode as base64
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Base64 encoded report content.")
        pdf_bytes = doc.tobytes()
        doc.close()

        b64_string = base64.b64encode(pdf_bytes).decode("utf-8")

        from app.services.pdf_service import extract_text

        text = await extract_text(b64_string)
        assert "Base64 encoded report content" in text


# =============================================================================
# Store Tests (In-Memory)
# =============================================================================


class TestStore:
    """Tests for the in-memory data store."""

    def test_save_and_get_analysis(self):
        """Save and retrieve an analysis record from memory."""
        from app.services.store import save_analysis_to_memory, get_analysis_from_memory

        save_analysis_to_memory("A-001", {"claim_id": "C-001", "status": "pending"})
        result = get_analysis_from_memory("C-001")
        assert result is not None
        assert result["claim_id"] == "C-001"

    def test_get_analysis_not_found(self):
        """Get returns None for non-existent analysis."""
        from app.services.store import get_analysis_from_memory

        result = get_analysis_from_memory("NONEXISTENT")
        assert result is None

    def test_save_and_get_draft(self):
        """Save and retrieve a draft response from memory."""
        from app.services.response_service import _save_draft_to_memory, _get_draft_from_memory

        _save_draft_to_memory("C-010", {"claim_id": "C-010", "original_draft": "Draft text"})
        result = _get_draft_from_memory("C-010")
        assert result is not None
        assert result["original_draft"] == "Draft text"

    def test_update_analysis(self):
        """Updating an analysis replaces the record in memory."""
        from app.services.store import save_analysis_to_memory, get_analysis_from_memory

        save_analysis_to_memory("A-003", {"claim_id": "C-003", "status": "pending"})
        save_analysis_to_memory("A-003-v2", {"claim_id": "C-003", "status": "completed", "coverage_decision": "covered"})
        result = get_analysis_from_memory("C-003")
        assert result["status"] == "completed"
        assert result["coverage_decision"] == "covered"
