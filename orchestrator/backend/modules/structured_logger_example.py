#!/usr/bin/env python3
"""
Example usage of the structured logging module

Run this file to see structured logging in action:
    uv run python orchestrator/backend/modules/structured_logger_example.py
"""

from structured_logger import StructuredLogger, configure_structured_logging
import time


def example_basic_logging():
    """Basic logging example"""
    print("\n=== Basic Logging ===")
    logger = StructuredLogger("example")

    logger.debug("Debug message", component="startup", details="Loading configuration")
    logger.info("Application started", version="1.0.0", environment="production")
    logger.warning("High memory usage", memory_mb=512, threshold_mb=400)
    logger.error("Database connection failed", error="Connection timeout", retry_count=3)
    logger.critical("System failure", reason="Out of disk space", available_mb=0)


def example_context_tracking():
    """Context tracking example"""
    print("\n=== Context Tracking ===")
    logger = StructuredLogger("example")

    # Set context for a request
    logger.set_request_id("req-abc123")
    logger.set_user_id("user-john-doe")

    # All subsequent logs will include these context variables
    logger.info("User logged in successfully")
    logger.info("User fetched profile data", profile_id="prof-456")
    logger.info("User updated settings", settings_changed=["theme", "notifications"])

    # Clear context when done
    logger.clear_context()
    logger.info("Request completed")


def example_http_logging():
    """HTTP request logging example"""
    print("\n=== HTTP Request Logging ===")
    logger = StructuredLogger("api")

    logger.set_request_id("req-xyz789")
    logger.set_user_id("user-alice")

    # Log HTTP request with all details
    logger.http_request(
        method="POST",
        path="/api/auth/login",
        status_code=200,
        duration_ms=45.2,
        user_agent="Mozilla/5.0",
        ip_address="192.168.1.100",
    )

    logger.clear_context()


def example_agent_logging():
    """Agent event logging example"""
    print("\n=== Agent Event Logging ===")
    logger = StructuredLogger("agent")

    logger.set_agent_id("agent-claude-001")
    logger.set_orchestrator_id("orch-main")

    logger.agent_event(
        agent_id="agent-claude-001",
        event_type="created",
        message="Agent initialized successfully",
        model="claude-3-5-sonnet-20241022",
    )

    logger.agent_event(
        agent_id="agent-claude-001",
        event_type="executing",
        message="Processing user request",
        prompt_tokens=150,
        estimated_cost_usd=0.0012,
    )

    logger.clear_context()


def example_sensitive_data_protection():
    """Sensitive data protection example"""
    print("\n=== Sensitive Data Protection ===")
    logger = StructuredLogger("security")

    # Passwords and API keys are automatically redacted
    logger.info(
        "User authentication",
        username="john@example.com",
        password="super_secret_123",  # Will be masked
        success=True,
    )

    logger.info(
        "API call made",
        endpoint="/api/claude",
        api_key="sk-ant-api-key-12345",  # Will be masked
        model="claude-3-5-sonnet-20241022",
        tokens=1500,
    )

    # Nested sensitive data is also protected
    logger.info(
        "User data",
        user={
            "id": "user-123",
            "email": "alice@example.com",
            "auth_token": "token-abc-xyz-789",  # Will be masked
            "preferences": {
                "theme": "dark",
                "secret": "my-secret-value",  # Will be masked
            },
        },
    )


def example_database_logging():
    """Database query logging example"""
    print("\n=== Database Query Logging ===")
    logger = StructuredLogger("database")

    logger.database_query(
        query="SELECT * FROM users WHERE id = $1",
        duration_ms=12.5,
        rows_affected=1,
    )

    # Long queries are automatically truncated
    long_query = "SELECT * FROM users WHERE " + " AND ".join(
        [f"field{i} = $1" for i in range(50)]
    )
    logger.database_query(query=long_query, duration_ms=250.0, rows_affected=0)


def example_performance_benchmark():
    """Performance benchmark"""
    print("\n=== Performance Benchmark ===")
    logger = StructuredLogger("benchmark")

    # Benchmark single log message
    iterations = 10000
    start = time.perf_counter()
    for i in range(iterations):
        logger.info("Performance test", iteration=i, data="sample")
    duration_ms = (time.perf_counter() - start) * 1000
    avg_duration_us = (duration_ms / iterations) * 1000

    print(f"Total time for {iterations} log messages: {duration_ms:.2f}ms")
    print(f"Average time per log message: {avg_duration_us:.2f}μs")
    print(f"Throughput: {iterations / (duration_ms / 1000):.0f} logs/second")

    # Verify <1ms requirement
    assert avg_duration_us < 1000, f"Performance requirement not met: {avg_duration_us:.2f}μs per log"
    print("✅ Performance requirement met: <1ms per log message")


def example_json_vs_console():
    """Demonstrate JSON vs console output"""
    print("\n=== JSON Output (Production) ===")

    # Configure for JSON output
    configure_structured_logging(json_output=True, log_level="INFO")
    logger = StructuredLogger("json-example")
    logger.info("This is JSON output", key="value", count=42)

    print("\n=== Console Output (Development) ===")

    # Configure for console output
    configure_structured_logging(json_output=False, log_level="INFO")
    logger2 = StructuredLogger("console-example")
    logger2.info("This is console output", key="value", count=42)


if __name__ == "__main__":
    print("=" * 80)
    print("Structured Logging Examples")
    print("=" * 80)

    # Configure for JSON output (production mode)
    configure_structured_logging(json_output=True, log_level="DEBUG")

    example_basic_logging()
    example_context_tracking()
    example_http_logging()
    example_agent_logging()
    example_sensitive_data_protection()
    example_database_logging()
    example_performance_benchmark()

    print("\n" + "=" * 80)
    print("All examples completed!")
    print("=" * 80)
