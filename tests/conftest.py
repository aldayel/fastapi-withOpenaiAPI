"""
Watheeq AI Service - Test Configuration and Fixtures

Shared fixtures for the pytest test suite.
Uses httpx AsyncClient with ASGITransport for async endpoint testing.
"""

import os

# Disable auth for tests by default (set BEARER_TOKEN to empty)
os.environ["BEARER_TOKEN"] = ""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Re-create settings after env override so auth is disabled
from app.config import Settings
import app.config as config_module
config_module.settings = Settings()

from app.main import app
from app.services.store import clear_all_stores


@pytest_asyncio.fixture
async def client():
    """Async HTTP test client for the FastAPI app (auth disabled)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def clean_stores():
    """Clear all in-memory stores before each test."""
    clear_all_stores()
    yield
    clear_all_stores()
