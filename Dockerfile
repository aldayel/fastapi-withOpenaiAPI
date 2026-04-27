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

# Copy Firebase credentials
COPY firebase-credentials.json ./firebase-credentials.json

# Cloud Run sets PORT env var; default to 8080
ENV PORT=8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; r = httpx.get(f'http://localhost:{__import__(\"os\").environ.get(\"PORT\", 8080)}/api/v1/analysis/health'); r.raise_for_status()" || exit 1

# Run the application — Cloud Run requires 0.0.0.0:$PORT
CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1
