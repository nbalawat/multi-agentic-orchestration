"""
Retry Logic with Exponential Backoff

Provides retry decorators and utilities for transient failure recovery,
specifically targeting asyncpg database operations.

Features:
- Exponential backoff with configurable base delay and max delay
- Configurable max attempts
- Selective retry based on exception types (transient vs permanent)
- Logging of retry attempts with context
- Request ID propagation for tracing
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
from typing import Any, Callable, Optional, Sequence, Type

import asyncpg

from .error_types import DatabaseError, ErrorCode, RetryExhaustedError

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# TRANSIENT ERROR DETECTION
# ═══════════════════════════════════════════════════════════

# asyncpg error codes that are transient and worth retrying
TRANSIENT_POSTGRES_ERRORS = {
    # Connection-level errors
    asyncpg.TooManyConnectionsError,
    asyncpg.CannotConnectNowError,
    asyncpg.ConnectionDoesNotExistError,
    asyncpg.ConnectionFailureError,
    # Transaction-level errors (serialization failures)
    asyncpg.SerializationError,
    asyncpg.DeadlockDetectedError,
    # Temporary resource errors
    asyncpg.TooManyConnectionsError,
}

# Python-level connection/timeout errors to retry
TRANSIENT_BASE_ERRORS = (
    ConnectionError,
    TimeoutError,
    asyncio.TimeoutError,
)


def is_transient_error(exc: Exception) -> bool:
    """
    Determine if an exception represents a transient (retryable) failure.

    Transient errors are temporary conditions that may resolve on retry,
    such as connection hiccups, deadlocks, or serialization conflicts.

    Args:
        exc: The exception to evaluate

    Returns:
        True if the error is transient and should be retried
    """
    # Check asyncpg-specific transient errors
    for error_type in TRANSIENT_POSTGRES_ERRORS:
        if isinstance(exc, error_type):
            return True

    # Check base Python transient errors
    if isinstance(exc, TRANSIENT_BASE_ERRORS):
        return True

    # Check for asyncpg.PostgresConnectionError (base class)
    if isinstance(exc, asyncpg.PostgresConnectionError):
        return True

    # Check for query_canceled (could be transient under load)
    if isinstance(exc, asyncpg.QueryCanceledError):
        return True

    return False


# ═══════════════════════════════════════════════════════════
# RETRY DECORATOR
# ═══════════════════════════════════════════════════════════


def with_retry(
    max_attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 10.0,
    jitter: bool = True,
    retryable_exceptions: Optional[Sequence[Type[Exception]]] = None,
    operation_name: Optional[str] = None,
):
    """
    Decorator for async functions that adds retry logic with exponential backoff.

    Implements full jitter exponential backoff:
    - Attempt 1: immediate
    - Attempt 2: random(0, base_delay * 2^0) → up to base_delay
    - Attempt 3: random(0, base_delay * 2^1) → up to base_delay * 2
    - ...up to max_delay cap

    Args:
        max_attempts: Maximum number of attempts (including first try). Default: 3
        base_delay: Base delay in seconds for backoff calculation. Default: 0.5
        max_delay: Maximum delay in seconds between retries. Default: 10.0
        jitter: Add random jitter to prevent thundering herd. Default: True
        retryable_exceptions: Specific exception types to retry on. If None,
            uses is_transient_error() to determine retryability.
        operation_name: Human-readable operation name for logging. If None,
            uses the function name.

    Returns:
        Decorated async function with retry logic

    Example:
        @with_retry(max_attempts=3, base_delay=0.5)
        async def get_orchestrator():
            async with get_connection() as conn:
                return await conn.fetchrow("SELECT ...")
    """

    def decorator(func: Callable) -> Callable:
        op_name = operation_name or func.__qualname__

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Optional[Exception] = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)

                except Exception as exc:
                    last_exception = exc

                    # Determine if this exception is retryable
                    should_retry = False
                    if retryable_exceptions:
                        should_retry = isinstance(exc, tuple(retryable_exceptions))
                    else:
                        should_retry = is_transient_error(exc)

                    if not should_retry or attempt >= max_attempts:
                        # Not retryable or out of attempts
                        if attempt > 1:
                            logger.error(
                                f"[retry] '{op_name}' failed permanently on attempt "
                                f"{attempt}/{max_attempts}: {type(exc).__name__}: {exc}"
                            )
                        # Wrap in RetryExhaustedError if we've been retrying
                        if attempt > 1:
                            raise RetryExhaustedError(
                                operation=op_name,
                                attempts=attempt,
                                last_error=exc,
                            ) from exc
                        raise

                    # Calculate backoff delay
                    exponent = attempt - 1  # 0-indexed for backoff
                    delay = min(base_delay * (2**exponent), max_delay)
                    if jitter:
                        delay = random.uniform(0, delay)

                    logger.warning(
                        f"[retry] '{op_name}' attempt {attempt}/{max_attempts} failed "
                        f"with transient error: {type(exc).__name__}: {exc}. "
                        f"Retrying in {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)

            # Should never reach here, but satisfy type checker
            assert last_exception is not None
            raise RetryExhaustedError(
                operation=op_name,
                attempts=max_attempts,
                last_error=last_exception,
            ) from last_exception

        return wrapper

    return decorator


# ═══════════════════════════════════════════════════════════
# CONVENIENCE WRAPPERS
# ═══════════════════════════════════════════════════════════


def db_retry(
    max_attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    operation_name: Optional[str] = None,
):
    """
    Convenience decorator specifically for database operations.

    Configured with sensible defaults for PostgreSQL:
    - 3 attempts total
    - 0.5s base delay with exponential backoff
    - 8s max delay
    - Full jitter to prevent thundering herd

    Args:
        max_attempts: Max retry attempts. Default: 3
        base_delay: Base delay in seconds. Default: 0.5
        max_delay: Max delay cap in seconds. Default: 8.0
        operation_name: Optional name for logging

    Example:
        @db_retry()
        async def get_orchestrator_by_id(orchestrator_id: uuid.UUID):
            async with get_connection() as conn:
                return await conn.fetchrow("SELECT ...")
    """
    return with_retry(
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
        jitter=True,
        operation_name=operation_name,
    )
