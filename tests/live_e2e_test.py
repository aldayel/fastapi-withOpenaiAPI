"""
Watheeq AI Service - Live End-to-End Test

This script tests the full pipeline:
  1. Trigger analysis with local PDF files
  2. Poll for completion
  3. Retrieve analysis results
  4. Retrieve draft response
  5. Edit draft response

Requires:
  - OPENAI_API_KEY set in .env
  - Server running on localhost:8000
"""

import base64
import json
import time
import sys

import httpx

BASE_URL = "http://localhost:8000"
AUTH_HEADER = {"Authorization": "Bearer your-secret-token"}


def encode_pdf_to_base64(file_path: str) -> str:
    """Read a PDF file and return base64-encoded string."""
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def main():
    print("=" * 60)
    print("WATHEEQ AI SERVICE - LIVE END-TO-END TEST")
    print("=" * 60)

    # Encode test PDFs as base64
    print("\n[1/6] Encoding test PDFs...")
    medical_b64 = encode_pdf_to_base64("tests/sample_medical_report.pdf")
    policy_b64 = encode_pdf_to_base64("tests/sample_policy_document.pdf")
    print(f"  Medical report: {len(medical_b64)} chars (base64)")
    print(f"  Policy document: {len(policy_b64)} chars (base64)")

    # Step 1: Health check
    print("\n[2/6] Health check...")
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        r = client.get("/api/v1/analysis/health")
        print(f"  Status: {r.status_code}")
        print(f"  Response: {r.json()}")
        assert r.status_code == 200, f"Health check failed: {r.status_code}"

    # Step 2: Trigger analysis
    print("\n[3/6] Triggering AI analysis...")
    payload = {
        "claim_id": "CLM-E2E-001",
        "patient_info": {
            "first_name": "Mohammed",
            "last_name": "Al-Qahtani",
            "date_of_birth": "1990-01-15",
        },
        "treatment_type": "Physiotherapy",
        "policy_plan_id": "PP-GOLD",
        "medical_report_url": medical_b64,
        "policy_document_url": policy_b64,
        "examiner_id": "EX-001",
    }

    with httpx.Client(base_url=BASE_URL, timeout=10, headers=AUTH_HEADER) as client:
        r = client.post("/api/v1/analysis/trigger", json=payload)
        print(f"  Status: {r.status_code}")
        trigger_data = r.json()
        print(f"  Response: {json.dumps(trigger_data, indent=2)}")
        assert r.status_code == 202, f"Trigger failed: {r.status_code}"
        analysis_id = trigger_data["analysis_id"]
        print(f"  Analysis ID: {analysis_id}")

    # Step 3: Poll for completion
    print("\n[4/6] Polling for analysis completion...")
    max_wait = 90  # seconds
    poll_interval = 3
    elapsed = 0
    status = "pending"

    with httpx.Client(base_url=BASE_URL, timeout=10, headers=AUTH_HEADER) as client:
        while elapsed < max_wait and status in ("pending", "processing"):
            time.sleep(poll_interval)
            elapsed += poll_interval
            r = client.get(f"/api/v1/analysis/CLM-E2E-001")
            if r.status_code == 200:
                result = r.json()
                status = result.get("status", "unknown")
                print(f"  [{elapsed}s] Status: {status}")
            elif r.status_code == 404:
                print(f"  [{elapsed}s] Not found yet...")
            else:
                print(f"  [{elapsed}s] Unexpected: {r.status_code}")

    if status != "completed":
        print(f"\n  WARNING: Analysis did not complete. Final status: {status}")
        if status == "failed":
            print(f"  Error: {result.get('error_message', 'N/A')}")
        sys.exit(1)

    # Step 4: Display analysis results
    print("\n[5/6] Analysis Results:")
    print(f"  Coverage Decision: {result.get('coverage_decision')}")
    print(f"  Confidence Score:  {result.get('confidence_score')}")
    print(f"  Recommended Action: {result.get('recommended_action')}")
    print(f"  Processing Time:   {result.get('processing_time_seconds')}s")
    print(f"  AI Model Used:     {result.get('ai_model_used')}")
    print(f"  Disclaimer:        {result.get('disclaimer')}")

    clauses = result.get("applicable_clauses", [])
    print(f"\n  Applicable Clauses ({len(clauses)}):")
    for i, clause in enumerate(clauses, 1):
        print(f"    [{i}] {clause.get('clause_id')}")
        print(f"        Text: {clause.get('clause_text', '')[:100]}...")
        print(f"        Relevance: {clause.get('relevance', '')[:100]}...")

    print(f"\n  Reasoning: {result.get('reasoning', '')[:300]}...")

    flags = result.get("flags", [])
    if flags:
        print(f"\n  Flags ({len(flags)}):")
        for flag in flags:
            print(f"    - {flag}")

    print(f"\n  Draft Response Preview:")
    draft = result.get("draft_response", "")
    print(f"    {draft[:300]}...")

    # Step 5: Get draft response via dedicated endpoint
    print("\n[6/6] Testing draft response endpoints...")
    with httpx.Client(base_url=BASE_URL, timeout=10, headers=AUTH_HEADER) as client:
        # GET draft
        r = client.get("/api/v1/responses/CLM-E2E-001/draft")
        print(f"  GET draft status: {r.status_code}")
        if r.status_code == 200:
            draft_data = r.json()
            print(f"  Is Edited: {draft_data.get('is_edited')}")
            print(f"  Disclaimer: {draft_data.get('disclaimer')}")

        # PUT edit draft
        edit_payload = {
            "edited_response": "Dear Mr. Al-Qahtani, [EDITED BY EXAMINER] Your physiotherapy claim has been reviewed...",
            "examiner_id": "EX-001",
        }
        r = client.put("/api/v1/responses/CLM-E2E-001/draft", json=edit_payload)
        print(f"  PUT edit status: {r.status_code}")
        if r.status_code == 200:
            edit_data = r.json()
            print(f"  Is Edited: {edit_data.get('is_edited')}")
            print(f"  Last Edited By: {edit_data.get('last_edited_by')}")

        # GET draft again to verify edit
        r = client.get("/api/v1/responses/CLM-E2E-001/draft")
        if r.status_code == 200:
            final_draft = r.json()
            print(f"  Original preserved: {final_draft.get('original_draft', '')[:80]}...")
            print(f"  Current (edited):   {final_draft.get('current_draft', '')[:80]}...")

    print("\n" + "=" * 60)
    print("END-TO-END TEST COMPLETED SUCCESSFULLY")
    print("=" * 60)


if __name__ == "__main__":
    main()
