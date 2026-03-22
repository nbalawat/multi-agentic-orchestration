"""
Integration tests for the auth feature (setup-auth).

Acceptance criteria verified:
- POST /auth/token with valid credentials returns a JWT (200).
- POST /auth/token with wrong password returns 401.
- A protected route rejects missing / expired tokens with 401.
- Passwords are never returned in any response payload.

These tests use a *real* PostgreSQL connection (DATABASE_URL from .env) and
are fully ephemeral — all test data is created and cleaned up within each
test.
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest
import pytest_asyncio
from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from auth.dependencies import get_current_user
from auth.password import hash_password, verify_password
from auth.router import router as auth_router
from auth.tokens import create_access_token, decode_access_token
from db.connection import close_pool, get_db, init_pool
from db.models import UserRecord

load_dotenv()

# ---------------------------------------------------------------------------
# Shared test application
# ---------------------------------------------------------------------------

_test_app = FastAPI()
_test_app.include_router(auth_router)


@_test_app.get("/protected", response_model=dict)
async def protected_route(current_user: UserRecord = Depends(get_current_user)) -> dict:
    """Minimal protected endpoint used in tests."""
    return {"email": current_user.email}


# ---------------------------------------------------------------------------
# Session-scoped database pool
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_pool() -> asyncpg.Pool:
    """Create a real asyncpg pool for the duration of a single test."""
    dsn = os.environ["DATABASE_URL"]
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
    yield pool
    await pool.close()


# ---------------------------------------------------------------------------
# Per-test user fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def test_user(db_pool: asyncpg.Pool) -> UserRecord:
    """Insert a fresh test user and delete it after the test."""
    email = f"test-{uuid.uuid4().hex[:8]}@example.com"
    password = "Test@1234!"
    hashed = hash_password(password)

    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO users (email, display_name, hashed_pw)
            VALUES ($1, $2, $3)
            RETURNING id, email, display_name, hashed_pw, is_active, created_at, updated_at
            """,
            email,
            "Test User",
            hashed,
        )
        user = UserRecord.model_validate(dict(row))

    yield user, password  # yield both so tests can use the plain password

    # Cleanup — hard delete the ephemeral test user
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM users WHERE id = $1", user.id)


# ---------------------------------------------------------------------------
# HTTP client fixture wired to the real pool
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(db_pool: asyncpg.Pool):
    """ASGI test client with the db pool injected."""

    async def _override_get_db():
        async with db_pool.acquire() as conn:
            yield conn

    _test_app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=_test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    _test_app.dependency_overrides.clear()


# ===========================================================================
# Unit tests — password utilities
# ===========================================================================


class TestPasswordUtilities:
    def test_hash_produces_non_empty_string(self):
        hashed = hash_password("secret")
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_hash_does_not_equal_plain(self):
        plain = "my_plain_password"
        assert hash_password(plain) != plain

    def test_verify_correct_password(self):
        plain = "correct_password"
        hashed = hash_password(plain)
        assert verify_password(plain, hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("correct")
        assert verify_password("wrong", hashed) is False

    def test_two_hashes_of_same_password_differ(self):
        """bcrypt uses random salt — same input must never produce identical hashes."""
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2


# ===========================================================================
# Unit tests — JWT token utilities
# ===========================================================================


class TestTokenUtilities:
    def test_create_and_decode_round_trip(self):
        sub = str(uuid.uuid4())
        token = create_access_token(sub=sub)
        token_data = decode_access_token(token)
        assert token_data.sub == sub

    def test_decode_invalid_token_raises(self):
        from jose import JWTError

        with pytest.raises(JWTError):
            decode_access_token("not.a.valid.token")

    def test_decode_tampered_token_raises(self):
        from jose import JWTError

        token = create_access_token(sub=str(uuid.uuid4()))
        tampered = token[:-4] + "xxxx"
        with pytest.raises(JWTError):
            decode_access_token(tampered)

    def test_expired_token_raises(self):
        """Tokens with a past expiry must be rejected."""
        from datetime import datetime, timedelta, timezone

        from jose import JWTError, jwt

        secret = os.environ["JWT_SECRET"]
        payload = {
            "sub": str(uuid.uuid4()),
            "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
        }
        expired_token = jwt.encode(payload, secret, algorithm="HS256")
        with pytest.raises(JWTError):
            decode_access_token(expired_token)


# ===========================================================================
# Integration tests — POST /auth/token
# ===========================================================================


class TestAuthTokenEndpoint:
    async def test_valid_credentials_return_200_with_token(self, client, test_user):
        user, plain_pw = test_user
        resp = await client.post(
            "/auth/token",
            data={"username": user.email, "password": plain_pw},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert len(body["access_token"]) > 0

    async def test_token_contains_correct_sub(self, client, test_user):
        user, plain_pw = test_user
        resp = await client.post(
            "/auth/token",
            data={"username": user.email, "password": plain_pw},
        )
        assert resp.status_code == 200
        token_data = decode_access_token(resp.json()["access_token"])
        assert token_data.sub == str(user.id)

    async def test_wrong_password_returns_401(self, client, test_user):
        user, _ = test_user
        resp = await client.post(
            "/auth/token",
            data={"username": user.email, "password": "totally_wrong_pw"},
        )
        assert resp.status_code == 401

    async def test_unknown_email_returns_401(self, client):
        resp = await client.post(
            "/auth/token",
            data={"username": "nobody@example.com", "password": "whatever"},
        )
        assert resp.status_code == 401

    async def test_response_does_not_contain_password(self, client, test_user):
        user, plain_pw = test_user
        resp = await client.post(
            "/auth/token",
            data={"username": user.email, "password": plain_pw},
        )
        body_text = resp.text
        assert plain_pw not in body_text
        assert "hashed_pw" not in body_text
        assert "password" not in body_text.lower().replace("password", "")  # field name only

    async def test_inactive_user_returns_401(self, db_pool, client, test_user):
        user, plain_pw = test_user
        # Soft-delete the user
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET is_active = FALSE WHERE id = $1", user.id)
        try:
            resp = await client.post(
                "/auth/token",
                data={"username": user.email, "password": plain_pw},
            )
            assert resp.status_code == 401
        finally:
            # Restore so the fixture cleanup can run
            async with db_pool.acquire() as conn:
                await conn.execute("UPDATE users SET is_active = TRUE WHERE id = $1", user.id)


# ===========================================================================
# Integration tests — protected route (get_current_user dependency)
# ===========================================================================


class TestProtectedRoute:
    async def test_valid_token_grants_access(self, client, test_user):
        user, plain_pw = test_user
        # Obtain real token via the endpoint
        token_resp = await client.post(
            "/auth/token",
            data={"username": user.email, "password": plain_pw},
        )
        token = token_resp.json()["access_token"]

        resp = await client.get("/protected", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["email"] == user.email

    async def test_missing_token_returns_401(self, client):
        resp = await client.get("/protected")
        assert resp.status_code == 401

    async def test_invalid_token_returns_401(self, client):
        resp = await client.get("/protected", headers={"Authorization": "Bearer notavalidtoken"})
        assert resp.status_code == 401

    async def test_expired_token_returns_401(self, client, test_user):
        from datetime import datetime, timedelta, timezone

        from jose import jwt

        user, _ = test_user
        secret = os.environ["JWT_SECRET"]
        expired_payload = {
            "sub": str(user.id),
            "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
        }
        expired_token = jwt.encode(expired_payload, secret, algorithm="HS256")
        resp = await client.get(
            "/protected",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert resp.status_code == 401

    async def test_token_for_nonexistent_user_returns_401(self, client):
        """A token for a user UUID that doesn't exist in the DB must be rejected."""
        ghost_token = create_access_token(sub=str(uuid.uuid4()))
        resp = await client.get(
            "/protected",
            headers={"Authorization": f"Bearer {ghost_token}"},
        )
        assert resp.status_code == 401
