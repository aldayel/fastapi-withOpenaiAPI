# Watheeq AI Analysis Service

**Sprint 3 -- AI-Powered Health Insurance Claims Analysis Microservice**

A standalone FastAPI microservice that provides AI-powered analysis of health insurance claims against policy documents. This service is the intelligence layer of the Watheeq AI platform, designed to be consumed by the main application (Next.js + Firebase) via REST API calls.

---

## What This Service Does

When a Claims Examiner picks a claim for review, this service:

1. **Ingests** the claim data (patient info, treatment type, medical report PDF)
2. **Extracts** text from both the medical report and policy document PDFs
3. **Analyzes** the claim against the policy using an LLM (OpenAI GPT-4o)
4. **Determines** coverage status (Covered / Not Covered / Partial)
5. **Identifies** applicable policy clauses with exact citations
6. **Generates** a draft response message for the examiner to review/edit

All AI outputs are **recommendations only** -- no decision is finalized without explicit Claims Examiner approval (Human-in-the-Loop principle).

---

## Architecture

```
Application (Next.js + Firebase)
        |
        v
  FastAPI Layer (validate request)
        |
        v
  AI/LLM Service (process with AI model)
        |
        v
  Return formatted response
```

**Design Pattern:** Thin routers (HTTP only) -> Thick services (all business logic)

---

## Quick Start

### 1. Clone and Setup

```bash
git clone https://github.com/RayanDesigns/fastapi-withOpenaiAPI.git
cd fastapi-withOpenaiAPI
git checkout feature/sprint-3-ai-service
```

### 2. Environment Configuration

```bash
cp .env.example .env
```

Edit `.env` and add your OpenAI API key:

```env
OPENAI_API_KEY=sk-your-actual-api-key-here
LLM_MODEL=gpt-4o
BEARER_TOKEN=your-secret-token
```

Leave `BEARER_TOKEN` empty to disable authentication in development.

### 3. Install Dependencies

**Option A -- pip:**

```bash
pip install fastapi uvicorn pydantic pydantic-settings openai httpx PyMuPDF python-dotenv python-multipart
```

**Option B -- uv (recommended):**

```bash
pip install uv
uv sync
```

### 4. Run the Service

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 5. Access API Documentation

| Resource | URL |
|----------|-----|
| Swagger UI | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| Health Check | http://localhost:8000/api/v1/analysis/health |

---

## API Endpoints

| Method | Endpoint | User Story | Description |
|--------|----------|------------|-------------|
| `POST` | `/api/v1/analysis/trigger` | US-20 | Trigger AI analysis for a claim |
| `GET` | `/api/v1/analysis/{claim_id}` | US-21, US-22 | Get AI analysis results |
| `GET` | `/api/v1/responses/{claim_id}/draft` | US-23 | Get AI draft response |
| `PUT` | `/api/v1/responses/{claim_id}/draft` | US-24 | Edit AI draft response |
| `GET` | `/api/v1/analysis/health` | -- | Service health check |

---

## Integration Guide (for Frontend + Firebase Team)

### When Examiner Picks a Claim -> Trigger Analysis

```javascript
// POST /api/v1/analysis/trigger
const response = await fetch('http://localhost:8000/api/v1/analysis/trigger', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer your-secret-token'
  },
  body: JSON.stringify({
    claim_id: 'CLM-001',
    patient_info: {
      first_name: 'Mohammed',
      last_name: 'Al-Qahtani',
      date_of_birth: '1990-01-15'
    },
    treatment_type: 'Physiotherapy',
    policy_plan_id: 'PP-BASIC',
    medical_report_url: 'https://firebasestorage.googleapis.com/...medical-report.pdf',
    policy_document_url: 'https://firebasestorage.googleapis.com/...policy-plan.pdf',
    examiner_id: 'EX-001'
  })
});

// Response (HTTP 202 Accepted):
// {
//   "analysis_id": "uuid",
//   "claim_id": "CLM-001",
//   "status": "pending",
//   "message": "AI analysis has been triggered successfully"
// }
```

### When Examiner Views Claim Details -> Get Analysis Results

```javascript
// GET /api/v1/analysis/{claim_id}
// Poll this endpoint until status is "completed" or "failed"
const response = await fetch('http://localhost:8000/api/v1/analysis/CLM-001', {
  headers: { 'Authorization': 'Bearer your-secret-token' }
});

// Response includes:
// - coverage_decision: "covered" | "not_covered" | "partial"
// - confidence_score: 0.0 to 1.0
// - applicable_clauses: [{ clause_id, clause_text, relevance }]
// - reasoning: "Detailed AI justification"
// - draft_response: "Generated message for claimant"
// - disclaimer: "This is an AI-assisted analysis..."
```

### When Examiner Wants to View Draft -> Get Draft Response

```javascript
// GET /api/v1/responses/{claim_id}/draft
const response = await fetch('http://localhost:8000/api/v1/responses/CLM-001/draft', {
  headers: { 'Authorization': 'Bearer your-secret-token' }
});

// Response:
// {
//   "claim_id": "CLM-001",
//   "original_draft": "AI-generated text...",
//   "current_draft": "Same as original or edited version",
//   "is_edited": false,
//   "generated_at": "2026-04-26T10:00:00",
//   "last_edited_at": null
// }
```

### When Examiner Edits the Draft -> Update Draft Response

```javascript
// PUT /api/v1/responses/{claim_id}/draft
const response = await fetch('http://localhost:8000/api/v1/responses/CLM-001/draft', {
  method: 'PUT',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer your-secret-token'
  },
  body: JSON.stringify({
    edited_response: 'Dear patient, after careful review of your claim...',
    examiner_id: 'EX-001'
  })
});

// Response:
// {
//   "claim_id": "CLM-001",
//   "current_draft": "Dear patient, after careful review...",
//   "is_edited": true,
//   "last_edited_at": "2026-04-26T11:30:00",
//   "last_edited_by": "EX-001"
// }
```

---

## Running Tests

```bash
# Install dev dependencies
pip install pytest pytest-asyncio pytest-cov anyio

# Run all tests
pytest -v

# Run with coverage report
pytest --cov=app --cov-report=term-missing -v

# Run specific test file
pytest tests/test_analysis.py -v
```

---

## Docker Deployment

### Build and Run

```bash
docker build -t watheeq-ai .
docker run -p 8000:8000 --env-file .env watheeq-ai
```

### Using Docker Compose

```bash
docker-compose up --build
```

---

## Firebase Integration (Optional -- Mode A)

By default, this service uses in-memory storage (Mode B -- stateless). To enable direct Firestore access:

1. Install Firebase Admin SDK:
   ```bash
   pip install firebase-admin
   ```

2. Update `.env`:
   ```env
   FIREBASE_ENABLED=true
   FIREBASE_PROJECT_ID=watheeq-ai
   FIREBASE_CREDENTIALS_PATH=./firebase-credentials.json
   ```

3. Replace in-memory store calls in `app/services/store.py` with Firestore operations. Each function in `store.py` includes commented Firestore equivalents.

---

## Project Structure

```
watheeq-ai-service/
├── app/
│   ├── main.py                    # FastAPI app + CORS + startup config
│   ├── config.py                  # Environment config (pydantic-settings)
│   ├── dependencies.py            # Shared dependencies (auth)
│   ├── routers/                   # API layer -- validation ONLY
│   │   ├── analysis.py            # US-20, US-21, US-22 endpoints
│   │   └── responses.py           # US-23, US-24 endpoints
│   ├── schemas/                   # Pydantic models -- request/response
│   │   ├── analysis.py            # Analysis schemas
│   │   └── responses.py           # Response schemas
│   ├── services/                  # Business logic (process_event pattern)
│   │   ├── analysis_service.py    # AI analysis orchestration (THE CORE)
│   │   ├── pdf_service.py         # PDF text extraction
│   │   ├── llm_service.py         # LLM API integration (OpenAI)
│   │   ├── response_service.py    # Draft response generation + editing
│   │   └── store.py               # In-memory data store
│   ├── models/                    # Internal domain models
│   │   ├── analysis.py            # AnalysisRecord dataclass
│   │   └── response.py            # DraftResponseRecord dataclass
│   └── utils/                     # Shared utilities
│       ├── prompts.py             # LLM prompt templates
│       └── exceptions.py          # Custom exception classes
├── tests/                         # Pytest test suite
│   ├── conftest.py                # Shared fixtures
│   ├── test_analysis.py           # Analysis endpoint tests
│   ├── test_responses.py          # Response endpoint tests
│   ├── test_llm_service.py        # Service layer tests
│   └── test_auth.py               # Authentication tests
├── .env.example                   # Environment variables template
├── pyproject.toml                 # Dependencies
├── Dockerfile                     # Container deployment
├── docker-compose.yml             # Local development
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
| NFR-08 | 99% LLM API success rate | Exponential backoff retry logic (3 attempts) |

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes | -- | OpenAI API key |
| `LLM_MODEL` | No | `gpt-4o` | LLM model to use |
| `LLM_TEMPERATURE` | No | `0.1` | LLM temperature (lower = more consistent) |
| `LLM_MAX_TOKENS` | No | `4000` | Maximum response tokens |
| `FIREBASE_ENABLED` | No | `false` | Enable Firestore integration |
| `FIREBASE_PROJECT_ID` | No | -- | Firebase project ID |
| `FIREBASE_CREDENTIALS_PATH` | No | -- | Path to Firebase credentials JSON |
| `CORS_ORIGINS` | No | `http://localhost:3000` | Comma-separated allowed origins |
| `BEARER_TOKEN` | No | -- | Auth token (empty = auth disabled) |
| `MAX_PDF_SIZE_MB` | No | `20` | Maximum PDF file size in MB |
| `ANALYSIS_TIMEOUT_SECONDS` | No | `60` | Analysis timeout in seconds |
| `SERVICE_HOST` | No | `0.0.0.0` | Service bind host |
| `SERVICE_PORT` | No | `8000` | Service bind port |
| `API_VERSION` | No | `v1` | API version prefix |
