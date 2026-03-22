"""
bcrypt password hashing and verification utilities.

Uses the ``bcrypt`` library directly for secure, salted password storage.

Usage
-----
::

    from auth.password import hash_password, verify_password

    hashed = hash_password("s3cr3t!")
    assert verify_password("s3cr3t!", hashed)   # True
    assert not verify_password("wrong", hashed)  # False

Security notes
--------------
- ``hash_password`` never returns the plain-text password.
- ``verify_password`` uses constant-time comparison internally (bcrypt design),
  preventing timing-based side-channel attacks.
- Plain-text passwords must **never** be logged or included in any response.
"""

from __future__ import annotations

import bcrypt


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*.

    Parameters
    ----------
    plain:
        The raw, plain-text password supplied by the user.

    Returns
    -------
    str
        A bcrypt hash string safe to store in the database.
    """
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify *plain* against a stored bcrypt *hashed* value.

    Parameters
    ----------
    plain:
        The raw, plain-text password to check.
    hashed:
        The bcrypt hash previously returned by :func:`hash_password`.

    Returns
    -------
    bool
        ``True`` if the password matches, ``False`` otherwise.
    """
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
