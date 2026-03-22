"""
Circuit Breaker Pattern for External API Calls

Implements the circuit breaker pattern for Claude API calls to prevent
cascading failures and provide graceful degradation when the API is
unavailable.

States:
  CLOSED   → Normal operation. Requests flow through.
  OPEN     → API is unavailable. Requests are rejected immediately.
  HALF_OPEN → Testing if API has recovered. One probe request allowed.

Transitions:
  CLOSED → OPEN:      failure_threshold consecutive failures
  OPEN → HALF_OPEN:   reset_timeout seconds have elapsed
  HALF_OPEN → CLOSED: probe request succeeds
  HALF_OPEN → OPEN:   probe request fails

Usage:
    breaker = CircuitBreaker(
        name="claude-api",
        failure_threshold=5,
        reset_timeout=60.0,
    )

    async def call_claude():
        async with breaker:
            result = await claude_api.call(...)
        return result
"""

from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Callable, Optional

from .error_types import CircuitBreakerOpenError, ClaudeAPIError, ErrorCode

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# CIRCUIT BREAKER STATE
# ═══════════════════════════════════════════════════════════


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "CLOSED"       # Normal operation
    OPEN = "OPEN"           # Failing — reject all requests
    HALF_OPEN = "HALF_OPEN" # Testing recovery — allow one probe


# ═══════════════════════════════════════════════════════════
# CIRCUIT BREAKER IMPLEMENTATION
# ═══════════════════════════════════════════════════════════


class CircuitBreaker:
    """
    Thread-safe asyncio circuit breaker for external API protection.

    Tracks consecutive failures and opens the circuit when the failure
    threshold is exceeded. After a reset timeout, allows one probe
    request to test recovery.

    Args:
        name: Service name for logging and error messages
        failure_threshold: Consecutive failures before opening circuit. Default: 5
        reset_timeout: Seconds to wait in OPEN state before trying HALF_OPEN. Default: 60.0
        success_threshold: Successes required in HALF_OPEN to close circuit. Default: 1
        timeout: Per-call timeout in seconds. None disables timeout. Default: None

    Attributes:
        state: Current circuit state (CLOSED/OPEN/HALF_OPEN)
        failure_count: Current consecutive failure count
        last_failure_time: Timestamp of last failure (epoch seconds)
        total_failures: Total failures since creation
        total_successes: Total successes since creation
        total_rejected: Total requests rejected due to open circuit
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
        success_threshold: int = 1,
        timeout: Optional[float] = None,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.success_threshold = success_threshold
        self.timeout = timeout

        # State tracking
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None

        # Metrics
        self.total_failures = 0
        self.total_successes = 0
        self.total_rejected = 0

        # Lock for thread-safe state transitions
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Current circuit state."""
        return self._state

    @property
    def failure_count(self) -> int:
        """Current consecutive failure count."""
        return self._failure_count

    @property
    def last_failure_time(self) -> Optional[float]:
        """Timestamp of last failure."""
        return self._last_failure_time

    def get_status(self) -> dict[str, Any]:
        """
        Get circuit breaker status as a dictionary.

        Returns:
            Dictionary with current state, counts, and timing info.
        """
        time_since_failure = None
        time_until_reset = None

        if self._last_failure_time is not None:
            time_since_failure = time.monotonic() - self._last_failure_time
            if self._state == CircuitState.OPEN:
                time_until_reset = max(0.0, self.reset_timeout - time_since_failure)

        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
            "total_rejected": self.total_rejected,
            "last_failure_time": self._last_failure_time,
            "time_since_last_failure_s": time_since_failure,
            "time_until_reset_s": time_until_reset,
        }

    async def _check_state(self) -> None:
        """
        Check and potentially transition circuit state.

        Transitions OPEN → HALF_OPEN if reset_timeout has elapsed.

        Raises:
            CircuitBreakerOpenError: If circuit is OPEN and timeout hasn't elapsed
        """
        async with self._lock:
            if self._state == CircuitState.OPEN:
                elapsed = time.monotonic() - (self._last_failure_time or 0)
                if elapsed >= self.reset_timeout:
                    self._state = CircuitState.HALF_OPEN
                    logger.info(
                        f"[circuit_breaker] '{self.name}' transitioning OPEN → HALF_OPEN "
                        f"after {elapsed:.1f}s (threshold: {self.reset_timeout}s)"
                    )
                else:
                    remaining = self.reset_timeout - elapsed
                    self.total_rejected += 1
                    raise CircuitBreakerOpenError(
                        service=self.name,
                        failure_count=self._failure_count,
                        reset_timeout=remaining,
                    )

    async def _record_success(self) -> None:
        """Record a successful call and potentially close the circuit."""
        async with self._lock:
            self.total_successes += 1

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    logger.info(
                        f"[circuit_breaker] '{self.name}' transitioning HALF_OPEN → CLOSED "
                        f"after successful probe"
                    )
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success (consecutive failures required)
                if self._failure_count > 0:
                    self._failure_count = 0
                    logger.debug(
                        f"[circuit_breaker] '{self.name}' failure count reset to 0 after success"
                    )

    async def _record_failure(self, exc: Exception) -> None:
        """Record a failed call and potentially open the circuit."""
        async with self._lock:
            self.total_failures += 1
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # Probe failed — go back to OPEN
                self._state = CircuitState.OPEN
                self._success_count = 0
                logger.warning(
                    f"[circuit_breaker] '{self.name}' transitioning HALF_OPEN → OPEN "
                    f"after probe failure: {type(exc).__name__}: {exc}"
                )
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._state = CircuitState.OPEN
                    logger.error(
                        f"[circuit_breaker] '{self.name}' transitioning CLOSED → OPEN "
                        f"after {self._failure_count} consecutive failures. "
                        f"Last error: {type(exc).__name__}: {exc}"
                    )
                else:
                    logger.warning(
                        f"[circuit_breaker] '{self.name}' failure {self._failure_count}/"
                        f"{self.failure_threshold}: {type(exc).__name__}: {exc}"
                    )

    async def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """
        Execute a callable (or already-created coroutine) through the circuit breaker.

        Accepts both an async callable (with optional args/kwargs) and a
        pre-created coroutine object (e.g. ``breaker.call(my_coro())``).

        Args:
            func: Async callable OR an already-started coroutine object.
            *args: Positional arguments forwarded to ``func`` when it is callable.
            **kwargs: Keyword arguments forwarded to ``func`` when it is callable.

        Returns:
            Result of the callable

        Raises:
            CircuitBreakerOpenError: If circuit is OPEN
            Exception: Any exception from the callable (after recording failure)
        """
        try:
            await self._check_state()
        except CircuitBreakerOpenError:
            # If a coroutine was already created, close it to prevent
            # "coroutine was never awaited" ResourceWarnings.
            if asyncio.iscoroutine(func):
                func.close()
            raise

        try:
            # Support both callables and pre-created coroutines
            if asyncio.iscoroutine(func):
                coro = func
            else:
                coro = func(*args, **kwargs)

            if self.timeout is not None:
                result = await asyncio.wait_for(coro, timeout=self.timeout)
            else:
                result = await coro

            await self._record_success()
            return result

        except CircuitBreakerOpenError:
            raise

        except asyncio.TimeoutError as exc:
            timeout_err = ClaudeAPIError(
                message=f"Call to '{self.name}' timed out after {self.timeout}s",
                code=ErrorCode.CLAUDE_API_TIMEOUT,
                details={"timeout_seconds": self.timeout},
            )
            await self._record_failure(exc)
            raise timeout_err from exc

        except Exception as exc:
            await self._record_failure(exc)
            raise

    async def __aenter__(self) -> "CircuitBreaker":
        """Support use as async context manager: `async with breaker:`"""
        await self._check_state()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[Exception],
        exc_tb: Any,
    ) -> bool:
        """Record success or failure based on whether an exception occurred."""
        if exc_type is None:
            await self._record_success()
        elif exc_type is not CircuitBreakerOpenError:
            await self._record_failure(exc_val)
        return False  # Don't suppress exceptions

    def reset(self) -> None:
        """
        Manually reset the circuit breaker to CLOSED state.

        Use this to recover from a known-fixed issue without waiting
        for the automatic reset timeout.
        """
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        logger.info(f"[circuit_breaker] '{self.name}' manually reset to CLOSED")


# ═══════════════════════════════════════════════════════════
# GLOBAL CIRCUIT BREAKER REGISTRY
# ═══════════════════════════════════════════════════════════


class CircuitBreakerRegistry:
    """
    Global registry for circuit breaker instances.

    Allows centralized management and status monitoring of all
    circuit breakers in the system.
    """

    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}

    def get_or_create(
        self,
        name: str,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
        success_threshold: int = 1,
        timeout: Optional[float] = None,
    ) -> CircuitBreaker:
        """
        Get an existing circuit breaker or create a new one.

        Args:
            name: Unique name for the circuit breaker
            failure_threshold: Failures before opening. Default: 5
            reset_timeout: Seconds before attempting reset. Default: 60.0
            success_threshold: Successes to close. Default: 1
            timeout: Per-call timeout. Default: None

        Returns:
            CircuitBreaker instance (existing or new)
        """
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                reset_timeout=reset_timeout,
                success_threshold=success_threshold,
                timeout=timeout,
            )
            logger.info(
                f"[circuit_breaker] Registered new circuit breaker: '{name}' "
                f"(threshold={failure_threshold}, reset={reset_timeout}s)"
            )
        return self._breakers[name]

    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get an existing circuit breaker by name."""
        return self._breakers.get(name)

    def get_all_status(self) -> dict[str, dict[str, Any]]:
        """
        Get status of all registered circuit breakers.

        Returns:
            Dictionary of name → status dict for all breakers
        """
        return {name: breaker.get_status() for name, breaker in self._breakers.items()}

    def reset_all(self) -> None:
        """Reset all circuit breakers to CLOSED state."""
        for breaker in self._breakers.values():
            breaker.reset()
        logger.info(f"[circuit_breaker] Reset all {len(self._breakers)} circuit breakers")


# Global registry instance
_registry = CircuitBreakerRegistry()


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """Get the global circuit breaker registry."""
    return _registry


def get_claude_api_breaker() -> CircuitBreaker:
    """
    Get (or create) the circuit breaker for Claude API calls.

    Configured for Claude API characteristics:
    - Opens after 5 consecutive failures
    - Waits 60 seconds before testing recovery
    - Closes after 1 successful probe

    Returns:
        CircuitBreaker instance for Claude API
    """
    return _registry.get_or_create(
        name="claude-api",
        failure_threshold=5,
        reset_timeout=60.0,
        success_threshold=1,
    )
