"""
Tests for the setup-db feature.

Covers all acceptance criteria:
  1. Running the migration creates the ``users`` table.
  2. The asyncpg pool initialises without error when DATABASE_URL is set.
  3. ``UserRecord.model_validate(row)`` succeeds for a row fetched via asyncpg.

Rules (per CLAUDE.md):
  - Real database connections — no mocking.
  - Tests are ephemeral: every inserted row is cleaned up after the test.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Path setup — make db/ importable regardless of where pytest is invoked from
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent  # repo root
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env from the project root so DATABASE_URL is available
env_file = PROJECT_ROOT / ".env"
if env_file.exists():
    load_dotenv(env_file)

from db.connection import close_pool, get_db, init_pool  # noqa: E402
from db.models import UserCreate, UserRecord, UserUpdate  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MIGRATION_FILE = PROJECT_ROOT / "db" / "migrations" / "001_create_users.sql"


async def _raw_pool() -> asyncpg.Pool:
    """Return a bare asyncpg pool using DATABASE_URL."""
    return await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=2)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def pool():
    """Function-scoped pool fixture — created/torn down per test to share the same event loop."""
    await init_pool()
    yield
    await close_pool()


# ---------------------------------------------------------------------------
# AC 1 — Migration creates the users table
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migration_creates_users_table():
    """Running 001_create_users.sql must produce a ``users`` table."""
    assert MIGRATION_FILE.exists(), f"Migration file not found: {MIGRATION_FILE}"

    sql = MIGRATION_FILE.read_text()

    raw = await _raw_pool()
    try:
        async with raw.acquire() as conn:
            # Run the migration (idempotent — uses IF NOT EXISTS)
            await conn.execute(sql)

            # Confirm the table now exists in the public schema
            exists: bool = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM   information_schema.tables
                    WHERE  table_schema = 'public'
                    AND    table_name   = 'users'
                )
                """
            )
            assert exists, "users table was not found after running the migration"

            # Confirm expected columns are present
            columns = await conn.fetch(
                """
                SELECT column_name, data_type
                FROM   information_schema.columns
                WHERE  table_schema = 'public'
                AND    table_name   = 'users'
                ORDER  BY ordinal_position
                """
            )
            column_names = {row["column_name"] for row in columns}
            expected = {"id", "email", "display_name", "hashed_pw", "is_active", "created_at", "updated_at"}
            assert expected.issubset(column_names), (
                f"Missing columns: {expected - column_names}"
            )
    finally:
        await raw.close()


# ---------------------------------------------------------------------------
# AC 2 — Pool initialises without error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pool_initialises(pool):
    """init_pool() must succeed and the pool must answer a trivial query."""
    # ``pool`` fixture already called init_pool(); verify it's usable
    db_gen = get_db()
    conn = await db_gen.__anext__()
    try:
        result = await conn.fetchval("SELECT 1")
        assert result == 1
    finally:
        try:
            await db_gen.aclose()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# AC 3 — UserRecord.model_validate succeeds for an asyncpg row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_record_model_validate(pool):
    """Insert a row, fetch it via asyncpg, and validate it with UserRecord."""
    test_email = f"test-{uuid.uuid4()}@example.com"

    db_gen = get_db()
    conn = await db_gen.__anext__()
    try:
        # Insert a synthetic user row
        row = await conn.fetchrow(
            """
            INSERT INTO users (email, display_name, hashed_pw)
            VALUES ($1, $2, $3)
            RETURNING *
            """,
            test_email,
            "Test User",
            "$2b$12$hashedpassword",
        )

        assert row is not None, "INSERT ... RETURNING returned no row"

        # Core acceptance criterion
        user = UserRecord.model_validate(dict(row))

        assert user.email == test_email
        assert user.display_name == "Test User"
        assert user.is_active is True
        assert user.id is not None
        assert user.created_at is not None
        assert user.updated_at is not None

        # Ephemeral — clean up the test row
        await conn.execute("DELETE FROM users WHERE email = $1", test_email)
    finally:
        try:
            await db_gen.aclose()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Additional model validation tests
# ---------------------------------------------------------------------------


def test_user_create_model():
    """UserCreate captures email, display_name, and plain-text password."""
    payload = UserCreate(
        email="alice@example.com",
        display_name="Alice",
        password="secret123",
    )
    assert payload.email == "alice@example.com"
    assert payload.display_name == "Alice"
    assert payload.password == "secret123"


def test_user_update_model_optional():
    """UserUpdate.display_name defaults to None (no mutation required)."""
    payload = UserUpdate()
    assert payload.display_name is None

    payload_with_name = UserUpdate(display_name="Bob")
    assert payload_with_name.display_name == "Bob"


def test_user_record_from_attributes():
    """UserRecord must accept attribute-style objects (from_attributes=True)."""

    class FakeRow:
        id = uuid.uuid4()
        email = "row@example.com"
        display_name = "Row User"
        hashed_pw = "$2b$12$hash"
        is_active = True
        from datetime import timezone
        created_at = __import__("datetime").datetime.now(tz=timezone.utc)
        updated_at = __import__("datetime").datetime.now(tz=timezone.utc)

    user = UserRecord.model_validate(FakeRow())
    assert user.email == "row@example.com"
    assert user.is_active is True
