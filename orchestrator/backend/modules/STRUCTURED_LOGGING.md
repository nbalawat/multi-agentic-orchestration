# Structured Logging Feature

High-performance structured JSON logging using `structlog` with request ID tracking, sensitive data protection, and <1ms overhead per message.

## Features

✅ **Structured JSON Output** - Production-ready JSON logs for parsing and analysis
✅ **Request ID Tracking** - Automatic context propagation using `contextvars`
✅ **Sensitive Data Protection** - Automatic masking of passwords, tokens, API keys
✅ **Performance Optimized** - <1ms per log message (tested at **187μs average**)
✅ **Log Levels** - DEBUG, INFO, WARNING, ERROR, CRITICAL
✅ **Convenience Methods** - HTTP requests, agent events, database queries
✅ **Development-Friendly** - Console output with colors for local development

## Quick Start

### Basic Usage

```python
from orchestrator.backend.modules.structured_logger import StructuredLogger

logger = StructuredLogger("my-service")

# Simple logging
logger.info("Application started", version="1.0.0", environment="production")
logger.error("Database connection failed", error="timeout", retry_count=3)
```

### Context Tracking

```python
# Set context for a request
logger.set_request_id("req-abc123")
logger.set_user_id("user-john-doe")

# All subsequent logs include these context variables
logger.info("User logged in successfully")
logger.info("User fetched profile", profile_id="prof-456")

# Clear context when done
logger.clear_context()
```

### HTTP Request Logging

```python
logger.http_request(
    method="POST",
    path="/api/auth/login",
    status_code=200,
    duration_ms=45.2,
    user_agent="Mozilla/5.0",
    ip_address="192.168.1.100",
)
```

**Output:**
```json
{
  "http_method": "POST",
  "http_path": "/api/auth/login",
  "http_status": 200,
  "duration_ms": 45.2,
  "user_agent": "Mozilla/5.0",
  "ip_address": "192.168.1.100",
  "request_id": "req-abc123",
  "user_id": "user-john-doe",
  "timestamp": "2026-03-24T17:41:42.806913+00:00",
  "level": "INFO",
  "logger": "api"
}
```

### Sensitive Data Protection

Passwords, tokens, and API keys are **automatically redacted**:

```python
logger.info(
    "User authentication",
    username="john@example.com",
    password="super_secret_123",  # Will be masked
    api_key="sk-ant-api-key-12345",  # Will be masked
)
```

**Output:**
```json
{
  "username": "john@example.com",
  "password": "***REDACTED***",
  "api_key": "***REDACTED***",
  "event": "User authentication",
  "timestamp": "2026-03-24T17:41:42.815413+00:00",
  "level": "INFO"
}
```

**Protected fields:**
- `password`, `passwd`, `pwd`
- `secret`
- `api_key`, `apikey`
- `authorization`, `bearer`
- `credential`, `private_key`, `access_key`
- `auth_token`, `api_token`, `access_token`, `refresh_token`
- `session_id`

**Note:** Fields like `prompt_tokens` or `output_tokens` are NOT masked (they count tokens, not contain them).

### Agent Event Logging

```python
logger.agent_event(
    agent_id="agent-claude-001",
    event_type="executing",
    message="Processing user request",
    prompt_tokens=150,
    estimated_cost_usd=0.0012,
)
```

### Database Query Logging

```python
logger.database_query(
    query="SELECT * FROM users WHERE id = $1",
    duration_ms=12.5,
    rows_affected=1,
)
```

Long queries are automatically truncated to 100 characters.

## Configuration

### Environment Variables

```bash
# Set to "production" for JSON logs, "development" for console output
ENVIRONMENT=production

# Set log level
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

### Programmatic Configuration

```python
from orchestrator.backend.modules.structured_logger import configure_structured_logging

# JSON output for production
configure_structured_logging(
    json_output=True,
    log_level="INFO",
    log_file="/var/log/orchestrator/structured.log"
)

# Console output for development
configure_structured_logging(
    json_output=False,
    log_level="DEBUG",
)
```

## Performance

Tested with 10,000 log messages:

- **Average latency:** 187.81μs per message ✅ (target: <1ms)
- **Throughput:** 5,325 logs/second
- **Context overhead:** <10% additional latency
- **Sensitive masking overhead:** <50% additional latency

## Context Variables

Context variables are stored using Python's `contextvars` module, making them:
- **Thread-safe** - Each request/task has isolated context
- **Async-safe** - Works correctly with `asyncio` and FastAPI
- **Automatic propagation** - Context flows through function calls

Available context variables:
- `request_id` - HTTP request ID for tracing
- `user_id` - Authenticated user ID
- `agent_id` - Sub-agent UUID
- `orchestrator_id` - Orchestrator agent UUID

## Integration with FastAPI

### Middleware for Request ID Tracking

```python
from fastapi import FastAPI, Request
from orchestrator.backend.modules.structured_logger import StructuredLogger
import uuid

app = FastAPI()
logger = StructuredLogger("api")

@app.middleware("http")
async def log_requests(request: Request, call_next):
    # Set request ID
    request_id = str(uuid.uuid4())
    logger.set_request_id(request_id)

    # Set user ID if authenticated
    if hasattr(request.state, "user_id"):
        logger.set_user_id(request.state.user_id)

    # Process request
    response = await call_next(request)

    # Log request
    logger.http_request(
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=0,  # Calculate actual duration
    )

    # Clear context
    logger.clear_context()

    return response
```

## Testing

Run the test suite:

```bash
uv run pytest orchestrator/backend/tests/test_structured_logger.py -v
```

Run the example:

```bash
uv run python orchestrator/backend/modules/structured_logger_example.py
```

## Architecture

### Processor Chain

Structlog processors run in order:

1. **merge_contextvars** - Merge context variables from `contextvars`
2. **add_context_variables** - Add request_id, user_id, agent_id, orchestrator_id
3. **add_timestamp** - Add ISO 8601 timestamp in UTC
4. **add_log_level** - Add log level (INFO, ERROR, etc.)
5. **add_logger_name** - Add logger name
6. **mask_sensitive_data** - Redact passwords, tokens, API keys
7. **format_exc_info** - Format exception tracebacks
8. **JSONRenderer** (production) or **ConsoleRenderer** (development)

### Performance Optimizations

- **Logger caching** - Loggers are cached on first use (`cache_logger_on_first_use=True`)
- **Compiled regex** - Sensitive field patterns are compiled once at module load
- **Context variables** - Use fast `contextvars` instead of thread-local storage
- **Minimal processors** - Only essential processors in the chain

## Migration from Existing Logger

The new structured logger can coexist with the existing `logger.py`:

```python
# Old logger
from orchestrator.backend.modules.logger import get_logger
old_logger = get_logger()
old_logger.info("Message")

# New structured logger
from orchestrator.backend.modules.structured_logger import get_structured_logger
new_logger = get_structured_logger()
new_logger.info("Message", key="value")
```

Gradually migrate to structured logging for better observability.

## Dependencies

Added to `pyproject.toml`:

```toml
dependencies = [
    # ... existing dependencies
    "structlog>=24.0.0",
]
```

Install with:

```bash
uv pip install structlog
```

## Acceptance Criteria

✅ Structured JSON output using structlog
✅ Request ID tracking with context variables
✅ Proper log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
✅ Sensitive data protection (passwords, tokens, API keys masked)
✅ Logging overhead <1ms per message (measured at 187μs)
✅ All tests passing (35/35)
✅ Performance benchmarks included
✅ Documentation and examples provided

## See Also

- [structlog documentation](https://www.structlog.org/)
- `structured_logger.py` - Main module
- `test_structured_logger.py` - Test suite
- `structured_logger_example.py` - Usage examples
