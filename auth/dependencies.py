"""
FastAPI dependencies for JWT bearer token authentication.

The primary export is :func:`get_current_user`, which can be used as a
``Depends(...)`` argument on any route that should require a valid, active user.

Usage
-----
::

    from fastapi import APIRouter, Depends
    from auth.dependencies import get_current_user
    from db.models import UserRecord

    router = APIRouter()

    @router.get("/users/me")
    async def me(current_user: UserRecord = Depends(get_current_user)):
        return {"email": current_user.email}

Raises
------
fastapi.HTTPException (401)
    - Token is missing, malformed, or expired.
    - The user referenced by the token does not exist.
    - The user account is inactive (soft-deleted).
"""

from __future__ import annotations

import asyncpg
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

from auth.tokens import decode_access_token
from db.connection import get_db
from db.models import UserRecord

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

_INACTIVE_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Inactive user",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    conn: asyncpg.Connection = Depends(get_db),
) -> UserRecord:
    """FastAPI dependency that resolves a bearer token to a :class:`~db.models.UserRecord`.

    Parameters
    ----------
    token:
        Raw JWT string extracted from the ``Authorization: Bearer <token>`` header
        by :data:`oauth2_scheme`.
    conn:
        Async database connection from the pool (injected by :func:`~db.connection.get_db`).

    Returns
    -------
    UserRecord
        The authenticated, active user.

    Raises
    ------
    HTTPException(401)
        If the token is invalid, expired, the user does not exist, or the
        user account is inactive.
    """
    # --- Decode JWT -------------------------------------------------------
    try:
        token_data = decode_access_token(token)
    except JWTError:
        raise _CREDENTIALS_EXCEPTION

    # --- Fetch user from DB -----------------------------------------------
    row = await conn.fetchrow(
        "SELECT id, email, display_name, hashed_pw, is_active, created_at, updated_at "
        "FROM users WHERE id = $1::uuid",
        token_data.sub,
    )
    if row is None:
        raise _CREDENTIALS_EXCEPTION

    user = UserRecord.model_validate(dict(row))

    # --- Guard inactive accounts ------------------------------------------
    if not user.is_active:
        raise _INACTIVE_EXCEPTION

    return user
