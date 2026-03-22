"""
JWT token creation and decoding for the User Management API.

Tokens are HS256-signed JWTs containing a ``sub`` claim (user UUID as string)
and an ``exp`` claim (60 minutes from issuance).

Environment
-----------
JWT_SECRET
    Signing secret — must be at least 32 characters.  Loaded from the
    ``JWT_SECRET`` environment variable (or ``.env`` file via python-dotenv).

Usage
-----
::

    from auth.tokens import create_access_token, decode_access_token

    token = create_access_token(sub=str(user.id))
    token_data = decode_access_token(token)  # raises JWTError if invalid
    print(token_data.sub)  # user UUID string
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from jose import JWTError, jwt
from pydantic import BaseModel

load_dotenv()

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60


def _get_secret() -> str:
    """Return the JWT signing secret, raising if absent or too short."""
    secret = os.environ.get("JWT_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError(
            "JWT_SECRET environment variable must be set and at least 32 characters long."
        )
    return secret


class TokenData(BaseModel):
    """Decoded claims extracted from a valid JWT.

    Attributes
    ----------
    sub:
        Subject — the user's UUID serialised as a plain string.
    """

    sub: str  # user UUID as string


def create_access_token(sub: str) -> str:
    """Create a signed JWT access token for the given subject.

    Parameters
    ----------
    sub:
        The user's UUID (as a string) to embed in the ``sub`` claim.

    Returns
    -------
    str
        URL-safe, HS256-signed JWT string.
    """
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, object] = {"sub": sub, "exp": exp}
    return jwt.encode(payload, _get_secret(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> TokenData:
    """Decode and validate a JWT access token.

    Parameters
    ----------
    token:
        Raw JWT string (without the ``Bearer `` prefix).

    Returns
    -------
    TokenData
        Parsed claims.

    Raises
    ------
    jose.JWTError
        If the token is malformed, expired, or the signature is invalid.
    """
    payload = jwt.decode(token, _get_secret(), algorithms=[ALGORITHM])
    sub: str | None = payload.get("sub")
    if sub is None:
        raise JWTError("Token is missing the 'sub' claim.")
    return TokenData(sub=sub)
