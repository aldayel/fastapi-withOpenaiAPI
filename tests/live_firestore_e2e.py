"""
Live End-to-End Test — Gemini + Firestore

Tests the full pipeline with a real claim from Firestore:
1. Picks a real claim from the 'claims' collection
2. Finds the matching policy PDF URL
3. Triggers AI analysis via the API
4. Polls until completion
5. Verifies aiDecision and aiMessage were written to the claim document
"""

import time
import json
import requests

BASE = "http://localhost:8000"
HEADERS = {
    "Authorization": "Bearer watheeq-sprint3-token",
    "Content-Type": "application/json",
}

# First, read a real claim from Firestore to get its data
import firebase_admin
from firebase_admin import credentials, firestore

try:
    firebase_admin.get_app()
except ValueError:
    cred = credentials.Certificate("firebase-credentials.json")
    firebase_admin.initialize_app(cred, {"projectId": "watheeqai-2"})

db = firestore.client()

print("=" * 60)
print("LIVE E2E TEST — GEMINI + FIRESTORE")
print("=" * 60)

# Step 1: Pick a real claim
print("\n[1/7] Finding a real claim from Firestore...")
claims = db.collection("claims").limit(3).get()
claim_doc = None
for c in claims:
    data = c.to_dict()
    if data.get("medicalReport"):
        claim_doc = c
        break

if not claim_doc:
    print("ERROR: No claims with medical reports found!")
    exit(1)

claim_data = claim_doc.to_dict()
claim_id = claim_doc.id
print(f"  Claim ID: {claim_id}")
print(f"  Patient: {claim_data.get('patientFName')} {claim_data.get('patientLName')}")
print(f"  Policy: {claim_data.get('policyName')}")
print(f"  Treatment: {claim_data.get('treatmentType')}")
print(f"  Medical Report URL: {claim_data.get('medicalReport', '')[:80]}...")

# Step 2: Find the policy PDF URL
print("\n[2/7] Finding policy document...")
policy_name = claim_data.get("policyName", "").lower()
# Map policy names to search terms
search_name = "basic"  # default
if "gold" in policy_name:
    search_name = "basic"  # use the available policy
elif "basic" in policy_name:
    search_name = "basic"

policies = db.collection("policies").where("policy_name", "==", search_name).limit(1).get()
policy_url = None
for p in policies:
    policy_url = p.to_dict().get("file_url")
    print(f"  Policy: {p.to_dict().get('policy_name')}")
    print(f"  URL: {policy_url[:80]}...")

if not policy_url:
    print("  WARNING: No policy found, using a placeholder")
    policy_url = claim_data.get("medicalReport", "")  # fallback

# Step 3: Health check
print("\n[3/7] Health check...")
r = requests.get(f"{BASE}/api/v1/analysis/health")
print(f"  Status: {r.status_code}")
print(f"  Response: {r.json()}")

# Step 4: Trigger analysis
print("\n[4/7] Triggering AI analysis...")
payload = {
    "claim_id": claim_id,
    "examiner_id": claim_data.get("examinerID", "test-examiner"),
    "patient_info": {
        "first_name": claim_data.get("patientFName", "Test"),
        "last_name": claim_data.get("patientLName", "Patient"),
        "date_of_birth": claim_data.get("patientDOB", "1990-01-01"),
    },
    "treatment_type": claim_data.get("treatmentType", "General"),
    "policy_plan_id": claim_data.get("policyName", "basic"),
    "medical_report_url": claim_data.get("medicalReport", ""),
    "policy_document_url": policy_url,
}
print(f"  Payload: {json.dumps(payload, indent=2)[:500]}")

r = requests.post(f"{BASE}/api/v1/analysis/trigger", json=payload, headers=HEADERS)
print(f"  Status: {r.status_code}")
resp = r.json()
print(f"  Response: {json.dumps(resp, indent=2)}")
analysis_id = resp.get("analysis_id")

# Step 5: Poll for completion
print("\n[5/7] Polling for analysis completion...")
max_wait = 120
waited = 0
final_status = "unknown"
while waited < max_wait:
    time.sleep(5)
    waited += 5
    r = requests.get(f"{BASE}/api/v1/analysis/{claim_id}", headers=HEADERS)
    if r.status_code == 200:
        data = r.json()
        status = data.get("status", "unknown")
        print(f"  [{waited}s] Status: {status}")
        if status in ("completed", "failed"):
            final_status = status
            print(f"  Full response: {json.dumps(data, indent=2)[:1000]}")
            break
    elif r.status_code == 404:
        print(f"  [{waited}s] Not found yet...")
    else:
        print(f"  [{waited}s] HTTP {r.status_code}: {r.text[:200]}")

if final_status == "completed":
    print("\n[6/7] Checking draft response...")
    r = requests.get(f"{BASE}/api/v1/responses/{claim_id}/draft", headers=HEADERS)
    print(f"  Status: {r.status_code}")
    if r.status_code == 200:
        draft = r.json()
        print(f"  Draft text (first 300 chars): {draft.get('draft_text', '')[:300]}...")

    print("\n[7/7] Verifying aiDecision and aiMessage in Firestore claim document...")
    updated_claim = db.collection("claims").document(claim_id).get().to_dict()
    ai_decision = updated_claim.get("aiDecision", "NOT FOUND")
    ai_message = updated_claim.get("aiMessage", "NOT FOUND")
    print(f"  aiDecision: {ai_decision}")
    print(f"  aiMessage (first 300 chars): {str(ai_message)[:300]}...")

    if ai_decision != "NOT FOUND" and ai_message != "NOT FOUND":
        print("\n" + "=" * 60)
        print("SUCCESS: Full pipeline working! aiDecision and aiMessage")
        print("are now in the Firestore claim document.")
        print("=" * 60)
    else:
        print("\n  WARNING: aiDecision or aiMessage not found in claim document")
else:
    print(f"\n  FAILED: Analysis ended with status: {final_status}")
