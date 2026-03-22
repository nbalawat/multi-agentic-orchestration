"""
Auth router — ``POST /auth/token``.

Implements the OAuth2 *password* grant flow: clients submit ``username``
(email address) and ``password`` as form fields and receive a short-lived
JWT access token in return.

Endpoints
---------
POST /auth/token
    Authenticate with email + password; returns a JWT bearer token.

Response schema::

    {
        "access_token": "<jwt>",
        "token_type": "bearer"
    }

Error codes
-----------
401
    Wrong email, wrong password, or the account is inactive.
"""

from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from auth.password import verify_password
from auth.tokens import create_access_token
from db.connection import get_db
from db.models import UserRecord

router = APIRouter(prefix="/auth", tags=["auth"])

_INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Incorrect email or password",
    headers={"WWW-Authenticate": "Bearer"},
)

_INACTIVE_USER = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Inactive user",
    headers={"WWW-Authenticate": "Bearer"},
)


class TokenResponse(BaseModel):
    """Response body for a successful token request.

    Attributes
    ----------
    access_token:
        Signed JWT string.
    token_type:
        Always ``"bearer"``.
    """

    access_token: str
    token_type: str = "bearer"


@router.post("/token", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    conn: asyncpg.Connection = Depends(get_db),
) -> TokenResponse:
    """Issue a JWT access token for a valid user credential pair.

    The ``username`` field of the OAuth2 password form is treated as the
    user's **email address**.

    Parameters
    ----------
    form_data:
        Standard OAuth2 ``application/x-www-form-urlencoded`` form containing
        ``username`` and ``password`` fields.
    conn:
        Async database connection (injected by :func:`~db.connection.get_db`).

    Returns
    -------
    TokenResponse
        ``{"access_token": "<jwt>", "token_type": "bearer"}``.

    Raises
    ------
    HTTPException(401)
        If the email does not exist, the password is wrong, or the account
        is inactive.
    """
    # --- Look up user by email --------------------------------------------
    row = await conn.fetchrow(
        "SELECT id, email, display_name, hashed_pw, is_active, created_at, updated_at "
        "FROM users WHERE email = $1",
        form_data.username,
    )
    if row is None:
        raise _INVALID_CREDENTIALS

    user = UserRecord.model_validate(dict(row))

    # --- Verify password (constant-time) ----------------------------------
    if not verify_password(form_data.password, user.hashed_pw):
        raise _INVALID_CREDENTIALS

    # --- Guard inactive accounts ------------------------------------------
    if not user.is_active:
        raise _INACTIVE_USER

    # --- Issue token ------------------------------------------------------
    token = create_access_token(sub=str(user.id))
    return TokenResponse(access_token=token)
