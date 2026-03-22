"""
Standardized Error Types and Response Models

Provides consistent error response format across all API endpoints with:
- Error codes for programmatic error handling
- Request ID tracking for debugging
- Structured error context (user_id, agent_id, etc.)
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════
# ERROR CODE ENUM
# ═══════════════════════════════════════════════════════════


class ErrorCode(str, Enum):
    """Standardized error codes for all system errors."""

    # Generic errors
    INTERNAL_ERROR = "INTERNAL_ERROR"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"

    # Database errors
    DATABASE_ERROR = "DATABASE_ERROR"
    DATABASE_CONNECTION_ERROR = "DATABASE_CONNECTION_ERROR"
    DATABASE_TIMEOUT = "DATABASE_TIMEOUT"
    DATABASE_TRANSACTION_FAILED = "DATABASE_TRANSACTION_FAILED"
    DATABASE_RETRY_EXHAUSTED = "DATABASE_RETRY_EXHAUSTED"

    # Claude API / AI errors
    CLAUDE_API_ERROR = "CLAUDE_API_ERROR"
    CLAUDE_API_TIMEOUT = "CLAUDE_API_TIMEOUT"
    CLAUDE_API_RATE_LIMITED = "CLAUDE_API_RATE_LIMITED"
    CLAUDE_API_CIRCUIT_OPEN = "CLAUDE_API_CIRCUIT_OPEN"
    CLAUDE_API_UNAVAILABLE = "CLAUDE_API_UNAVAILABLE"

    # Agent errors
    AGENT_NOT_FOUND = "AGENT_NOT_FOUND"
    AGENT_EXECUTION_FAILED = "AGENT_EXECUTION_FAILED"
    AGENT_ALREADY_RUNNING = "AGENT_ALREADY_RUNNING"
    AGENT_INTERRUPTED = "AGENT_INTERRUPTED"

    # Orchestrator errors
    ORCHESTRATOR_NOT_FOUND = "ORCHESTRATOR_NOT_FOUND"
    ORCHESTRATOR_EXECUTION_FAILED = "ORCHESTRATOR_EXECUTION_FAILED"
    ORCHESTRATOR_BUSY = "ORCHESTRATOR_BUSY"

    # WebSocket errors
    WEBSOCKET_ERROR = "WEBSOCKET_ERROR"
    WEBSOCKET_SEND_FAILED = "WEBSOCKET_SEND_FAILED"

    # Project / workspace errors
    WORKSPACE_NOT_FOUND = "WORKSPACE_NOT_FOUND"
    PROJECT_NOT_FOUND = "PROJECT_NOT_FOUND"
    PHASE_TRANSITION_FAILED = "PHASE_TRANSITION_FAILED"

    # Plugin errors
    PLUGIN_NOT_FOUND = "PLUGIN_NOT_FOUND"
    PLUGIN_LOAD_FAILED = "PLUGIN_LOAD_FAILED"


# ═══════════════════════════════════════════════════════════
# ERROR RESPONSE MODELS
# ═══════════════════════════════════════════════════════════


class ErrorDetail(BaseModel):
    """Detailed error information with optional context."""

    code: ErrorCode
    message: str
    details: Optional[dict[str, Any]] = None

    # Debugging context
    request_id: Optional[str] = None
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    orchestrator_id: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standardized error response format for all API endpoints."""

    status: str = "error"
    error: ErrorDetail
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    @classmethod
    def create(
        cls,
        code: ErrorCode,
        message: str,
        request_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        orchestrator_id: Optional[str] = None,
    ) -> "ErrorResponse":
        """
        Factory method for creating standardized error responses.

        Args:
            code: Error code for programmatic handling
            message: Human-readable error message
            request_id: Optional request ID for tracing (auto-generated if not provided)
            details: Optional additional error details
            user_id: Optional user context for debugging
            agent_id: Optional agent context for debugging
            orchestrator_id: Optional orchestrator context for debugging

        Returns:
            ErrorResponse with consistent format
        """
        rid = request_id or str(uuid.uuid4())
        return cls(
            status="error",
            error=ErrorDetail(
                code=code,
                message=message,
                details=details,
                request_id=rid,
                user_id=user_id,
                agent_id=agent_id,
                orchestrator_id=orchestrator_id,
            ),
            request_id=rid,
        )


# ═══════════════════════════════════════════════════════════
# CUSTOM EXCEPTION CLASSES
# ═══════════════════════════════════════════════════════════


class OrchestratorError(Exception):
    """Base exception for all orchestrator errors."""

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        details: Optional[dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}
        self.request_id = request_id or str(uuid.uuid4())

    def to_response(
        self,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        orchestrator_id: Optional[str] = None,
    ) -> ErrorResponse:
        """Convert exception to ErrorResponse."""
        return ErrorResponse.create(
            code=self.code,
            message=self.message,
            request_id=self.request_id,
            details=self.details,
            user_id=user_id,
            agent_id=agent_id,
            orchestrator_id=orchestrator_id,
        )


class DatabaseError(OrchestratorError):
    """Database operation errors."""

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.DATABASE_ERROR,
        details: Optional[dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ):
        super().__init__(message, code, details, request_id)


class RetryExhaustedError(DatabaseError):
    """Raised when all retry attempts for a database operation are exhausted."""

    def __init__(
        self,
        operation: str,
        attempts: int,
        last_error: Exception,
        request_id: Optional[str] = None,
    ):
        super().__init__(
            message=f"Database operation '{operation}' failed after {attempts} attempts: {last_error}",
            code=ErrorCode.DATABASE_RETRY_EXHAUSTED,
            details={
                "operation": operation,
                "attempts": attempts,
                "last_error": str(last_error),
                "last_error_type": type(last_error).__name__,
            },
            request_id=request_id,
        )
        self.operation = operation
        self.attempts = attempts
        self.last_error = last_error


class CircuitBreakerOpenError(OrchestratorError):
    """Raised when the circuit breaker is open and rejecting requests."""

    def __init__(
        self,
        service: str,
        failure_count: int,
        reset_timeout: float,
        request_id: Optional[str] = None,
    ):
        super().__init__(
            message=f"Circuit breaker open for service '{service}' after {failure_count} failures. "
                    f"Will attempt reset in {reset_timeout:.0f}s.",
            code=ErrorCode.CLAUDE_API_CIRCUIT_OPEN,
            details={
                "service": service,
                "failure_count": failure_count,
                "reset_timeout_seconds": reset_timeout,
            },
            request_id=request_id,
        )
        self.service = service
        self.failure_count = failure_count
        self.reset_timeout = reset_timeout


class ClaudeAPIError(OrchestratorError):
    """Claude API call failures."""

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.CLAUDE_API_ERROR,
        details: Optional[dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ):
        super().__init__(message, code, details, request_id)


class AgentError(OrchestratorError):
    """Agent lifecycle and execution errors."""

    def __init__(
        self,
        message: str,
        agent_id: Optional[str] = None,
        code: ErrorCode = ErrorCode.AGENT_EXECUTION_FAILED,
        details: Optional[dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ):
        super().__init__(message, code, details, request_id)
        self._agent_id = agent_id
