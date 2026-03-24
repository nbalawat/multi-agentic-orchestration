"""
Shared Test Fixtures for Integration Tests

Provides Docker testcontainers for PostgreSQL and Redis, database schema setup,
test data factories, and cleanup utilities for ephemeral integration testing.

NO MOCKING - All tests use real PostgreSQL and Redis via testcontainers.
Tests are fully ephemeral: setup → execute → cleanup.

Run with: uv run pytest tests/ -v
"""

import pytest
import pytest_asyncio
import asyncio
import asyncpg
import redis.asyncio as aioredis
import uuid
import os
from pathlib import Path
from typing import AsyncGenerator, Dict, Any
from faker import Faker
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

# Import database modules
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


fake = Faker()


# ═══════════════════════════════════════════════════════════
# DOCKER CONFIGURATION FOR MACOS
# ═══════════════════════════════════════════════════════════


def configure_docker_for_macos():
    """
    Configure Docker socket path for macOS compatibility.

    On macOS, Docker Desktop may use ~/.docker/run/docker.sock instead of
    /var/run/docker.sock. This function detects the correct socket and sets
    the DOCKER_HOST environment variable if needed.
    """
    if os.environ.get("DOCKER_HOST"):
        # Already configured
        return

    # Check common Docker socket locations
    home = Path.home()
    mac_socket = home / ".docker" / "run" / "docker.sock"
    colima_socket = home / ".colima" / "default" / "docker.sock"
    standard_socket = Path("/var/run/docker.sock")

    if mac_socket.exists():
        os.environ["DOCKER_HOST"] = f"unix://{mac_socket}"
        print(f"✅ Configured Docker socket: {mac_socket}")
    elif colima_socket.exists():
        os.environ["DOCKER_HOST"] = f"unix://{colima_socket}"
        print(f"✅ Configured Docker socket: {colima_socket}")
    elif standard_socket.exists():
        # Standard location, no configuration needed
        print(f"✅ Using standard Docker socket: {standard_socket}")
    else:
        print("⚠️  Docker socket not found at standard locations")


# Configure Docker before any containers are created
configure_docker_for_macos()

# Disable Ryuk container for macOS compatibility
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")


# ═══════════════════════════════════════════════════════════
# TESTCONTAINER FIXTURES
# ═══════════════════════════════════════════════════════════


@pytest.fixture(scope="session")
def postgres_container():
    """
    Start PostgreSQL testcontainer for the entire test session.

    Reuses the same container across all tests for performance.
    """
    container = PostgresContainer(
        image="postgres:16-alpine",
        username="test",
        password="test",
        dbname="testdb"
    )
    container.start()

    print(f"\n✅ PostgreSQL testcontainer started: {container.get_connection_url()}")

    yield container

    container.stop()
    print("\n✅ PostgreSQL testcontainer stopped")


@pytest.fixture(scope="session")
def redis_container():
    """
    Start Redis testcontainer for the entire test session.

    Reuses the same container across all tests for performance.
    """
    container = RedisContainer(image="redis:7-alpine")
    container.start()

    print(f"\n✅ Redis testcontainer started: {container.get_connection_url()}")

    yield container

    container.stop()
    print("\n✅ Redis testcontainer stopped")


@pytest.fixture(scope="session")
def postgres_url(postgres_container) -> str:
    """
    Get PostgreSQL connection URL from testcontainer.

    Converts SQLAlchemy format (postgresql+psycopg2://) to asyncpg format (postgresql://)
    """
    url = postgres_container.get_connection_url()
    # Convert SQLAlchemy URL to asyncpg format
    if "postgresql+psycopg2://" in url:
        url = url.replace("postgresql+psycopg2://", "postgresql://")
    return url


@pytest.fixture(scope="session")
def redis_url(redis_container) -> str:
    """Get Redis connection URL from testcontainer."""
    return redis_container.get_connection_url()


# ═══════════════════════════════════════════════════════════
# DATABASE SCHEMA SETUP
# ═══════════════════════════════════════════════════════════


@pytest_asyncio.fixture(scope="session")
async def db_schema(postgres_url: str):
    """
    Apply database migrations to create schema in testcontainer.

    Runs once per test session.
    """
    conn = await asyncpg.connect(postgres_url)

    try:
        # Get migration files in order
        # Navigate from tests/conftest.py -> orchestrator/db/migrations
        migrations_dir = Path(__file__).parent.parent.parent / "db" / "migrations"

        if not migrations_dir.exists():
            raise FileNotFoundError(f"Migrations directory not found: {migrations_dir}")

        migration_files = list(migrations_dir.glob("*.sql"))

        if not migration_files:
            raise FileNotFoundError(f"No migration files found in: {migrations_dir}")

        # Sort migrations by numeric prefix (0_, 1_, 2_, etc.)
        def migration_sort_key(path: Path) -> int:
            """Extract numeric prefix from migration filename for sorting."""
            name = path.stem  # filename without extension
            # Extract first number from filename (e.g., "0_orchestrator" -> 0, "10_projects" -> 10)
            import re
            match = re.match(r'^(\d+)', name)
            return int(match.group(1)) if match else 999

        migration_files = sorted(migration_files, key=migration_sort_key)

        print(f"\n🔄 Applying {len(migration_files)} migrations...")

        for migration_file in migration_files:
            sql = migration_file.read_text()
            print(f"   📄 Applying {migration_file.name}")
            await conn.execute(sql)

        print("✅ All migrations applied successfully")

        yield conn

    finally:
        await conn.close()


# ═══════════════════════════════════════════════════════════
# DATABASE CONNECTION POOL FIXTURES
# ═══════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def db_pool(postgres_url: str, db_schema) -> AsyncGenerator[asyncpg.Pool, None]:
    """
    Create a fresh database connection pool for each test.

    Provides isolated connection pool per test function.
    """
    pool = await asyncpg.create_pool(
        postgres_url,
        min_size=2,
        max_size=5,
        command_timeout=30
    )

    yield pool

    await pool.close()


@pytest_asyncio.fixture
async def db_conn(db_pool: asyncpg.Pool) -> AsyncGenerator[asyncpg.Connection, None]:
    """
    Provide a database connection with automatic transaction rollback.

    Each test gets a fresh connection in a transaction that's rolled back
    after the test completes, ensuring complete isolation between tests.
    """
    async with db_pool.acquire() as conn:
        # Start transaction
        tx = conn.transaction()
        await tx.start()

        yield conn

        # Rollback transaction to clean up test data
        await tx.rollback()


# ═══════════════════════════════════════════════════════════
# REDIS CONNECTION FIXTURES
# ═══════════════════════════════════════════════════════════


@pytest_asyncio.fixture
async def redis_client(redis_url: str) -> AsyncGenerator[aioredis.Redis, None]:
    """
    Create Redis client for each test.

    Automatically flushes all keys after test completes.
    """
    client = aioredis.from_url(redis_url, decode_responses=True)

    yield client

    # Cleanup: flush all Redis keys
    await client.flushall()
    await client.aclose()


# ═══════════════════════════════════════════════════════════
# TEST DATA FACTORIES
# ═══════════════════════════════════════════════════════════


class TestDataFactory:
    """Factory for generating realistic test data."""

    def __init__(self, conn: asyncpg.Connection):
        self.conn = conn
        self.fake = fake

    async def create_workspace(
        self,
        name: str = None,
        description: str = None,
        status: str = "active"
    ) -> Dict[str, Any]:
        """Create a test workspace."""
        import json
        name = name or self.fake.company()
        description = description or self.fake.catch_phrase()
        root_path = f"/tmp/test-workspace-{uuid.uuid4()}"

        row = await self.conn.fetchrow(
            """
            INSERT INTO workspaces (name, description, root_path, status, metadata)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            RETURNING *
            """,
            name, description, root_path, status, json.dumps({})
        )

        return dict(row)

    async def create_project(
        self,
        workspace_id: uuid.UUID,
        name: str = None,
        archetype: str = "greenfield",
        current_phase: str = "research"
    ) -> Dict[str, Any]:
        """Create a test project."""
        import json
        name = name or self.fake.bs()
        repo_path = f"/tmp/test-repo-{uuid.uuid4()}"

        row = await self.conn.fetchrow(
            """
            INSERT INTO projects (
                workspace_id, name, repo_path, archetype,
                current_phase, phase_status, metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
            RETURNING *
            """,
            workspace_id, name, repo_path, archetype,
            current_phase, "not_started", json.dumps({})
        )

        return dict(row)

    async def create_orchestrator_agent(
        self,
        system_prompt: str = None,
        working_dir: str = None
    ) -> Dict[str, Any]:
        """Create a test orchestrator agent."""
        import json
        system_prompt = system_prompt or "Test orchestrator"
        working_dir = working_dir or f"/tmp/test-orch-{uuid.uuid4()}"
        session_id = f"session-{uuid.uuid4()}"

        row = await self.conn.fetchrow(
            """
            INSERT INTO orchestrator_agents (
                session_id, system_prompt, status, working_dir, metadata
            )
            VALUES ($1, $2, $3, $4, $5::jsonb)
            RETURNING *
            """,
            session_id, system_prompt, "idle", working_dir, json.dumps({})
        )

        return dict(row)

    async def create_agent(
        self,
        orchestrator_agent_id: uuid.UUID,
        name: str = None,
        model: str = "claude-sonnet-4"
    ) -> Dict[str, Any]:
        """Create a test agent."""
        import json
        name = name or f"test-agent-{self.fake.word()}"
        session_id = f"session-{uuid.uuid4()}"

        row = await self.conn.fetchrow(
            """
            INSERT INTO agents (
                orchestrator_agent_id, name, model, session_id,
                status, metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6::jsonb)
            RETURNING *
            """,
            orchestrator_agent_id, name, model, session_id, "idle", json.dumps({})
        )

        return dict(row)

    async def create_feature(
        self,
        project_id: uuid.UUID,
        feature_id: str = None,
        name: str = None,
        status: str = "planned"
    ) -> Dict[str, Any]:
        """Create a test feature."""
        import json
        feature_id = feature_id or f"F{self.fake.random_int(min=1, max=999):03d}"
        name = name or self.fake.catch_phrase()

        row = await self.conn.fetchrow(
            """
            INSERT INTO features (
                project_id, feature_id, name, description,
                category, status, metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
            RETURNING *
            """,
            project_id, feature_id, name, self.fake.text(max_nb_chars=100),
            "core", status, json.dumps({})
        )

        return dict(row)


@pytest.fixture
def test_factory(db_conn: asyncpg.Connection) -> TestDataFactory:
    """Provide test data factory for each test."""
    return TestDataFactory(db_conn)


# ═══════════════════════════════════════════════════════════
# CLEANUP UTILITIES
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def cleanup_tracker():
    """
    Track created resources for cleanup verification.

    Usage:
        async def test_example(cleanup_tracker):
            workspace_id = await create_workspace()
            cleanup_tracker.add("workspace", workspace_id)

            # Test assertions...

            # Verify cleanup happened
            assert await cleanup_tracker.verify_deleted(conn, "workspace", workspace_id)
    """
    resources = []

    class CleanupTracker:
        def add(self, resource_type: str, resource_id: uuid.UUID):
            """Track a resource for cleanup verification."""
            resources.append((resource_type, resource_id))

        async def verify_deleted(
            self,
            conn: asyncpg.Connection,
            resource_type: str,
            resource_id: uuid.UUID
        ) -> bool:
            """Verify that a resource was deleted."""
            table_map = {
                "workspace": "workspaces",
                "project": "projects",
                "agent": "agents",
                "orchestrator": "orchestrator_agents",
                "feature": "features"
            }

            table = table_map.get(resource_type)
            if not table:
                raise ValueError(f"Unknown resource type: {resource_type}")

            result = await conn.fetchval(
                f"SELECT COUNT(*) FROM {table} WHERE id = $1",
                resource_id
            )

            return result == 0

    return CleanupTracker()


# ═══════════════════════════════════════════════════════════
# ISOLATION VERIFICATION UTILITIES
# ═══════════════════════════════════════════════════════════


async def verify_workspace_isolation(
    conn: asyncpg.Connection,
    workspace1_id: uuid.UUID,
    workspace2_id: uuid.UUID
) -> bool:
    """
    Verify that two workspaces are properly isolated.

    Returns True if:
    - Projects from workspace1 are not visible in workspace2
    - Projects from workspace2 are not visible in workspace1
    """
    # Get projects for workspace1
    ws1_projects = await conn.fetch(
        "SELECT id FROM projects WHERE workspace_id = $1",
        workspace1_id
    )

    # Get projects for workspace2
    ws2_projects = await conn.fetch(
        "SELECT id FROM projects WHERE workspace_id = $1",
        workspace2_id
    )

    # Verify no overlap
    ws1_project_ids = {row['id'] for row in ws1_projects}
    ws2_project_ids = {row['id'] for row in ws2_projects}

    return ws1_project_ids.isdisjoint(ws2_project_ids)


@pytest.fixture
def isolation_verifier(db_conn: asyncpg.Connection):
    """Provide workspace isolation verification utility."""
    async def verify(workspace1_id: uuid.UUID, workspace2_id: uuid.UUID) -> bool:
        return await verify_workspace_isolation(db_conn, workspace1_id, workspace2_id)

    return verify
