# Watheeq AI Analysis Service

**Sprint 3 — AI-Powered Health Insurance Claims Analysis Microservice**

A standalone FastAPI microservice that provides AI-powered analysis of health insurance claims against policy documents. Built with **Google Gemini 2.5 Flash** and **Firebase Firestore**. This service is the intelligence layer of the Watheeq AI platform, designed to be consumed by the main application (Flutter + Firebase) via REST API calls.

---

## Live Production URL

The service is deployed and publicly accessible on Render:

| Resource | URL |
|----------|-----|
| **Base URL** | https://watheeq-ai-service.onrender.com |
| **Swagger UI (Interactive Docs)** | https://watheeq-ai-service.onrender.com/docs |
| **ReDoc** | https://watheeq-ai-service.onrender.com/redoc |
| **Health Check** | https://watheeq-ai-service.onrender.com/api/v1/analysis/health |

**Authentication:** All endpoints (except health check) require the header:

```
Authorization: Bearer watheeq-sprint3-token
```

> **Note:** The Render free tier spins down after 15 minutes of inactivity. The first request after spin-down takes approximately 50 seconds. Subsequent requests are fast.

---

## What This Service Does

When a Claims Examiner picks a claim for review, this service:

1. **Ingests** the claim data (patient info, treatment type, medical report PDF)
2. **Extracts** text from both the medical report and policy document PDFs
3. **Analyzes** the claim against the policy using **Gemini 2.5 Flash** LLM
4. **Determines** coverage status: `covered`, `not_covered`, or `partial`
5. **Identifies** applicable policy clauses with exact citations
6. **Generates** a professional draft response message for the examiner to review/edit
7. **Writes back** `aiDecision` and `aiMessage` to the claim document in Firestore

All AI outputs are **recommendations only** — no decision is finalized without explicit Claims Examiner approval (Human-in-the-Loop principle).

---

## Architecture

```
Flutter App (Frontend)
        |
        v
Firebase Backend (Sprints 1 & 2)
        |
        v
  FastAPI Layer (validate request, auth)
        |
        v
  AI/LLM Service (Gemini 2.5 Flash)
        |
        v
  Firestore (write aiDecision + aiMessage to claims collection)
```

**Design Pattern:** Thin routers (HTTP concerns only) → Thick services (all business logic via `process_event()` abstraction)

---

## API Endpoints — Complete Reference

### Summary Table

| Method | Endpoint | Auth | User Story | Description |
|--------|----------|------|------------|-------------|
| `POST` | `/api/v1/analysis/trigger` | Required | US-20 | Trigger AI analysis for a claim |
| `GET` | `/api/v1/analysis/{claim_id}` | Required | US-21, US-22 | Get AI analysis results |
| `GET` | `/api/v1/responses/{claim_id}/draft` | Required | US-23 | Get AI draft response |
| `PUT` | `/api/v1/responses/{claim_id}/draft` | Required | US-24 | Edit AI draft response |
| `GET` | `/api/v1/analysis/health` | **No** | — | Service health check |

---

### 1. Trigger AI Analysis — `POST /api/v1/analysis/trigger`

Triggers the AI analysis pipeline for a claim. Returns immediately with HTTP 202 (Accepted) while the analysis runs in the background.

**Request:**

```http
POST /api/v1/analysis/trigger
Content-Type: application/json
Authorization: Bearer watheeq-sprint3-token
```

```json
{
  "claim_id": "2qzERAkeDSFegHcfnhL5",
  "examiner_id": "phone_966500000002",
  "patient_info": {
    "first_name": "Mohammed",
    "last_name": "Al-Qahtani",
    "date_of_birth": "1990-01-15"
  },
  "treatment_type": "Diagnostic Imaging",
  "policy_plan_id": "Gold Health Plan",
  "medical_report_url": "https://res.cloudinary.com/dj4p6dpnh/raw/upload/v.../medical-report.pdf",
  "policy_document_url": "https://res.cloudinary.com/dj4p6dpnh/raw/upload/v.../policy-document.pdf"
}
```

**Request Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `claim_id` | string | Yes | Firestore document ID from the `claims` collection |
| `examiner_id` | string | Yes | ID of the Claims Examiner who triggered the analysis |
| `patient_info.first_name` | string | Yes | Patient's first name |
| `patient_info.last_name` | string | Yes | Patient's last name |
| `patient_info.date_of_birth` | string | Yes | Patient's date of birth (YYYY-MM-DD) |
| `treatment_type` | string | Yes | Type of treatment (e.g., "Diagnostic Imaging", "Surgery") |
| `policy_plan_id` | string | Yes | Name of the insurance policy plan (e.g., "Gold Health Plan") |
| `medical_report_url` | string | Yes | URL to the medical report PDF (Cloudinary or Firebase Storage) |
| `policy_document_url` | string | Yes | URL to the policy document PDF (Cloudinary or Firebase Storage) |

**Response (HTTP 202 Accepted):**

```json
{
  "analysis_id": "087f73e0-82bd-494b-bdaf-c11002e012b6",
  "claim_id": "2qzERAkeDSFegHcfnhL5",
  "status": "pending",
  "message": "AI analysis has been triggered successfully"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `analysis_id` | string | Unique UUID for this analysis run |
| `claim_id` | string | The claim being analyzed |
| `status` | string | Always `"pending"` on trigger |
| `message` | string | Confirmation message |

**What happens in the background after trigger:**
1. Downloads the medical report PDF from the provided URL
2. Looks up the policy document from the `policies` Firestore collection (by `policy_plan_id`)
3. Extracts text from both PDFs using PyMuPDF
4. Sends the extracted text + claim data to Gemini 2.5 Flash for analysis
5. Parses the AI response (coverage decision, clauses, reasoning)
6. Generates a draft response letter
7. Writes `aiDecision` and `aiMessage` to the claim document in Firestore
8. Stores the full analysis record in the `ai_analyses` collection
9. Stores the draft response in the `ai_drafts` collection

---

### 2. Get Analysis Results — `GET /api/v1/analysis/{claim_id}`

Retrieves the AI analysis results for a claim. Poll this endpoint until `status` is `"completed"` or `"failed"`.

**Request:**

```http
GET /api/v1/analysis/2qzERAkeDSFegHcfnhL5
Authorization: Bearer watheeq-sprint3-token
```

**Response (HTTP 200 — completed):**

```json
{
  "analysis_id": "087f73e0-82bd-494b-bdaf-c11002e012b6",
  "claim_id": "2qzERAkeDSFegHcfnhL5",
  "status": "completed",
  "coverage_decision": "covered",
  "confidence_score": 0.9,
  "applicable_clauses": [
    {
      "clause_id": "ARTICLE 2",
      "clause_text": "The policy covers out-patient medical treatment including diagnostics...",
      "relevance": "Diagnostic Imaging falls under the diagnostics category covered by this clause"
    }
  ],
  "reasoning": "Based on ARTICLE 2 of the Gold Health Plan, Diagnostic Imaging is covered as it falls under the diagnostics category for out-patient medical treatment.",
  "flags": [],
  "recommended_action": "approve",
  "draft_response": "Dear Mohammed Al-Qahtani,\n\nWe are pleased to inform you that your claim for Diagnostic Imaging has been reviewed and is covered under your Gold Health Plan...",
  "ai_model_used": "gemini-2.5-flash",
  "processing_time_seconds": 18.72,
  "created_at": "2026-04-27T19:37:32.589837",
  "completed_at": "2026-04-27T19:37:51.301059",
  "error_message": null,
  "disclaimer": "This is an AI-assisted analysis. Final decision requires human review."
}
```

**Response (HTTP 200 — still processing):**

```json
{
  "analysis_id": "087f73e0-82bd-494b-bdaf-c11002e012b6",
  "claim_id": "2qzERAkeDSFegHcfnhL5",
  "status": "processing",
  "coverage_decision": null,
  "confidence_score": null,
  "applicable_clauses": null,
  "reasoning": null,
  "flags": null,
  "recommended_action": null,
  "draft_response": null,
  "ai_model_used": "gemini-2.5-flash",
  "processing_time_seconds": null,
  "created_at": "2026-04-27T19:37:32.589837",
  "completed_at": null,
  "error_message": null,
  "disclaimer": "This is an AI-assisted analysis. Final decision requires human review."
}
```

**Response (HTTP 404 — claim not found):**

```json
{
  "detail": "No analysis found for claim 2qzERAkeDSFegHcfnhL5"
}
```

**Response Fields:**

| Field | Type | Values | Description |
|-------|------|--------|-------------|
| `analysis_id` | string | UUID | Unique ID for this analysis run |
| `claim_id` | string | — | The claim that was analyzed |
| `status` | string | `pending`, `processing`, `completed`, `failed` | Current analysis status |
| `coverage_decision` | string or null | `covered`, `not_covered`, `partial` | AI coverage determination |
| `confidence_score` | float or null | 0.0 to 1.0 | AI confidence in the decision |
| `applicable_clauses` | array or null | — | List of cited policy clauses |
| `applicable_clauses[].clause_id` | string | — | Clause identifier (e.g., "ARTICLE 2") |
| `applicable_clauses[].clause_text` | string | — | Exact quoted text from the policy |
| `applicable_clauses[].relevance` | string | — | Why this clause applies |
| `reasoning` | string or null | — | Detailed AI justification |
| `flags` | array or null | — | Concerns flagged for manual review |
| `recommended_action` | string or null | `approve`, `reject`, `request_more_info` | AI recommended next step |
| `draft_response` | string or null | — | AI-generated draft letter for the claimant |
| `ai_model_used` | string or null | — | LLM model used (e.g., "gemini-2.5-flash") |
| `processing_time_seconds` | float or null | — | Total processing time |
| `created_at` | datetime or null | ISO 8601 | When analysis was triggered |
| `completed_at` | datetime or null | ISO 8601 | When analysis completed |
| `error_message` | string or null | — | Error details if status is "failed" |
| `disclaimer` | string | — | HITL disclaimer (always present) |

---

### 3. Get Draft Response — `GET /api/v1/responses/{claim_id}/draft`

Retrieves the AI-generated draft response letter for a claim. The examiner can review this before sending to the claimant.

**Request:**

```http
GET /api/v1/responses/2qzERAkeDSFegHcfnhL5/draft
Authorization: Bearer watheeq-sprint3-token
```

**Response (HTTP 200):**

```json
{
  "claim_id": "2qzERAkeDSFegHcfnhL5",
  "original_draft": "Dear Mohammed Al-Qahtani,\n\nWe are pleased to inform you that your claim for Diagnostic Imaging has been reviewed and is covered under your Gold Health Plan...",
  "current_draft": "Dear Mohammed Al-Qahtani,\n\nWe are pleased to inform you that your claim for Diagnostic Imaging has been reviewed and is covered under your Gold Health Plan...",
  "is_edited": false,
  "generated_at": "2026-04-27T19:37:50.007184",
  "last_edited_at": null,
  "last_edited_by": null,
  "disclaimer": "This is an AI-assisted draft. Review and edit before sending to the claimant."
}
```

**Response (HTTP 404 — no draft found):**

```json
{
  "detail": "No draft response found for claim 2qzERAkeDSFegHcfnhL5"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `claim_id` | string | The claim this draft belongs to |
| `original_draft` | string | The original AI-generated draft (never changes) |
| `current_draft` | string | Current version (same as original, or edited by examiner) |
| `is_edited` | boolean | `true` if the examiner has edited the draft |
| `generated_at` | datetime or null | When the AI generated this draft |
| `last_edited_at` | datetime or null | When the draft was last edited |
| `last_edited_by` | string or null | Examiner ID who last edited |
| `disclaimer` | string | HITL disclaimer |

---

### 4. Edit Draft Response — `PUT /api/v1/responses/{claim_id}/draft`

Allows the Claims Examiner to edit the AI-generated draft response before sending it to the claimant.

**Request:**

```http
PUT /api/v1/responses/2qzERAkeDSFegHcfnhL5/draft
Content-Type: application/json
Authorization: Bearer watheeq-sprint3-token
```

```json
{
  "edited_response": "Dear Mohammed Al-Qahtani,\n\nAfter careful review of your claim for Diagnostic Imaging, we are pleased to confirm that this service is fully covered under your Gold Health Plan. Please proceed with the treatment at any approved facility.\n\nSincerely,\nWatheeq Claims Team",
  "examiner_id": "phone_966500000002"
}
```

**Request Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `edited_response` | string | Yes | The edited response text |
| `examiner_id` | string | Yes | ID of the examiner making the edit |

**Response (HTTP 200):**

```json
{
  "claim_id": "2qzERAkeDSFegHcfnhL5",
  "current_draft": "Dear Mohammed Al-Qahtani,\n\nAfter careful review of your claim...",
  "is_edited": true,
  "last_edited_at": "2026-04-27T20:15:30.123456",
  "last_edited_by": "phone_966500000002"
}
```

**Response Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `claim_id` | string | The claim this draft belongs to |
| `current_draft` | string | The updated draft text |
| `is_edited` | boolean | Always `true` after editing |
| `last_edited_at` | datetime | Timestamp of this edit |
| `last_edited_by` | string | Examiner ID who made the edit |

---

### 5. Health Check — `GET /api/v1/analysis/health`

Returns the service health status. **No authentication required.**

**Request:**

```http
GET /api/v1/analysis/health
```

**Response (HTTP 200):**

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "llm_provider": "google-gemini",
  "llm_model": "gemini-2.5-flash"
}
```

---

## Firestore Integration

The service reads from and writes to your existing Firestore database.

### Collections Used

| Collection | Read/Write | Purpose |
|------------|------------|---------|
| `claims` | **Read + Write** | Reads claim data; writes `aiDecision` and `aiMessage` after analysis |
| `policies` | **Read** | Looks up policy documents by `policy_name` to get `file_url` |
| `ai_analyses` | **Write + Read** | Stores full AI analysis records (document ID = claim_id) |
| `ai_drafts` | **Write + Read** | Stores draft response records (document ID = claim_id) |

### Fields Written to `claims` Collection

After the AI analysis completes, two fields are added to the existing claim document:

| Field | Type | Values | Description |
|-------|------|--------|-------------|
| `aiDecision` | string | `"covered"`, `"not_covered"`, `"partial"` | The AI coverage determination |
| `aiMessage` | string | — | The AI-generated draft response letter for the claimant |

**Example:** After analysis, the claim document `2qzERAkeDSFegHcfnhL5` in the `claims` collection will have:

```
claimId: "2qzERAkeDSFegHcfnhL5"
patientFName: "Mohammed"
patientLName: "Al-Qahtani"
treatmentType: "Diagnostic Imaging"
policyName: "Gold Health Plan"
status: "under review"
examinerResponse: ""
aiDecision: "covered"          <-- NEW (written by AI service)
aiMessage: "Dear Mohammed..."  <-- NEW (written by AI service)
```

The Flutter frontend can read these fields directly from Firestore (via snapshot listeners) without needing to call the AI service API.

---

## Frontend Integration Guide

### Option A: Call the AI Service API Directly

Use this when the examiner clicks "Analyze" in the Flutter app:

```javascript
// Step 1: Trigger analysis
const BASE_URL = "https://watheeq-ai-service.onrender.com";
const TOKEN = "watheeq-sprint3-token";

const triggerResponse = await fetch(`${BASE_URL}/api/v1/analysis/trigger`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": `Bearer ${TOKEN}`
  },
  body: JSON.stringify({
    claim_id: "2qzERAkeDSFegHcfnhL5",
    examiner_id: "phone_966500000002",
    patient_info: {
      first_name: "Mohammed",
      last_name: "Al-Qahtani",
      date_of_birth: "1990-01-15"
    },
    treatment_type: "Diagnostic Imaging",
    policy_plan_id: "Gold Health Plan",
    medical_report_url: "https://res.cloudinary.com/.../medical-report.pdf",
    policy_document_url: "https://res.cloudinary.com/.../policy-document.pdf"
  })
});

const { analysis_id, claim_id } = await triggerResponse.json();
// analysis_id = "087f73e0-82bd-494b-bdaf-c11002e012b6"

// Step 2: Poll for results (every 5 seconds)
let result;
do {
  await new Promise(resolve => setTimeout(resolve, 5000));
  const pollResponse = await fetch(
    `${BASE_URL}/api/v1/analysis/${claim_id}`,
    { headers: { "Authorization": `Bearer ${TOKEN}` } }
  );
  result = await pollResponse.json();
} while (result.status === "pending" || result.status === "processing");

// Step 3: Display the result
console.log(result.coverage_decision);  // "covered" | "not_covered" | "partial"
console.log(result.reasoning);          // "Based on ARTICLE 2..."
console.log(result.draft_response);     // "Dear Mohammed..."

// Step 4: Get the draft response for editing
const draftResponse = await fetch(
  `${BASE_URL}/api/v1/responses/${claim_id}/draft`,
  { headers: { "Authorization": `Bearer ${TOKEN}` } }
);
const draft = await draftResponse.json();
// Display draft.current_draft in a text editor

// Step 5: Save examiner's edits
const editResponse = await fetch(
  `${BASE_URL}/api/v1/responses/${claim_id}/draft`,
  {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${TOKEN}`
    },
    body: JSON.stringify({
      edited_response: "Dear Mohammed, after careful review...",
      examiner_id: "phone_966500000002"
    })
  }
);
```

### Option B: Read Results from Firestore Directly

Since the AI service writes `aiDecision` and `aiMessage` to the claim document, the Flutter app can simply listen for changes:

```dart
// Flutter / Dart — Listen for AI results on a claim
FirebaseFirestore.instance
  .collection('claims')
  .doc('2qzERAkeDSFegHcfnhL5')
  .snapshots()
  .listen((snapshot) {
    final data = snapshot.data();
    if (data != null && data['aiDecision'] != null) {
      // AI analysis is complete
      String decision = data['aiDecision'];   // "covered", "not_covered", "partial"
      String message = data['aiMessage'];     // Draft response letter
      // Update the UI
    }
  });
```

---

## Quick Start (Local Development)

### 1. Clone and Setup

```bash
git clone https://github.com/aldayel/fastapi-withOpenaiAPI.git
cd fastapi-withOpenaiAPI
```

### 2. Environment Configuration

```bash
cp .env.example .env
```

Edit `.env` and add your credentials:

```env
GEMINI_API_KEY=your-gemini-api-key
LLM_MODEL=gemini-2.5-flash
BEARER_TOKEN=your-secret-token
FIREBASE_ENABLED=true
FIREBASE_PROJECT_ID=watheeqai-2
FIREBASE_CREDENTIALS_PATH=./firebase-credentials.json
```

### 3. Install Dependencies

```bash
pip install fastapi uvicorn pydantic pydantic-settings google-genai firebase-admin httpx PyMuPDF python-dotenv python-multipart
```

### 4. Run the Service

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. Access API Documentation

Open http://localhost:8000/docs for the interactive Swagger UI.

---

## Running Tests

```bash
# Install dev dependencies
pip install pytest pytest-asyncio pytest-cov anyio

# Run all 42 tests
pytest -v

# Run with coverage report
pytest --cov=app --cov-report=term-missing -v
```

---

## Docker Deployment

```bash
# Build and run
docker build -t watheeq-ai .
docker run -p 8000:8000 --env-file .env watheeq-ai

# Or using Docker Compose
docker-compose up --build
```

---

## Project Structure

```
watheeq-ai-service/
├── app/
│   ├── main.py                    # FastAPI app + CORS + startup config
│   ├── config.py                  # Environment config (pydantic-settings)
│   ├── dependencies.py            # Shared dependencies (Bearer token auth)
│   ├── routers/                   # API layer — validation ONLY
│   │   ├── analysis.py            # US-20, US-21, US-22 endpoints
│   │   └── responses.py           # US-23, US-24 endpoints
│   ├── schemas/                   # Pydantic models — request/response contracts
│   │   ├── analysis.py            # Analysis request + response schemas
│   │   └── responses.py           # Draft response request + response schemas
│   ├── services/                  # Business logic (process_event pattern)
│   │   ├── analysis_service.py    # AI analysis orchestration (THE CORE)
│   │   ├── pdf_service.py         # PDF text extraction (PyMuPDF)
│   │   ├── llm_service.py         # Gemini API integration + model fallback
│   │   ├── response_service.py    # Draft response generation + editing
│   │   └── store.py               # Firestore persistence + in-memory fallback
│   ├── models/                    # Internal domain models
│   │   ├── analysis.py            # AnalysisRecord dataclass
│   │   └── response.py            # DraftResponseRecord dataclass
│   └── utils/                     # Shared utilities
│       ├── prompts.py             # LLM prompt templates
│       └── exceptions.py          # Custom exception classes
├── tests/                         # Pytest test suite (42 tests)
│   ├── conftest.py                # Shared fixtures
│   ├── test_analysis.py           # Analysis endpoint tests
│   ├── test_responses.py          # Response endpoint tests
│   ├── test_llm_service.py        # Service layer tests
│   └── test_auth.py               # Authentication tests
├── .env.example                   # Environment variables template
├── pyproject.toml                 # Dependencies
├── Dockerfile                     # Container deployment
├── docker-compose.yml             # Local development
├── render.yaml                    # Render.com deployment config
└── README.md                      # This file
```

---

## User Stories Implemented

| ID | Title | Priority | Story Points | Status |
|----|-------|----------|-------------|--------|
| US-20 | Automatic AI Analysis Trigger | Must Have | 5 | Implemented |
| US-21 | AI Claim Analysis | Must Have | 19 | Implemented |
| US-22 | AI Coverage Decision View | Must Have | 7 | Implemented |
| US-23 | AI Draft Response Generation | Should Have | 11 | Implemented |
| US-24 | Draft Response Editing | Should Have | 3 | Implemented |

---

## Non-Functional Requirements

| ID | Requirement | Implementation |
|----|-------------|----------------|
| NFR-01 | 90%+ clause matching accuracy | Structured JSON output + careful prompt engineering |
| NFR-02 | Recovery within 180s | Docker auto-restart + health checks |
| NFR-03 | PDF processing < 10s for 20MB | PyMuPDF (fast C-based extraction) |
| NFR-05 | Role-based access | Bearer token authentication |
| NFR-08 | 99% LLM API success rate | Model fallback chain (gemini-2.5-flash → gemini-2.5-flash-lite → gemini-2.0-flash-lite) + exponential backoff retry (3 attempts) |

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GEMINI_API_KEY` | **Yes** | — | Google Gemini API key |
| `LLM_MODEL` | No | `gemini-2.5-flash` | Primary LLM model |
| `LLM_TEMPERATURE` | No | `0.1` | LLM temperature (lower = more consistent) |
| `LLM_MAX_TOKENS` | No | `4000` | Maximum response tokens |
| `FIREBASE_ENABLED` | No | `true` | Enable Firestore integration |
| `FIREBASE_PROJECT_ID` | No | `watheeqai-2` | Firebase project ID |
| `FIREBASE_CREDENTIALS_PATH` | No | `./firebase-credentials.json` | Path to Firebase credentials JSON file |
| `FIREBASE_CREDENTIALS_JSON` | No | — | Firebase credentials as JSON string (for cloud deployment) |
| `CORS_ORIGINS` | No | `*` | Comma-separated allowed origins |
| `BEARER_TOKEN` | No | — | Auth token (empty = auth disabled) |
| `MAX_PDF_SIZE_MB` | No | `20` | Maximum PDF file size in MB |
| `ANALYSIS_TIMEOUT_SECONDS` | No | `60` | Analysis timeout in seconds |
| `SERVICE_HOST` | No | `0.0.0.0` | Service bind host |
| `SERVICE_PORT` | No | `8000` | Service bind port |

---

## Error Handling

All errors follow a consistent format:

| HTTP Status | Meaning | Example |
|-------------|---------|---------|
| `200` | Success | Analysis result returned |
| `202` | Accepted | Analysis triggered, processing in background |
| `401` | Unauthorized | Missing or invalid Bearer token |
| `404` | Not Found | No analysis/draft found for the given claim_id |
| `422` | Validation Error | Missing required fields in request body |
| `500` | Server Error | Internal error (LLM failure, PDF error, etc.) |

Error response format:

```json
{
  "detail": "Human-readable error message"
}
```
