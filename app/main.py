"""
Watheeq AI Analysis Service - Application Entry Point

FastAPI application with CORS middleware, router registration,
and startup configuration for the AI claims analysis microservice.

Run locally:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Swagger UI:
    http://localhost:8000/docs

ReDoc:
    http://localhost:8000/redoc
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import analysis, responses

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(
    title="Watheeq AI Analysis Service",
    description=(
        "AI-powered health insurance claims analysis microservice. "
        "Analyzes medical claims against policy documents, determines coverage, "
        "cites applicable policy clauses, and generates draft responses. "
        "All outputs are AI-assisted recommendations requiring human review (HITL)."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# =============================================================================
# CORS Middleware
# =============================================================================

# Parse allowed origins from comma-separated config string
allowed_origins = [
    origin.strip()
    for origin in settings.CORS_ORIGINS.split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# Router Registration
# =============================================================================

# Analysis endpoints (US-20, US-21, US-22)
app.include_router(
    analysis.router,
    prefix=f"/api/{settings.API_VERSION}/analysis",
    tags=["Analysis"],
)

# Response endpoints (US-23, US-24)
app.include_router(
    responses.router,
    prefix=f"/api/{settings.API_VERSION}/responses",
    tags=["Responses"],
)


# =============================================================================
# Root Endpoint
# =============================================================================


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with service information."""
    return {
        "service": "Watheeq AI Analysis Service",
        "version": "1.0.0",
        "description": "AI-powered health insurance claims analysis microservice",
        "docs": "/docs",
        "health": f"/api/{settings.API_VERSION}/analysis/health",
    }


# =============================================================================
# Startup / Shutdown Events
# =============================================================================


@app.on_event("startup")
async def startup_event():
    """Log service startup configuration."""
    logger.info("=" * 60)
    logger.info("Watheeq AI Analysis Service starting up...")
    logger.info(f"  LLM Model:       {settings.LLM_MODEL}")
    logger.info(f"  LLM Temperature: {settings.LLM_TEMPERATURE}")
    firebase_status = "Enabled" if settings.FIREBASE_ENABLED else "Disabled (Mode B)"
    logger.info(f"  Firebase:        {firebase_status}")
    logger.info(f"  CORS Origins:    {allowed_origins}")
    logger.info(f"  API Version:     {settings.API_VERSION}")
    auth_status = "Enabled" if settings.BEARER_TOKEN else "Disabled (dev mode)"
    logger.info(f"  Auth:            {auth_status}")
    logger.info("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    """Log service shutdown."""
    logger.info("Watheeq AI Analysis Service shutting down...")
