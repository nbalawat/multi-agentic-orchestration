# Integration Test Suite

Comprehensive end-to-end integration tests using **real PostgreSQL and Redis** via Docker testcontainers.

## Overview

This test suite provides:

- ✅ **Real Database Tests** - PostgreSQL via testcontainers (NO mocking)
- ✅ **Real Redis Tests** - Redis via testcontainers
- ✅ **Ephemeral Tests** - Automatic setup/teardown with transaction rollback
- ✅ **Multi-Tenant Isolation** - Verify workspace isolation
- ✅ **Full RAPIDS Workflows** - Test complete lifecycle from research to deploy
- ✅ **Concurrent Operations** - Test parallel agent execution
- ✅ **Proper Cleanup** - All test data automatically cleaned up

## Architecture

### Test Containers

The suite uses [testcontainers-python](https://testcontainers-python.readthedocs.io/) to spin up real Docker containers:

- **PostgreSQL 16** - Full database with migrations applied
- **Redis 7** - For caching, sessions, and rate limiting

Containers are started once per test session and reused across tests for performance.

### Test Fixtures (conftest.py)

```python
db_conn        # Database connection with automatic rollback
db_pool        # Connection pool for each test
redis_client   # Redis client with automatic cleanup
test_factory   # Factory for creating test data
cleanup_tracker     # Verify resources are cleaned up
isolation_verifier  # Verify multi-tenant isolation
```

### Test Data Factories

The `TestDataFactory` class provides helpers to create realistic test data:

```python
async def test_example(db_conn, test_factory):
    workspace = await test_factory.create_workspace(name="Test Co")
    project = await test_factory.create_project(workspace_id=workspace['id'])
    feature = await test_factory.create_feature(project_id=project['id'])
```

## Running Tests

### Prerequisites

1. **Docker must be running** (testcontainers will start containers)
2. Install dependencies:
   ```bash
   uv sync --dev
   ```

### Run All Integration Tests

```bash
# Run all integration tests
uv run pytest orchestrator/backend/tests/test_integration_suite.py -v

# Run with parallel execution (faster)
uv run pytest orchestrator/backend/tests/test_integration_suite.py -v -n auto

# Run specific test
uv run pytest orchestrator/backend/tests/test_integration_suite.py::test_multi_tenant_workspace_isolation -v

# Run with coverage
uv run pytest orchestrator/backend/tests/test_integration_suite.py -v --cov=orchestrator
```

### Run Specific Test Categories

```bash
# Workspace isolation tests
uv run pytest orchestrator/backend/tests/test_integration_suite.py -k "isolation" -v

# RAPIDS workflow tests
uv run pytest orchestrator/backend/tests/test_integration_suite.py -k "rapids" -v

# Agent lifecycle tests
uv run pytest orchestrator/backend/tests/test_integration_suite.py -k "agent" -v

# Concurrent operation tests
uv run pytest orchestrator/backend/tests/test_integration_suite.py -k "concurrent" -v

# Redis tests
uv run pytest orchestrator/backend/tests/test_integration_suite.py -k "redis" -v
```

## Test Categories

### 1. Workspace Isolation Tests

Verify multi-tenant isolation:

- ✅ `test_multi_tenant_workspace_isolation` - Workspaces can't see each other's data
- ✅ `test_workspace_cascade_deletion` - Deleting workspace cascades to all children

### 2. RAPIDS Workflow Tests

Test full lifecycle:

- ✅ `test_full_rapids_workflow` - Complete workflow: workspace → project → phases → features
- ✅ `test_feature_dependency_graph` - Feature dependencies and execution order

### 3. Agent Lifecycle Tests

Test agent operations:

- ✅ `test_orchestrator_agent_lifecycle` - Orchestrator creation, cost tracking, status
- ✅ `test_sub_agent_creation_and_tracking` - Sub-agents linked to orchestrator
- ✅ `test_agent_log_insertion_and_retrieval` - Event logging and filtering

### 4. Concurrent Operations Tests

Test parallel execution:

- ✅ `test_concurrent_feature_execution` - Multiple features execute simultaneously
- ✅ `test_concurrent_workspace_operations` - Multiple workspaces created concurrently

### 5. Cleanup Verification Tests

Test ephemeral nature:

- ✅ `test_transaction_rollback_cleanup` - Transaction rollback cleans up data
- ✅ `test_explicit_cleanup_verification` - Explicit cleanup and verification

### 6. Redis Integration Tests

Test Redis functionality:

- ✅ `test_redis_session_storage` - Session storage with TTL
- ✅ `test_redis_rate_limiting` - Token bucket rate limiting
- ✅ `test_redis_agent_coordination` - Distributed locking

## Writing New Integration Tests

### Basic Structure

```python
@pytest.mark.asyncio
async def test_my_feature(db_conn, test_factory):
    """
    Test description explaining what this verifies.
    """
    # Setup: Create test data using factory
    workspace = await test_factory.create_workspace()

    # Execute: Perform operations
    result = await db_conn.fetchrow("SELECT * FROM workspaces WHERE id = $1", workspace['id'])

    # Verify: Assert expectations
    assert result is not None
    assert result['status'] == 'active'

    # No cleanup needed - automatic transaction rollback
```

### Using Cleanup Tracker

```python
@pytest.mark.asyncio
async def test_with_cleanup_tracking(db_conn, test_factory, cleanup_tracker):
    # Create resource and track it
    workspace = await test_factory.create_workspace()
    cleanup_tracker.add("workspace", workspace['id'])

    # Perform operations...

    # Explicitly delete
    await db_conn.execute("DELETE FROM workspaces WHERE id = $1", workspace['id'])

    # Verify deletion
    assert await cleanup_tracker.verify_deleted(db_conn, "workspace", workspace['id'])
```

### Testing Multi-Tenant Isolation

```python
@pytest.mark.asyncio
async def test_isolation(db_conn, test_factory, isolation_verifier):
    ws1 = await test_factory.create_workspace(name="Tenant A")
    ws2 = await test_factory.create_workspace(name="Tenant B")

    # Create projects in each workspace
    await test_factory.create_project(workspace_id=ws1['id'])
    await test_factory.create_project(workspace_id=ws2['id'])

    # Verify isolation
    assert await isolation_verifier(ws1['id'], ws2['id'])
```

### Testing Redis

```python
@pytest.mark.asyncio
async def test_redis_feature(redis_client):
    # Redis operations
    await redis_client.set("key", "value")
    value = await redis_client.get("key")
    assert value == "value"

    # Cleanup automatic via fixture
```

## Best Practices

### 1. Use Real Data, No Mocks

```python
# ✅ GOOD: Use real database
async def test_real(db_conn):
    result = await db_conn.fetchrow("SELECT * FROM workspaces")

# ❌ BAD: Mock database
async def test_mocked(mocker):
    mock_db = mocker.patch("database.fetchrow")
```

### 2. Ephemeral Tests

```python
# ✅ GOOD: Let transaction rollback clean up
async def test_ephemeral(db_conn, test_factory):
    workspace = await test_factory.create_workspace()
    # Test code...
    # No cleanup needed - automatic rollback

# ❌ BAD: Manual cleanup (unnecessary with db_conn fixture)
async def test_manual_cleanup(db_conn, test_factory):
    workspace = await test_factory.create_workspace()
    # Test code...
    await db_conn.execute("DELETE FROM workspaces WHERE id = $1", workspace['id'])
```

### 3. Use Test Factories

```python
# ✅ GOOD: Use factory
async def test_with_factory(test_factory):
    workspace = await test_factory.create_workspace(name="Test")
    project = await test_factory.create_project(workspace_id=workspace['id'])

# ❌ BAD: Manual SQL (error-prone, verbose)
async def test_manual_sql(db_conn):
    workspace_id = uuid.uuid4()
    await db_conn.execute(
        "INSERT INTO workspaces (id, name, root_path, status, metadata, created_at, updated_at) ..."
    )
```

### 4. Clear Test Documentation

```python
# ✅ GOOD: Clear docstring explaining what's tested
async def test_workspace_isolation(db_conn, test_factory):
    """
    Test that workspaces are properly isolated.

    Verifies:
    - Each workspace only sees its own projects
    - No cross-workspace data leakage
    """

# ❌ BAD: No documentation
async def test_workspaces(db_conn):
    # What does this test?
```

## Troubleshooting

### Docker Not Running

```
Error: Cannot connect to Docker daemon
```

**Solution:** Start Docker Desktop or Docker daemon

### Port Already in Use

```
Error: Port 5432 is already allocated
```

**Solution:** Stop any local PostgreSQL/Redis instances or use different ports

### Migration Failures

```
Error: relation "workspaces" does not exist
```

**Solution:** Check that migrations in `orchestrator/db/migrations/` are valid

### Slow Tests

**Solution:** Use parallel execution:
```bash
uv run pytest tests/test_integration_suite.py -n auto
```

### Test Isolation Issues

If tests fail when run together but pass individually:

1. Check for shared state between tests
2. Verify transaction rollback is working
3. Add explicit cleanup if needed

## Performance

### Container Reuse

Containers start once per test session (not per test) for performance:

- **PostgreSQL**: ~2-3 seconds startup (session scope)
- **Redis**: ~1-2 seconds startup (session scope)
- **Per-test overhead**: ~10-50ms (transaction setup/rollback)

### Parallel Execution

Use `-n auto` for parallel execution:

```bash
# Sequential (slower)
uv run pytest tests/test_integration_suite.py -v
# Time: ~30 seconds

# Parallel (faster)
uv run pytest tests/test_integration_suite.py -v -n auto
# Time: ~10 seconds (3x speedup with 4 cores)
```

### CI/CD Optimization

For CI/CD pipelines:

1. Cache Docker images (postgres:16-alpine, redis:7-alpine)
2. Use parallel test execution
3. Run integration tests only on main branch or PRs

```yaml
# GitHub Actions example
- name: Run Integration Tests
  run: |
    uv run pytest orchestrator/backend/tests/test_integration_suite.py \
      -v -n auto --maxfail=3
```

## Coverage

Generate coverage reports:

```bash
# Run tests with coverage
uv run pytest tests/test_integration_suite.py --cov=orchestrator --cov-report=html

# View HTML report
open htmlcov/index.html
```

## Integration with Existing Tests

This integration test suite complements existing unit tests:

- **Unit tests** (`test_database.py`, etc.) - Test individual modules
- **Integration tests** (`test_integration_suite.py`) - Test full workflows

Run all tests together:

```bash
uv run pytest orchestrator/backend/tests/ -v
```

## Maintenance

### Adding New Test Categories

1. Add new test functions to `test_integration_suite.py`
2. Use appropriate fixtures (`db_conn`, `test_factory`, etc.)
3. Document what the test verifies
4. Update this README with the new test category

### Updating Test Factories

When database schema changes:

1. Update `TestDataFactory` methods in `conftest.py`
2. Ensure all required fields are populated
3. Run tests to verify factories still work

### Schema Changes

When migrations are added:

1. Testcontainers automatically apply new migrations
2. Update test factories if new tables/columns added
3. Add new tests for new functionality

## Questions?

See existing tests in `test_integration_suite.py` for examples.
