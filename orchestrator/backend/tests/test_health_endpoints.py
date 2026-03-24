"""
Health Check Endpoints Tests

Tests health check endpoints with REAL database connections.
NO MOCKING - Tests must be ephemeral (setup → execute → teardown).

Run with: uv run pytest tests/test_health_endpoints.py -v
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

# Import main app and database module
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from modules import database


@pytest_asyncio.fixture(scope="function")
async def db_pool():
    """Initialize database pool for testing"""
    await database.init_pool()
    yield
    await database.close_pool()


@pytest_asyncio.fixture
async def client(db_pool):
    """Create async HTTP client for testing FastAPI app"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_liveness_probe_returns_200(client):
    """Test /health/live endpoint returns 200 when app is running"""
    response = await client.get("/health/live")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "alive"
    assert data["service"] == "orchestrator-3-stream"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_liveness_probe_no_database_check(client):
    """Test /health/live endpoint doesn't check database connectivity"""
    # Liveness should succeed even if database has issues
    # This test verifies it's a lightweight check
    response = await client.get("/health/live")

    assert response.status_code == 200
    data = response.json()

    # Should NOT have database status in liveness check
    assert "checks" not in data
    assert "database" not in data


@pytest.mark.asyncio
async def test_readiness_probe_returns_200_when_healthy(client):
    """Test /health/ready endpoint returns 200 when all dependencies are healthy"""
    response = await client.get("/health/ready")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ready"
    assert data["service"] == "orchestrator-3-stream"
    assert "timestamp" in data
    assert "checks" in data
    assert "duration_ms" in data

    # Verify database check passed
    assert "database" in data["checks"]
    assert data["checks"]["database"]["status"] == "healthy"
    assert data["checks"]["database"]["type"] == "postgresql"


@pytest.mark.asyncio
async def test_readiness_probe_includes_timing(client):
    """Test /health/ready endpoint includes duration_ms for performance monitoring"""
    response = await client.get("/health/ready")

    assert response.status_code == 200
    data = response.json()

    assert "duration_ms" in data
    assert isinstance(data["duration_ms"], (int, float))
    # Health check should complete quickly (under 1 second)
    assert data["duration_ms"] < 1000


@pytest.mark.asyncio
async def test_readiness_probe_fast_execution(client):
    """Test /health/ready completes quickly (under 500ms)"""
    import time

    start = time.time()
    response = await client.get("/health/ready")
    duration = time.time() - start

    assert response.status_code == 200
    # Should complete in under 500ms
    assert duration < 0.5


@pytest.mark.asyncio
async def test_readiness_probe_database_check():
    """Test /health/ready endpoint checks database connectivity"""
    # Initialize database pool
    await database.init_pool()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()

        # Verify database connectivity check
        assert data["checks"]["database"]["status"] == "healthy"

    await database.close_pool()


@pytest.mark.asyncio
async def test_readiness_probe_returns_503_on_database_failure():
    """Test /health/ready returns 503 when database is unavailable"""
    # Close the database pool to simulate database failure
    await database.close_pool()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/ready")

        assert response.status_code == 503
        data = response.json()

        assert data["status"] == "not_ready"
        assert "checks" in data
        assert data["checks"]["database"]["status"] == "unhealthy"
        assert "error" in data["checks"]["database"]

    # Reinitialize pool for other tests
    await database.init_pool()


@pytest.mark.asyncio
async def test_existing_health_endpoint_still_works(client):
    """Test existing /health endpoint is not affected by new endpoints"""
    response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "healthy"
    assert data["service"] == "orchestrator-3-stream"
    assert "websocket_connections" in data


@pytest.mark.asyncio
async def test_all_health_endpoints_respond(client):
    """Test all health endpoints are accessible"""
    endpoints = ["/health", "/health/live", "/health/ready"]

    for endpoint in endpoints:
        response = await client.get(endpoint)
        assert response.status_code in [200, 503], f"{endpoint} returned unexpected status"
        assert response.json() is not None


@pytest.mark.asyncio
async def test_readiness_probe_timestamp_format(client):
    """Test /health/ready returns valid ISO 8601 timestamp"""
    from datetime import datetime

    response = await client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()

    # Verify timestamp is valid ISO 8601 format
    timestamp = data["timestamp"]
    parsed = datetime.fromisoformat(timestamp)
    assert parsed is not None


@pytest.mark.asyncio
async def test_liveness_probe_timestamp_format(client):
    """Test /health/live returns valid ISO 8601 timestamp"""
    from datetime import datetime

    response = await client.get("/health/live")
    assert response.status_code == 200
    data = response.json()

    # Verify timestamp is valid ISO 8601 format
    timestamp = data["timestamp"]
    parsed = datetime.fromisoformat(timestamp)
    assert parsed is not None
