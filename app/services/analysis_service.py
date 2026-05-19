"""
Watheeq AI Service — Analysis Service (THE CORE)

Orchestrates the full AI claim analysis pipeline (US-20, US-21):
  1. Resolve PDF URLs from Firestore if not provided
  2. Extract text from medical report PDF
  3. Extract text from policy document PDF
  4. Extract text from supporting documents (if any)
  5. Build structured prompt (FR-34: all 6 required fields)
  6. Call Gemini LLM API
  7. Parse and validate LLM response (enforce hard-rejection rules)
  8. Generate draft response (US-23)
  9. Write aiDecision + aiMessage (reasoning) to the claims collection
  10. Cache results in memory for GET endpoint retrieval

STATELESS: No ai_analyses or ai_drafts Firestore collections.
Only writes aiDecision and aiMessage to the existing claim document.

HARD-REJECTION RULES (enforced in prompt + validated in parser):
  - Identity mismatch (name or DOB) → always not_covered
  - Claimed amount exceeds policy limit → always not_covered
  - Treatment not covered by policy → always not_covered
  - Missing/invalid documentation → always not_covered
  - Claim conditions not met → always not_covered
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Optional

from app.config import settings
from app.schemas.analysis import AnalysisTriggerRequest
from app.services import llm_service, pdf_service, response_service
from app.services.store import (
    save_analysis_to_memory,
    get_analysis_from_memory,
    update_claim_with_ai_result,
    get_claim,
    get_policy_by_name,
)
from app.utils.exceptions import (
    AnalysisNotFoundError,
    LLMResponseParsingError,
    LLMServiceError,
    PDFDownloadError,
    PDFExtractionError,
)
from app.utils.prompts import CLAIM_ANALYSIS_SYSTEM_PROMPT, build_analysis_prompt

logger = logging.getLogger(__name__)


async def process_claim_analysis(
    analysis_id: str,
    claim_data: AnalysisTriggerRequest,
) -> None:
    """
    Core AI analysis pipeline — runs as a FastAPI BackgroundTask.

    Orchestrates the entire analysis workflow with a configurable timeout.
    If the analysis exceeds ANALYSIS_TIMEOUT_SECONDS, it is marked as failed.

    Args:
        analysis_id: Unique identifier for this analysis run.
        claim_data: Validated request data from the trigger endpoint.
    """
    start_time = time.time()

    # Initialize in-memory record as "processing"
    record = {
        "analysis_id": analysis_id,
        "claim_id": claim_data.claim_id,
        "examiner_id": claim_data.examiner_id,
        "status": "processing",
        "ai_model_used": settings.LLM_MODEL,
        "created_at": datetime.utcnow().isoformat(),
    }
    save_analysis_to_memory(analysis_id, record)

    try:
        # Enforce analysis timeout
        await asyncio.wait_for(
            _run_analysis_pipeline(analysis_id, claim_data, record, start_time),
            timeout=settings.ANALYSIS_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        _handle_failure(
            analysis_id, record, start_time,
            f"Analysis timed out after {settings.ANALYSIS_TIMEOUT_SECONDS} seconds"
        )
    except Exception as e:
        _handle_failure(analysis_id, record, start_time, f"Unexpected error: {e}")


async def _run_analysis_pipeline(
    analysis_id: str,
    claim_data: AnalysisTriggerRequest,
    record: dict,
    start_time: float,
) -> None:
    """
    Inner pipeline — separated so the timeout wrapper can cancel it cleanly.
    """
    try:
        # =================================================================
        # Step 0: Resolve PDF URLs from Firestore if not provided in request
        # =================================================================
        medical_report_url = claim_data.medical_report_url
        policy_document_url = claim_data.policy_document_url
        claim_doc = None  # Will be fetched from Firestore if needed

        if not medical_report_url or not policy_document_url:
            logger.info(f"[{analysis_id}] Step 0: Resolving PDF URLs from Firestore...")
            claim_doc = get_claim(claim_data.claim_id)
            if claim_doc:
                # Get medical report URL from claim document
                if not medical_report_url:
                    medical_report_url = claim_doc.get("medicalReport")
                    if medical_report_url:
                        logger.info(f"[{analysis_id}] Got medicalReport URL from claim doc")
                    else:
                        raise PDFExtractionError(
                            "No medical report URL found in claim document or request"
                        )

                # Get policy document URL from policies collection
                if not policy_document_url:
                    policy_name = claim_doc.get("policyName", "")
                    if policy_name:
                        policy_doc = get_policy_by_name(policy_name)
                        if policy_doc:
                            policy_document_url = policy_doc.get("file_url")
                            logger.info(
                                f"[{analysis_id}] Got policy URL from policies "
                                f"collection (policyName='{policy_name}')"
                            )
                        else:
                            raise PDFExtractionError(
                                f"Policy '{policy_name}' not found in policies collection"
                            )
                    else:
                        raise PDFExtractionError(
                            "No policyName found in claim document"
                        )
            else:
                raise PDFExtractionError(
                    f"Claim {claim_data.claim_id} not found in Firestore "
                    "and no PDF URLs provided in request"
                )

        # =================================================================
        # Step 1: Extract text from medical report PDF
        # =================================================================
        logger.info(f"[{analysis_id}] Step 1: Extracting medical report text...")
        medical_text = await pdf_service.extract_text(medical_report_url)
        if not medical_text or len(medical_text.strip()) < 50:
            raise PDFExtractionError(
                "Medical report PDF appears to be empty or unreadable. "
                "Cannot proceed with analysis."
            )
        logger.info(
            f"[{analysis_id}] Medical report extracted: {len(medical_text)} characters"
        )

        # =================================================================
        # Step 2: Extract text from policy document PDF
        # =================================================================
        logger.info(f"[{analysis_id}] Step 2: Extracting policy document text...")
        policy_text = await pdf_service.extract_text(policy_document_url)
        if not policy_text or len(policy_text.strip()) < 50:
            raise PDFExtractionError(
                "Policy document PDF appears to be empty or unreadable. "
                "Cannot proceed with analysis."
            )
        logger.info(
            f"[{analysis_id}] Policy document extracted: {len(policy_text)} characters"
        )

        # =================================================================
        # Step 2b: Extract text from supporting documents (if any)
        # =================================================================
        supporting_text = ""
        supporting_doc_url = None

        # Fetch claim doc if not already fetched
        if not claim_doc:
            claim_doc = get_claim(claim_data.claim_id)
        if claim_doc:
            supporting_doc_url = claim_doc.get("supportingDocuments")

        if supporting_doc_url and supporting_doc_url.strip() not in ("", "some URL"):
            logger.info(f"[{analysis_id}] Step 2b: Extracting supporting documents text...")
            try:
                supporting_text = await pdf_service.extract_text(supporting_doc_url)
                logger.info(
                    f"[{analysis_id}] Supporting documents extracted: "
                    f"{len(supporting_text)} characters"
                )
            except Exception as e:
                # Non-fatal — log and continue without supporting docs
                logger.warning(
                    f"[{analysis_id}] Could not extract supporting documents "
                    f"(non-fatal, continuing): {e}"
                )
                supporting_text = ""
        else:
            logger.info(f"[{analysis_id}] Step 2b: No supporting documents for this claim")

        # =================================================================
        # Step 3: Build structured prompt (FR-34: all 6 required fields)
        # =================================================================
        logger.info(f"[{analysis_id}] Step 3: Building analysis prompt (FR-34: 6/6 fields)...")
        user_prompt = build_analysis_prompt(
            claim_id=claim_data.claim_id,
            patient_info=claim_data.patient_info.model_dump(),
            treatment_type=claim_data.treatment_type,
            medical_report_text=medical_text,
            policy_document_text=policy_text,
            supporting_documents_text=supporting_text,
        )

        # =================================================================
        # Step 4: Call Gemini LLM API
        # =================================================================
        logger.info(f"[{analysis_id}] Step 4: Calling Gemini API...")
        llm_response = await llm_service.analyze(
            user_prompt=user_prompt,
            system_prompt=CLAIM_ANALYSIS_SYSTEM_PROMPT,
        )
        logger.info(f"[{analysis_id}] Gemini response received")

        # =================================================================
        # Step 5: Parse and validate LLM response
        # =================================================================
        logger.info(f"[{analysis_id}] Step 5: Parsing and validating LLM response...")
        parsed = _parse_llm_response(llm_response)
        logger.info(
            f"[{analysis_id}] Decision: {parsed['coverage_decision']} "
            f"(confidence: {parsed.get('confidence_score', 'N/A')})"
        )
        if parsed.get("rejection_reasons"):
            logger.info(
                f"[{analysis_id}] Rejection reasons: {parsed['rejection_reasons']}"
            )

        # =================================================================
        # Step 6: Generate draft response (US-23)
        # covered → hardcoded approval statement
        # not_covered → AI-generated rejection letter
        # =================================================================
        logger.info(f"[{analysis_id}] Step 6: Generating draft response...")
        draft_text = await response_service.generate_draft(
            claim_id=claim_data.claim_id,
            patient_info=claim_data.patient_info.model_dump(),
            treatment_type=claim_data.treatment_type,
            coverage_decision=parsed["coverage_decision"],
            reasoning=parsed["reasoning"],
            applicable_clauses=parsed["applicable_clauses"],
            flags=parsed.get("flags", []),
            rejection_reasons=parsed.get("rejection_reasons", []),
        )

        # =================================================================
        # Step 7: Write aiDecision + aiMessage to the claims collection
        # aiMessage = the AI reasoning (NOT the draft letter)
        # =================================================================
        processing_time = time.time() - start_time
        logger.info(
            f"[{analysis_id}] Step 7: Updating claim {claim_data.claim_id} "
            f"with aiDecision='{parsed['coverage_decision']}' and aiMessage..."
        )
        update_claim_with_ai_result(
            claim_id=claim_data.claim_id,
            ai_decision=parsed["coverage_decision"],
            ai_message=parsed["reasoning"],
        )

        # =================================================================
        # Step 8: Cache completed results in memory for GET endpoint
        # =================================================================
        logger.info(
            f"[{analysis_id}] Step 8: Caching results in memory "
            f"(total time: {processing_time:.2f}s)"
        )
        record.update({
            "status": "completed",
            "coverage_decision": parsed["coverage_decision"],
            "confidence_score": parsed.get("confidence_score", 0.0),
            "applicable_clauses": parsed.get("applicable_clauses", []),
            "reasoning": parsed.get("reasoning", ""),
            "rejection_reasons": parsed.get("rejection_reasons", []),
            "flags": parsed.get("flags", []),
            "draft_response": draft_text,
            "ai_model_used": settings.LLM_MODEL,
            "processing_time_seconds": round(processing_time, 2),
            "completed_at": datetime.utcnow().isoformat(),
        })
        save_analysis_to_memory(analysis_id, record)

        logger.info(
            f"[{analysis_id}] Analysis pipeline completed successfully. "
            f"Decision: {parsed['coverage_decision']}, "
            f"Confidence: {parsed.get('confidence_score', 'N/A')}, "
            f"Time: {processing_time:.2f}s"
        )

    except (PDFExtractionError, PDFDownloadError) as e:
        _handle_failure(analysis_id, record, start_time, f"PDF processing error: {e}")
    except (LLMServiceError, LLMResponseParsingError) as e:
        _handle_failure(analysis_id, record, start_time, f"LLM error: {e}")
    except Exception as e:
        _handle_failure(analysis_id, record, start_time, f"Unexpected error: {e}")


def _handle_failure(
    analysis_id: str,
    record: dict,
    start_time: float,
    error_message: str,
) -> None:
    """Update the in-memory analysis record to failed status."""
    processing_time = time.time() - start_time
    logger.error(f"[{analysis_id}] Analysis failed: {error_message}")

    record.update({
        "status": "failed",
        "error_message": error_message,
        "processing_time_seconds": round(processing_time, 2),
        "completed_at": datetime.utcnow().isoformat(),
    })
    save_analysis_to_memory(analysis_id, record)


def _parse_llm_response(response: dict) -> dict:
    """
    Parse and validate the structured LLM response.

    Enforces:
    - Valid coverage_decision (only "covered" or "not_covered")
    - Valid confidence_score (0.0 to 1.0)
    - Valid applicable_clauses list
    - rejection_reasons list (new field from hardened prompt)
    - reasoning and flags fields

    Args:
        response: Raw parsed JSON from the LLM.

    Returns:
        Validated response dictionary.

    Raises:
        LLMResponseParsingError: If required fields are missing or invalid.
    """
    # Validate coverage_decision — only two valid values
    coverage_decision = response.get("coverage_decision", "").lower().strip()
    valid_decisions = {"covered", "not_covered"}
    if coverage_decision not in valid_decisions:
        raise LLMResponseParsingError(
            f"Invalid coverage_decision: '{coverage_decision}'. "
            f"Expected one of: {valid_decisions}"
        )

    # Validate confidence_score
    confidence_score = response.get("confidence_score")
    if confidence_score is not None:
        try:
            confidence_score = float(confidence_score)
            confidence_score = max(0.0, min(1.0, confidence_score))
        except (TypeError, ValueError):
            confidence_score = 0.0
    else:
        confidence_score = 0.0

    # Validate applicable_clauses
    clauses = response.get("applicable_clauses", [])
    if not isinstance(clauses, list):
        clauses = []

    validated_clauses = []
    for clause in clauses:
        if isinstance(clause, dict):
            validated_clauses.append({
                "clause_id": str(clause.get("clause_id", "Unknown")),
                "clause_text": str(clause.get("clause_text", "")),
                "relevance": str(clause.get("relevance", "")),
            })

    # Validate rejection_reasons (new field)
    rejection_reasons = response.get("rejection_reasons", [])
    if not isinstance(rejection_reasons, list):
        rejection_reasons = []
    rejection_reasons = [str(r) for r in rejection_reasons if r]

    # Validate flags
    flags = response.get("flags", [])
    if not isinstance(flags, list):
        flags = []
    flags = [str(f) for f in flags if f]

    # Validate reasoning
    reasoning = response.get("reasoning", "No reasoning provided")
    if not reasoning or not isinstance(reasoning, str):
        reasoning = "No reasoning provided"

    return {
        "coverage_decision": coverage_decision,
        "confidence_score": confidence_score,
        "applicable_clauses": validated_clauses,
        "rejection_reasons": rejection_reasons,
        "reasoning": reasoning,
        "flags": flags,
    }


def get_analysis_result(claim_id: str) -> dict:
    """
    Retrieve the analysis result for a claim (US-22).

    Results are cached in memory only (stateless architecture).
    If the service restarts, past results are lost — the frontend
    should rely on the aiDecision/aiMessage fields in the claim document.

    Args:
        claim_id: The claim to retrieve analysis for.

    Returns:
        Analysis data dictionary.

    Raises:
        AnalysisNotFoundError: If no analysis exists for the claim.
    """
    data = get_analysis_from_memory(claim_id)
    if data is None:
        raise AnalysisNotFoundError(claim_id)
    return data
