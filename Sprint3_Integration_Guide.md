# Watheeq AI Service — Sprint 3 Integration & Readiness Guide

This document outlines exactly what has been built, what is missing before the service can be shipped to production, and how the frontend and Firebase backend teams can integrate with the new AI microservice.

## 1. What Has Been Built (The APIs)

The Sprint 3 AI microservice is fully implemented as a standalone FastAPI application. It exposes five REST API endpoints that map directly to the five user stories:

### Core Analysis Endpoints
- **`POST /api/v1/analysis/trigger`** (US-20)
  - **Purpose:** Starts the asynchronous AI analysis pipeline.
  - **Input:** Claim details, patient info, and URLs to the medical report and policy document PDFs.
  - **Output:** Returns `HTTP 202 Accepted` immediately with a unique `analysis_id`.
- **`GET /api/v1/analysis/{claim_id}`** (US-21 & US-22)
  - **Purpose:** Polls for the result of the background analysis.
  - **Output:** Returns the current status (`pending`, `processing`, `completed`, `failed`). Once completed, it returns the full AI coverage decision, confidence score, cited policy clauses, reasoning, and recommended action.

### Draft Response Endpoints
- **`GET /api/v1/responses/{claim_id}/draft`** (US-23)
  - **Purpose:** Retrieves the AI-generated draft response message intended for the claimant.
  - **Output:** Returns the original AI draft and the current (potentially edited) draft.
- **`PUT /api/v1/responses/{claim_id}/draft`** (US-24)
  - **Purpose:** Allows a Claims Examiner to edit the AI draft before sending it.
  - **Input:** The edited text and the examiner's ID.
  - **Output:** Saves the edit while preserving the original AI draft for audit purposes.

### Utility Endpoints
- **`GET /api/v1/analysis/health`**
  - **Purpose:** Service health check for load balancers and Docker orchestration.

---

## 2. What is Missing to be "Ready to Ship"

While the code is functionally complete and passes all 42 automated tests (including a live end-to-end test with real PDFs), the following infrastructure and configuration gaps must be addressed before deploying to a live production environment:

### A. Production Environment Variables
The service currently relies on a `.env` file. To run in production, the DevOps team must inject the following real secrets into the container environment:
- **`OPENAI_API_KEY`**: A valid OpenAI API key with billing enabled. (The default model is set to `gpt-4.1-mini` for compatibility and speed).
- **`BEARER_TOKEN`**: A secure, randomly generated string used to authenticate requests from the main Watheeq backend to this microservice.
- **`CORS_ORIGINS`**: Must be updated from `http://localhost:3000` to the actual production frontend domains (e.g., `https://app.watheeq.ai`).

### B. Persistent Storage (Mode A vs Mode B)
Currently, the service uses **Mode B (In-Memory Storage)**. This means if the Docker container restarts, all pending analyses and draft responses are lost.
- **Action Required:** The backend team must implement **Mode A (Firestore)**. The `app/services/store.py` file contains explicit, commented-out code showing exactly how to swap the in-memory dictionaries for Firebase Firestore collections (`analyses` and `draft_responses`).
- **Requirements:** `FIREBASE_ENABLED=true` and a valid `firebase-credentials.json` file mounted into the container.

### C. Robust Background Processing
Currently, the AI pipeline runs using FastAPI's built-in `BackgroundTasks`. This is sufficient for MVP and low volume, but it is tied to the web worker process.
- **Action Required for Scale:** For high-volume production, the background task in `app/routers/analysis.py` should be migrated to a dedicated task queue like **Celery + Redis**. The architecture is already decoupled to support this (the logic is isolated in `analysis_service.py`).

### D. Production Deployment Orchestration
The provided `docker-compose.yml` is designed for single-node deployment.
- **Action Required:** The DevOps team should deploy the provided `Dockerfile` to a managed container service (e.g., AWS ECS, Google Cloud Run, or Kubernetes) behind a load balancer with HTTPS termination.

---

## 3. How the Team Can Integrate It

The AI microservice is designed to be consumed via REST API calls. Here is how the frontend and main Firebase backend teams should interact with it:

### Step 1: Triggering the Analysis (Backend/Frontend)
When a Claims Examiner clicks "Analyze Claim", the main application should send a POST request to the AI service. The PDFs must be accessible via public or signed URLs (e.g., Firebase Storage download URLs), or passed as base64 strings.

```javascript
const response = await fetch("https://ai.watheeq.internal/api/v1/analysis/trigger", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer <YOUR_SECRET_TOKEN>"
  },
  body: JSON.stringify({
    claim_id: "CLM-12345",
    patient_info: {
      first_name: "Mohammed",
      last_name: "Al-Qahtani",
      date_of_birth: "1990-01-15"
    },
    treatment_type: "Physiotherapy",
    policy_plan_id: "PP-GOLD",
    medical_report_url: "https://firebasestorage.googleapis.com/.../report.pdf",
    policy_document_url: "https://firebasestorage.googleapis.com/.../policy.pdf",
    examiner_id: "EX-001"
  })
});
// Returns HTTP 202 with { "analysis_id": "...", "status": "pending" }
```

### Step 2: Polling for Results (Frontend)
Because LLM processing and PDF extraction take time (typically 10-15 seconds), the frontend should poll the GET endpoint every 3-5 seconds until the status changes from `processing` to `completed`.

```javascript
const pollResponse = await fetch("https://ai.watheeq.internal/api/v1/analysis/CLM-12345", {
  headers: { "Authorization": "Bearer <YOUR_SECRET_TOKEN>" }
});
const data = await pollResponse.json();

if (data.status === "completed") {
  // Display data.coverage_decision, data.applicable_clauses, etc.
} else if (data.status === "failed") {
  // Display data.error_message
}
```

### Step 3: Managing the Draft Response (Frontend)
Once the analysis is complete, the AI automatically generates a draft response. The frontend can fetch this draft and present it in a text editor for the Claims Examiner.

```javascript
// Fetch the draft
const draftRes = await fetch("https://ai.watheeq.internal/api/v1/responses/CLM-12345/draft", {
  headers: { "Authorization": "Bearer <YOUR_SECRET_TOKEN>" }
});
const draftData = await draftRes.json();
// Display draftData.current_draft in a textarea

// Save examiner edits
await fetch("https://ai.watheeq.internal/api/v1/responses/CLM-12345/draft", {
  method: "PUT",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer <YOUR_SECRET_TOKEN>"
  },
  body: JSON.stringify({
    edited_response: "Dear Mr. Al-Qahtani, your claim has been reviewed...",
    examiner_id: "EX-001"
  })
});
```

## Summary
The AI core is fully functional. To ship it, the team needs to:
1. Provision an OpenAI API key.
2. Deploy the Docker container to a cloud provider.
3. Swap the `store.py` implementation to use Firebase (code provided in comments).
4. Implement the REST API calls in the frontend/main backend as shown above.
