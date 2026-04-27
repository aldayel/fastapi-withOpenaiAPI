FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for PyMuPDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first for better Docker layer caching
COPY pyproject.toml .

# Install Python dependencies
RUN pip install --no-cache-dir pip --upgrade && \
    pip install --no-cache-dir \
    fastapi[standard] \
    uvicorn[standard] \
    pydantic \
    pydantic-settings \
    google-genai \
    firebase-admin \
    httpx \
    PyMuPDF \
    python-dotenv \
    python-multipart

# Copy application code
COPY app/ ./app/

# Copy Firebase credentials if present (for local/Cloud Run deployment)
# On Render, credentials are passed via FIREBASE_CREDENTIALS_JSON env var
COPY firebase-credentials.jso[n] ./

# Default port (Render sets PORT env var automatically)
ENV PORT=8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen(f'http://localhost:{__import__(\"os\").environ.get(\"PORT\", 8080)}/api/v1/analysis/health')" || exit 1

# Run the application
CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1
