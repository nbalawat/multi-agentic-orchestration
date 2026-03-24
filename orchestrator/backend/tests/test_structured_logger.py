#!/usr/bin/env python3
"""
Tests for structured logging module

Covers:
- Basic logging functionality (all levels)
- Request ID tracking with context variables
- Sensitive data protection
- Performance (<1ms per message)
- JSON output format
- Context management
"""

import json
import logging
import time
from io import StringIO
from pathlib import Path
from typing import Dict, List
import pytest

from orchestrator.backend.modules.structured_logger import (
    StructuredLogger,
    configure_structured_logging,
    add_context_variables,
    mask_sensitive_data,
    add_timestamp,
    add_log_level,
    request_id_ctx,
    user_id_ctx,
    agent_id_ctx,
    orchestrator_id_ctx,
)


@pytest.fixture
def logger():
    """Create a structured logger for testing"""
    # Reset logging configuration
    logging.root.handlers.clear()

    # Configure for testing (console output, DEBUG level)
    configure_structured_logging(
        json_output=True,
        log_level="DEBUG",
        log_file=None,
    )

    logger = StructuredLogger("test")

    # Clear context before each test
    logger.clear_context()

    yield logger

    # Clean up after test
    logger.clear_context()


@pytest.fixture
def capture_logs():
    """Capture log output for assertion"""
    log_capture = StringIO()
    handler = logging.StreamHandler(log_capture)
    handler.setLevel(logging.DEBUG)
    logging.root.addHandler(handler)

    yield log_capture

    logging.root.removeHandler(handler)


class TestBasicLogging:
    """Test basic logging functionality"""

    def test_debug_level(self, logger, capture_logs):
        """Test DEBUG level logging"""
        logger.debug("debug message", key="value")

        output = capture_logs.getvalue()
        assert "debug message" in output
        log_entry = json.loads(output.strip())
        assert log_entry["event"] == "debug message"
        assert log_entry["key"] == "value"
        assert log_entry["level"] == "DEBUG"

    def test_info_level(self, logger, capture_logs):
        """Test INFO level logging"""
        logger.info("info message", status="ok")

        output = capture_logs.getvalue()
        log_entry = json.loads(output.strip())
        assert log_entry["event"] == "info message"
        assert log_entry["status"] == "ok"
        assert log_entry["level"] == "INFO"

    def test_warning_level(self, logger, capture_logs):
        """Test WARNING level logging"""
        logger.warning("warning message", issue="minor")

        output = capture_logs.getvalue()
        log_entry = json.loads(output.strip())
        assert log_entry["event"] == "warning message"
        assert log_entry["issue"] == "minor"
        assert log_entry["level"] == "WARNING"

    def test_error_level(self, logger, capture_logs):
        """Test ERROR level logging"""
        logger.error("error message", error_code=500)

        output = capture_logs.getvalue()
        log_entry = json.loads(output.strip())
        assert log_entry["event"] == "error message"
        assert log_entry["error_code"] == 500
        assert log_entry["level"] == "ERROR"

    def test_critical_level(self, logger, capture_logs):
        """Test CRITICAL level logging"""
        logger.critical("critical message", severity="high")

        output = capture_logs.getvalue()
        log_entry = json.loads(output.strip())
        assert log_entry["event"] == "critical message"
        assert log_entry["severity"] == "high"
        assert log_entry["level"] == "CRITICAL"


class TestContextTracking:
    """Test request ID and context tracking"""

    def test_request_id_tracking(self, logger, capture_logs):
        """Test request ID is added to logs"""
        logger.set_request_id("req-12345")
        logger.info("test event")

        output = capture_logs.getvalue()
        log_entry = json.loads(output.strip())
        assert log_entry["request_id"] == "req-12345"

    def test_user_id_tracking(self, logger, capture_logs):
        """Test user ID is added to logs"""
        logger.set_user_id("user-67890")
        logger.info("user action")

        output = capture_logs.getvalue()
        log_entry = json.loads(output.strip())
        assert log_entry["user_id"] == "user-67890"

    def test_agent_id_tracking(self, logger, capture_logs):
        """Test agent ID is added to logs"""
        logger.set_agent_id("agent-abc123")
        logger.info("agent event")

        output = capture_logs.getvalue()
        log_entry = json.loads(output.strip())
        assert log_entry["agent_id"] == "agent-abc123"

    def test_orchestrator_id_tracking(self, logger, capture_logs):
        """Test orchestrator ID is added to logs"""
        logger.set_orchestrator_id("orch-xyz789")
        logger.info("orchestrator event")

        output = capture_logs.getvalue()
        log_entry = json.loads(output.strip())
        assert log_entry["orchestrator_id"] == "orch-xyz789"

    def test_multiple_context_variables(self, logger, capture_logs):
        """Test multiple context variables simultaneously"""
        logger.set_request_id("req-001")
        logger.set_user_id("user-002")
        logger.set_agent_id("agent-003")
        logger.set_orchestrator_id("orch-004")

        logger.info("complex event")

        output = capture_logs.getvalue()
        log_entry = json.loads(output.strip())
        assert log_entry["request_id"] == "req-001"
        assert log_entry["user_id"] == "user-002"
        assert log_entry["agent_id"] == "agent-003"
        assert log_entry["orchestrator_id"] == "orch-004"

    def test_clear_context(self, logger, capture_logs):
        """Test clearing context variables"""
        logger.set_request_id("req-12345")
        logger.set_user_id("user-67890")

        logger.clear_context()
        logger.info("event after clear")

        output = capture_logs.getvalue()
        log_entry = json.loads(output.strip())
        assert "request_id" not in log_entry
        assert "user_id" not in log_entry


class TestSensitiveDataProtection:
    """Test sensitive data masking"""

    def test_password_masking(self, logger, capture_logs):
        """Test password fields are masked"""
        logger.info("user login", password="secret123", username="john")

        output = capture_logs.getvalue()
        log_entry = json.loads(output.strip())
        assert log_entry["password"] == "***REDACTED***"
        assert log_entry["username"] == "john"

    def test_token_masking(self, logger, capture_logs):
        """Test token fields are masked"""
        logger.info("api call", api_token="abc123xyz", endpoint="/api/users")

        output = capture_logs.getvalue()
        log_entry = json.loads(output.strip())
        assert log_entry["api_token"] == "***REDACTED***"
        assert log_entry["endpoint"] == "/api/users"

    def test_api_key_masking(self, logger, capture_logs):
        """Test API key fields are masked"""
        logger.info("config", api_key="sk-1234567890", service="claude")

        output = capture_logs.getvalue()
        log_entry = json.loads(output.strip())
        assert log_entry["api_key"] == "***REDACTED***"
        assert log_entry["service"] == "claude"

    def test_authorization_header_masking(self, logger, capture_logs):
        """Test authorization headers are masked"""
        logger.info("http request", authorization="Bearer token123", method="GET")

        output = capture_logs.getvalue()
        log_entry = json.loads(output.strip())
        assert log_entry["authorization"] == "***REDACTED***"
        assert log_entry["method"] == "GET"

    def test_nested_sensitive_data_masking(self, logger, capture_logs):
        """Test nested sensitive data is masked"""
        logger.info(
            "complex object",
            user={
                "username": "john",
                "password": "secret123",
                "settings": {
                    "api_key": "key123",
                    "theme": "dark"
                }
            }
        )

        output = capture_logs.getvalue()
        log_entry = json.loads(output.strip())
        assert log_entry["user"]["username"] == "john"
        assert log_entry["user"]["password"] == "***REDACTED***"
        assert log_entry["user"]["settings"]["api_key"] == "***REDACTED***"
        assert log_entry["user"]["settings"]["theme"] == "dark"

    def test_list_with_sensitive_data_masking(self, logger, capture_logs):
        """Test sensitive data in lists is masked"""
        logger.info(
            "user list",
            users=[
                {"username": "alice", "password": "pass1"},
                {"username": "bob", "auth_token": "token2"},
            ]
        )

        output = capture_logs.getvalue()
        log_entry = json.loads(output.strip())
        assert log_entry["users"][0]["username"] == "alice"
        assert log_entry["users"][0]["password"] == "***REDACTED***"
        assert log_entry["users"][1]["username"] == "bob"
        assert log_entry["users"][1]["auth_token"] == "***REDACTED***"

    def test_case_insensitive_masking(self, logger, capture_logs):
        """Test sensitive field matching is case-insensitive"""
        logger.info(
            "mixed case",
            PASSWORD="pass1",
            ApiKey="key1",
            bearer_token="token1"
        )

        output = capture_logs.getvalue()
        log_entry = json.loads(output.strip())
        assert log_entry["PASSWORD"] == "***REDACTED***"
        assert log_entry["ApiKey"] == "***REDACTED***"
        assert log_entry["bearer_token"] == "***REDACTED***"


class TestJSONOutput:
    """Test JSON output format"""

    def test_json_structure(self, logger, capture_logs):
        """Test log output is valid JSON"""
        logger.info("test event", key="value")

        output = capture_logs.getvalue().strip()
        log_entry = json.loads(output)

        assert isinstance(log_entry, dict)
        assert "event" in log_entry
        assert "timestamp" in log_entry
        assert "level" in log_entry
        assert "logger" in log_entry

    def test_timestamp_format(self, logger, capture_logs):
        """Test timestamp is ISO 8601 format"""
        logger.info("test event")

        output = capture_logs.getvalue().strip()
        log_entry = json.loads(output)

        # Verify timestamp is ISO 8601
        timestamp = log_entry["timestamp"]
        assert "T" in timestamp
        assert timestamp.endswith("Z") or "+" in timestamp or "-" in timestamp[-6:]

    def test_structured_fields(self, logger, capture_logs):
        """Test structured fields are preserved"""
        logger.info(
            "complex event",
            count=42,
            items=["a", "b", "c"],
            metadata={"key": "value", "number": 123}
        )

        output = capture_logs.getvalue().strip()
        log_entry = json.loads(output)

        assert log_entry["count"] == 42
        assert log_entry["items"] == ["a", "b", "c"]
        assert log_entry["metadata"]["key"] == "value"
        assert log_entry["metadata"]["number"] == 123


class TestConvenienceMethods:
    """Test convenience methods for common log types"""

    def test_http_request_logging(self, logger, capture_logs):
        """Test HTTP request logging"""
        logger.http_request(
            method="GET",
            path="/api/users",
            status_code=200,
            duration_ms=45.2
        )

        output = capture_logs.getvalue().strip()
        log_entry = json.loads(output)

        assert log_entry["event"] == "http_request"
        assert log_entry["http_method"] == "GET"
        assert log_entry["http_path"] == "/api/users"
        assert log_entry["http_status"] == 200
        assert log_entry["duration_ms"] == 45.2

    def test_agent_event_logging(self, logger, capture_logs):
        """Test agent event logging"""
        logger.agent_event(
            agent_id="agent-123",
            event_type="created",
            message="Agent created successfully"
        )

        output = capture_logs.getvalue().strip()
        log_entry = json.loads(output)

        assert log_entry["event"] == "agent_event"
        assert log_entry["agent_id"] == "agent-123"
        assert log_entry["event_type"] == "created"
        assert log_entry["message"] == "Agent created successfully"

    def test_database_query_logging(self, logger, capture_logs):
        """Test database query logging"""
        logger.database_query(
            query="SELECT * FROM users WHERE id = $1",
            duration_ms=12.5,
            rows_affected=1
        )

        output = capture_logs.getvalue().strip()
        log_entry = json.loads(output)

        assert log_entry["event"] == "database_query"
        assert "SELECT * FROM users" in log_entry["query"]
        assert log_entry["duration_ms"] == 12.5
        assert log_entry["rows_affected"] == 1

    def test_database_query_truncation(self, logger, capture_logs):
        """Test long database queries are truncated"""
        long_query = "SELECT * FROM users WHERE " + " AND ".join([f"field{i} = $1" for i in range(50)])

        logger.database_query(
            query=long_query,
            duration_ms=100.0,
            rows_affected=5
        )

        output = capture_logs.getvalue().strip()
        log_entry = json.loads(output)

        # Query should be truncated to 100 chars + "..."
        assert len(log_entry["query"]) <= 103
        assert log_entry["query"].endswith("...")


class TestPerformance:
    """Test logging performance"""

    def test_single_log_performance(self, logger):
        """Test single log message is <1ms"""
        start = time.perf_counter()
        logger.info("performance test", iteration=1)
        duration_ms = (time.perf_counter() - start) * 1000

        assert duration_ms < 1.0, f"Log message took {duration_ms:.3f}ms, expected <1ms"

    def test_batch_logging_performance(self, logger):
        """Test 1000 log messages average <1ms each"""
        iterations = 1000

        start = time.perf_counter()
        for i in range(iterations):
            logger.info("batch test", iteration=i, data={"key": "value"})
        duration_ms = (time.perf_counter() - start) * 1000

        avg_duration = duration_ms / iterations
        assert avg_duration < 1.0, f"Average log time {avg_duration:.3f}ms, expected <1ms"

    def test_context_overhead(self, logger):
        """Test context variables don't add significant overhead"""
        # Baseline: log without context (warm up first)
        for i in range(10):
            logger.info("warmup")

        start = time.perf_counter()
        for i in range(100):
            logger.info("no context")
        baseline_duration = (time.perf_counter() - start) * 1000

        # With context
        logger.set_request_id("req-123")
        logger.set_user_id("user-456")
        logger.set_agent_id("agent-789")

        start = time.perf_counter()
        for i in range(100):
            logger.info("with context")
        context_duration = (time.perf_counter() - start) * 1000

        # Context overhead should be reasonable (<50% increase)
        # Allow for some overhead since context adds value
        overhead_ratio = context_duration / baseline_duration
        assert overhead_ratio < 1.5, f"Context overhead {overhead_ratio:.2f}x, expected <1.5x"

    def test_sensitive_masking_overhead(self, logger):
        """Test sensitive data masking doesn't add significant overhead"""
        # Baseline: log without sensitive data
        start = time.perf_counter()
        for i in range(100):
            logger.info("no sensitive data", username="john", email="john@example.com")
        baseline_duration = (time.perf_counter() - start) * 1000

        # With sensitive data
        start = time.perf_counter()
        for i in range(100):
            logger.info(
                "with sensitive data",
                username="john",
                password="secret",
                api_key="key123",
                auth_token="token456"
            )
        sensitive_duration = (time.perf_counter() - start) * 1000

        # Masking overhead should be reasonable (<50% increase)
        # Some overhead is expected for security features
        overhead_ratio = sensitive_duration / baseline_duration
        assert overhead_ratio < 1.5, f"Masking overhead {overhead_ratio:.2f}x, expected <1.5x"


class TestProcessors:
    """Test individual processor functions"""

    def test_add_context_variables_processor(self):
        """Test context variables processor"""
        # Set context
        request_id_ctx.set("req-123")
        user_id_ctx.set("user-456")

        event_dict = {"event": "test"}
        result = add_context_variables(None, None, event_dict)

        assert result["request_id"] == "req-123"
        assert result["user_id"] == "user-456"

        # Clean up
        request_id_ctx.set(None)
        user_id_ctx.set(None)

    def test_mask_sensitive_data_processor(self):
        """Test sensitive data masking processor"""
        event_dict = {
            "event": "test",
            "password": "secret",
            "username": "john"
        }

        result = mask_sensitive_data(None, None, event_dict)

        assert result["password"] == "***REDACTED***"
        assert result["username"] == "john"

    def test_add_timestamp_processor(self):
        """Test timestamp processor"""
        event_dict = {"event": "test"}
        result = add_timestamp(None, None, event_dict)

        assert "timestamp" in result
        assert "T" in result["timestamp"]

    def test_add_log_level_processor(self):
        """Test log level processor"""
        event_dict = {"event": "test", "level": "info"}
        result = add_log_level(None, None, event_dict)

        assert result["level"] == "INFO"


class TestIntegration:
    """Integration tests with realistic scenarios"""

    def test_full_http_request_lifecycle(self, logger, capture_logs):
        """Test complete HTTP request logging with all features"""
        # Simulate incoming request
        logger.set_request_id("req-abc123")
        logger.set_user_id("user-john-doe")

        # Log request
        logger.http_request(
            method="POST",
            path="/api/auth/login",
            status_code=200,
            duration_ms=45.2,
            user_agent="Mozilla/5.0",
            ip_address="192.168.1.100"
        )

        output = capture_logs.getvalue().strip()
        log_entry = json.loads(output)

        # Verify all fields
        assert log_entry["event"] == "http_request"
        assert log_entry["http_method"] == "POST"
        assert log_entry["http_path"] == "/api/auth/login"
        assert log_entry["http_status"] == 200
        assert log_entry["duration_ms"] == 45.2
        assert log_entry["request_id"] == "req-abc123"
        assert log_entry["user_id"] == "user-john-doe"
        assert log_entry["user_agent"] == "Mozilla/5.0"
        assert log_entry["ip_address"] == "192.168.1.100"

    def test_agent_execution_with_sensitive_data(self, logger, capture_logs):
        """Test agent execution logging with API key protection"""
        logger.set_agent_id("agent-xyz789")
        logger.set_orchestrator_id("orch-main")

        logger.agent_event(
            agent_id="agent-xyz789",
            event_type="api_call",
            message="Calling Claude API",
            api_key="sk-ant-api-key-12345",  # Should be masked
            model="claude-3-5-sonnet-20241022",
            prompt_tokens=150
        )

        output = capture_logs.getvalue().strip()
        log_entry = json.loads(output)

        assert log_entry["agent_id"] == "agent-xyz789"
        assert log_entry["orchestrator_id"] == "orch-main"
        assert log_entry["api_key"] == "***REDACTED***"
        assert log_entry["model"] == "claude-3-5-sonnet-20241022"
        assert log_entry["prompt_tokens"] == 150
