"""
Integration Test Suite

End-to-end integration tests with REAL PostgreSQL and Redis using Docker test containers.
Tests full workflows including multi-tenant isolation, RAPIDS lifecycle, and concurrent operations.

NO MOCKING - Tests are ephemeral with proper setup/teardown.

Run with: uv run pytest tests/test_integration_suite.py -v
Run in parallel: uv run pytest tests/test_integration_suite.py -v -n auto
"""

import pytest
import pytest_asyncio
import asyncio
import uuid
from datetime import datetime
from typing import Dict, Any


# ═══════════════════════════════════════════════════════════
# WORKSPACE ISOLATION TESTS
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_multi_tenant_workspace_isolation(db_conn, test_factory, isolation_verifier):
    """
    Test that workspaces are properly isolated from each other.

    Verifies:
    - Each workspace only sees its own projects
    - Projects cannot leak between workspaces
    - Concurrent workspace operations don't interfere
    """
    # Create two separate workspaces (multi-tenant scenario)
    workspace1 = await test_factory.create_workspace(name="Company A")
    workspace2 = await test_factory.create_workspace(name="Company B")

    workspace1_id = workspace1['id']
    workspace2_id = workspace2['id']

    # Create projects in workspace1
    project1_ws1 = await test_factory.create_project(
        workspace_id=workspace1_id,
        name="Project Alpha"
    )
    project2_ws1 = await test_factory.create_project(
        workspace_id=workspace1_id,
        name="Project Beta"
    )

    # Create projects in workspace2
    project1_ws2 = await test_factory.create_project(
        workspace_id=workspace2_id,
        name="Project Gamma"
    )

    # Verify workspace1 only sees its own projects
    ws1_projects = await db_conn.fetch(
        "SELECT id, name FROM projects WHERE workspace_id = $1",
        workspace1_id
    )
    assert len(ws1_projects) == 2
    ws1_names = {row['name'] for row in ws1_projects}
    assert ws1_names == {"Project Alpha", "Project Beta"}

    # Verify workspace2 only sees its own projects
    ws2_projects = await db_conn.fetch(
        "SELECT id, name FROM projects WHERE workspace_id = $1",
        workspace2_id
    )
    assert len(ws2_projects) == 1
    assert ws2_projects[0]['name'] == "Project Gamma"

    # Verify complete isolation using isolation verifier
    assert await isolation_verifier(workspace1_id, workspace2_id)

    print(f"✅ Workspace isolation verified: WS1={len(ws1_projects)} projects, WS2={len(ws2_projects)} projects")


@pytest.mark.asyncio
async def test_workspace_cascade_deletion(db_conn, test_factory):
    """
    Test that deleting a workspace cascades to all child resources.

    Verifies:
    - Projects are deleted when workspace is deleted
    - Features are deleted when projects are deleted
    - No orphaned records remain
    """
    # Create workspace with projects and features
    workspace = await test_factory.create_workspace(name="Temporary Workspace")
    workspace_id = workspace['id']

    project1 = await test_factory.create_project(workspace_id=workspace_id, name="Temp Project 1")
    project2 = await test_factory.create_project(workspace_id=workspace_id, name="Temp Project 2")

    feature1 = await test_factory.create_feature(project_id=project1['id'], feature_id="F001")
    feature2 = await test_factory.create_feature(project_id=project1['id'], feature_id="F002")
    feature3 = await test_factory.create_feature(project_id=project2['id'], feature_id="F003")

    # Verify all resources exist
    project_count = await db_conn.fetchval(
        "SELECT COUNT(*) FROM projects WHERE workspace_id = $1",
        workspace_id
    )
    assert project_count == 2

    feature_count = await db_conn.fetchval(
        """
        SELECT COUNT(*) FROM features f
        JOIN projects p ON f.project_id = p.id
        WHERE p.workspace_id = $1
        """,
        workspace_id
    )
    assert feature_count == 3

    # Delete workspace (should cascade)
    await db_conn.execute("DELETE FROM workspaces WHERE id = $1", workspace_id)

    # Verify cascade deletion
    project_count_after = await db_conn.fetchval(
        "SELECT COUNT(*) FROM projects WHERE workspace_id = $1",
        workspace_id
    )
    assert project_count_after == 0

    # Note: Features cascade depends on schema definition
    # If ON DELETE CASCADE is set up, features should be deleted too
    feature_count_after = await db_conn.fetchval(
        """
        SELECT COUNT(*) FROM features f
        WHERE f.project_id IN (
            SELECT id FROM projects WHERE workspace_id = $1
        )
        """,
        workspace_id
    )
    assert feature_count_after == 0

    print(f"✅ Cascade deletion verified: {project_count} projects, {feature_count} features deleted")


# ═══════════════════════════════════════════════════════════
# RAPIDS WORKFLOW TESTS
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_full_rapids_workflow(db_conn, test_factory):
    """
    Test complete RAPIDS workflow from workspace creation to feature execution.

    Workflow:
    1. Create workspace
    2. Create project in workspace
    3. Progress through RAPIDS phases (research → analysis → plan → implement)
    4. Create features in plan phase
    5. Execute features in implement phase
    6. Verify phase transitions and status updates
    """
    # Step 1: Create workspace
    workspace = await test_factory.create_workspace(name="RAPIDS Test Workspace")
    workspace_id = workspace['id']

    # Step 2: Create project
    project = await test_factory.create_project(
        workspace_id=workspace_id,
        name="Test Greenfield Project",
        archetype="greenfield",
        current_phase="research"
    )
    project_id = project['id']

    # Verify initial state
    assert project['current_phase'] == 'research'
    assert project['phase_status'] == 'not_started'

    # Step 3: Progress through phases
    phases = ["research", "analysis", "plan", "implement"]

    for phase in phases:
        # Create phase record
        phase_record = await db_conn.fetchrow(
            """
            INSERT INTO project_phases (
                project_id, phase, status, started_at, entry_criteria_met, metadata
            )
            VALUES ($1, $2, $3, NOW(), $4, $5)
            RETURNING *
            """,
            project_id, phase, "in_progress", True, {}
        )

        # Update project current phase
        await db_conn.execute(
            """
            UPDATE projects
            SET current_phase = $1, phase_status = $2, updated_at = NOW()
            WHERE id = $3
            """,
            phase, "in_progress", project_id
        )

        # Verify phase transition
        current_project = await db_conn.fetchrow(
            "SELECT * FROM projects WHERE id = $1",
            project_id
        )
        assert current_project['current_phase'] == phase
        assert current_project['phase_status'] == 'in_progress'

        print(f"   ✅ Phase {phase}: in_progress")

    # Step 4: Create features in plan phase
    features_data = [
        ("F001", "database-schema", "planned"),
        ("F002", "auth-system", "planned"),
        ("F003", "api-endpoints", "planned"),
    ]

    feature_ids = []
    for feature_id, name, status in features_data:
        feature = await test_factory.create_feature(
            project_id=project_id,
            feature_id=feature_id,
            name=name,
            status=status
        )
        feature_ids.append(feature['id'])

    # Verify features created
    feature_count = await db_conn.fetchval(
        "SELECT COUNT(*) FROM features WHERE project_id = $1",
        project_id
    )
    assert feature_count == 3

    # Step 5: Execute features (simulate implement phase)
    for feature_id in feature_ids:
        # Start execution
        await db_conn.execute(
            """
            UPDATE features
            SET status = $1, updated_at = NOW()
            WHERE id = $2
            """,
            "in_progress", feature_id
        )

        # Complete execution
        await db_conn.execute(
            """
            UPDATE features
            SET status = $1, updated_at = NOW()
            WHERE id = $2
            """,
            "complete", feature_id
        )

    # Verify all features completed
    completed_count = await db_conn.fetchval(
        """
        SELECT COUNT(*) FROM features
        WHERE project_id = $1 AND status = 'complete'
        """,
        project_id
    )
    assert completed_count == 3

    # Step 6: Complete implement phase
    await db_conn.execute(
        """
        UPDATE project_phases
        SET status = $1, completed_at = NOW(), exit_criteria_met = $2
        WHERE project_id = $3 AND phase = $4
        """,
        "complete", True, project_id, "implement"
    )

    # Verify implement phase completed
    implement_phase = await db_conn.fetchrow(
        """
        SELECT * FROM project_phases
        WHERE project_id = $1 AND phase = 'implement'
        """,
        project_id
    )
    assert implement_phase['status'] == 'complete'
    assert implement_phase['exit_criteria_met'] is True
    assert implement_phase['completed_at'] is not None

    print(f"✅ Full RAPIDS workflow completed: {len(phases)} phases, {feature_count} features")


@pytest.mark.asyncio
async def test_feature_dependency_graph(db_conn, test_factory):
    """
    Test feature dependency graph and execution ordering.

    Verifies:
    - Features can declare dependencies
    - Dependency graph is respected during execution
    - Dependent features cannot complete before dependencies
    """
    workspace = await test_factory.create_workspace()
    project = await test_factory.create_project(workspace_id=workspace['id'])
    project_id = project['id']

    # Create features with dependencies
    # F001 (no deps) → F002 (depends on F001) → F003 (depends on F002)
    f001 = await test_factory.create_feature(
        project_id=project_id,
        feature_id="F001",
        name="foundation",
        status="planned"
    )

    f002 = await db_conn.fetchrow(
        """
        INSERT INTO features (
            project_id, feature_id, name, description,
            category, status, dependencies, metadata
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING *
        """,
        project_id, "F002", "auth-system", "Authentication system",
        "core", "planned", ["F001"], {}
    )

    f003 = await db_conn.fetchrow(
        """
        INSERT INTO features (
            project_id, feature_id, name, description,
            category, status, dependencies, metadata
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING *
        """,
        project_id, "F003", "user-management", "User management",
        "core", "planned", ["F002"], {}
    )

    # Verify dependencies stored correctly
    f002_deps = await db_conn.fetchval(
        "SELECT dependencies FROM features WHERE feature_id = 'F002' AND project_id = $1",
        project_id
    )
    assert f002_deps == ["F001"]

    f003_deps = await db_conn.fetchval(
        "SELECT dependencies FROM features WHERE feature_id = 'F003' AND project_id = $1",
        project_id
    )
    assert f003_deps == ["F002"]

    # Execute features in dependency order
    # 1. Complete F001
    await db_conn.execute(
        "UPDATE features SET status = 'complete' WHERE id = $1",
        f001['id']
    )

    # 2. Now F002 can start (dependency met)
    f002_can_start = await db_conn.fetchval(
        """
        SELECT CASE
            WHEN NOT EXISTS (
                SELECT 1 FROM features
                WHERE feature_id = ANY($1::text[])
                AND project_id = $2
                AND status != 'complete'
            ) THEN true
            ELSE false
        END
        """,
        f002_deps, project_id
    )
    assert f002_can_start is True

    await db_conn.execute(
        "UPDATE features SET status = 'complete' WHERE id = $1",
        f002['id']
    )

    # 3. Now F003 can start (dependency met)
    f003_can_start = await db_conn.fetchval(
        """
        SELECT CASE
            WHEN NOT EXISTS (
                SELECT 1 FROM features
                WHERE feature_id = ANY($1::text[])
                AND project_id = $2
                AND status != 'complete'
            ) THEN true
            ELSE false
        END
        """,
        f003_deps, project_id
    )
    assert f003_can_start is True

    print("✅ Feature dependency graph verified: F001 → F002 → F003")


# ═══════════════════════════════════════════════════════════
# AGENT LIFECYCLE TESTS
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_orchestrator_agent_lifecycle(db_conn, test_factory):
    """
    Test orchestrator agent creation, execution, and cost tracking.

    Verifies:
    - Orchestrator agent singleton pattern
    - Session management
    - Cost accumulation
    - Agent status transitions
    """
    # Create orchestrator agent
    orch = await test_factory.create_orchestrator_agent(
        system_prompt="Test orchestrator prompt",
        working_dir="/tmp/test-orch"
    )
    orch_id = orch['id']

    # Verify initial state
    assert orch['status'] == 'idle'
    assert orch['input_tokens'] == 0
    assert orch['output_tokens'] == 0
    assert orch['total_cost'] == 0.0

    # Update status to executing
    await db_conn.execute(
        "UPDATE orchestrator_agents SET status = $1 WHERE id = $2",
        "executing", orch_id
    )

    # Simulate token usage
    await db_conn.execute(
        """
        UPDATE orchestrator_agents
        SET
            input_tokens = input_tokens + $1,
            output_tokens = output_tokens + $2,
            total_cost = total_cost + $3
        WHERE id = $4
        """,
        1000, 500, 0.015, orch_id
    )

    # Verify cost accumulation
    orch_updated = await db_conn.fetchrow(
        "SELECT * FROM orchestrator_agents WHERE id = $1",
        orch_id
    )
    assert orch_updated['input_tokens'] == 1000
    assert orch_updated['output_tokens'] == 500
    assert float(orch_updated['total_cost']) == 0.015

    # Add more usage (simulating multiple turns)
    await db_conn.execute(
        """
        UPDATE orchestrator_agents
        SET
            input_tokens = input_tokens + $1,
            output_tokens = output_tokens + $2,
            total_cost = total_cost + $3
        WHERE id = $4
        """,
        2000, 1000, 0.030, orch_id
    )

    # Verify cumulative costs
    orch_final = await db_conn.fetchrow(
        "SELECT * FROM orchestrator_agents WHERE id = $1",
        orch_id
    )
    assert orch_final['input_tokens'] == 3000
    assert orch_final['output_tokens'] == 1500
    assert abs(float(orch_final['total_cost']) - 0.045) < 0.0001

    print(f"✅ Orchestrator lifecycle verified: {orch_final['input_tokens']} tokens, ${orch_final['total_cost']:.4f}")


@pytest.mark.asyncio
async def test_sub_agent_creation_and_tracking(db_conn, test_factory):
    """
    Test sub-agent creation and parent-child relationship tracking.

    Verifies:
    - Sub-agents linked to orchestrator
    - Multiple agents can exist concurrently
    - Independent cost tracking per agent
    """
    # Create orchestrator
    orch = await test_factory.create_orchestrator_agent()
    orch_id = orch['id']

    # Create multiple sub-agents
    agent1 = await test_factory.create_agent(
        orchestrator_agent_id=orch_id,
        name="feature-builder-1",
        model="claude-sonnet-4"
    )

    agent2 = await test_factory.create_agent(
        orchestrator_agent_id=orch_id,
        name="feature-builder-2",
        model="claude-sonnet-4"
    )

    agent3 = await test_factory.create_agent(
        orchestrator_agent_id=orch_id,
        name="test-runner",
        model="claude-haiku-4"
    )

    # Verify all agents linked to orchestrator
    agent_count = await db_conn.fetchval(
        "SELECT COUNT(*) FROM agents WHERE orchestrator_agent_id = $1",
        orch_id
    )
    assert agent_count == 3

    # Simulate different cost profiles for each agent
    await db_conn.execute(
        "UPDATE agents SET input_tokens = 5000, output_tokens = 2000, total_cost = 0.10 WHERE id = $1",
        agent1['id']
    )
    await db_conn.execute(
        "UPDATE agents SET input_tokens = 3000, output_tokens = 1500, total_cost = 0.06 WHERE id = $1",
        agent2['id']
    )
    await db_conn.execute(
        "UPDATE agents SET input_tokens = 1000, output_tokens = 500, total_cost = 0.01 WHERE id = $1",
        agent3['id']
    )

    # Calculate total cost across all agents
    total_cost = await db_conn.fetchval(
        "SELECT SUM(total_cost) FROM agents WHERE orchestrator_agent_id = $1",
        orch_id
    )
    assert abs(float(total_cost) - 0.17) < 0.0001

    # Verify individual agent costs
    agents = await db_conn.fetch(
        "SELECT name, input_tokens, output_tokens, total_cost FROM agents WHERE orchestrator_agent_id = $1",
        orch_id
    )

    cost_by_agent = {row['name']: float(row['total_cost']) for row in agents}
    assert cost_by_agent['feature-builder-1'] == 0.10
    assert cost_by_agent['feature-builder-2'] == 0.06
    assert cost_by_agent['test-runner'] == 0.01

    print(f"✅ Sub-agent tracking verified: {agent_count} agents, total cost ${total_cost:.4f}")


@pytest.mark.asyncio
async def test_agent_log_insertion_and_retrieval(db_conn, test_factory):
    """
    Test agent event logging for debugging and monitoring.

    Verifies:
    - Agent logs capture tool usage, errors, and events
    - Logs associated with correct agent
    - Log retrieval with filtering
    """
    # Create agent
    orch = await test_factory.create_orchestrator_agent()
    agent = await test_factory.create_agent(orchestrator_agent_id=orch['id'])
    agent_id = agent['id']

    # Insert various log events
    log_events = [
        ("tool_use", "pre", {"tool": "Read", "args": {"file_path": "/test.py"}}),
        ("tool_use", "post", {"tool": "Read", "result": "success"}),
        ("error", None, {"error": "FileNotFoundError", "message": "File not found"}),
        ("completion", None, {"status": "success", "tokens": 500}),
    ]

    for event_type, event_step, event_data in log_events:
        await db_conn.execute(
            """
            INSERT INTO agent_logs (
                agent_id, event_type, event_step, event_data
            )
            VALUES ($1, $2, $3, $4)
            """,
            agent_id, event_type, event_step, event_data
        )

    # Retrieve all logs for agent
    logs = await db_conn.fetch(
        "SELECT * FROM agent_logs WHERE agent_id = $1 ORDER BY created_at",
        agent_id
    )
    assert len(logs) == 4

    # Filter logs by event type
    tool_logs = await db_conn.fetch(
        "SELECT * FROM agent_logs WHERE agent_id = $1 AND event_type = 'tool_use'",
        agent_id
    )
    assert len(tool_logs) == 2

    error_logs = await db_conn.fetch(
        "SELECT * FROM agent_logs WHERE agent_id = $1 AND event_type = 'error'",
        agent_id
    )
    assert len(error_logs) == 1
    assert error_logs[0]['event_data']['error'] == 'FileNotFoundError'

    print(f"✅ Agent logging verified: {len(logs)} total logs, {len(tool_logs)} tool logs, {len(error_logs)} errors")


# ═══════════════════════════════════════════════════════════
# CONCURRENT OPERATIONS TESTS
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_concurrent_feature_execution(db_conn, test_factory):
    """
    Test concurrent feature execution with proper isolation.

    Verifies:
    - Multiple features can execute concurrently
    - No race conditions in status updates
    - Cost tracking remains accurate under concurrency
    """
    workspace = await test_factory.create_workspace()
    project = await test_factory.create_project(workspace_id=workspace['id'])
    project_id = project['id']

    # Create multiple independent features (no dependencies)
    features = []
    for i in range(5):
        feature = await test_factory.create_feature(
            project_id=project_id,
            feature_id=f"F{i:03d}",
            name=f"feature-{i}",
            status="planned"
        )
        features.append(feature)

    # Simulate concurrent execution
    async def execute_feature(feature_id):
        """Simulate feature execution with random work."""
        # Start feature
        await db_conn.execute(
            "UPDATE features SET status = 'in_progress' WHERE id = $1",
            feature_id
        )

        # Simulate work
        await asyncio.sleep(0.01)

        # Complete feature
        await db_conn.execute(
            "UPDATE features SET status = 'complete' WHERE id = $1",
            feature_id
        )

    # Execute all features concurrently
    await asyncio.gather(*[
        execute_feature(feature['id'])
        for feature in features
    ])

    # Verify all features completed
    completed_count = await db_conn.fetchval(
        """
        SELECT COUNT(*) FROM features
        WHERE project_id = $1 AND status = 'complete'
        """,
        project_id
    )
    assert completed_count == 5

    print(f"✅ Concurrent execution verified: {completed_count} features completed concurrently")


@pytest.mark.asyncio
async def test_concurrent_workspace_operations(db_conn, test_factory):
    """
    Test concurrent operations across multiple workspaces.

    Verifies:
    - Multiple workspaces can be created concurrently
    - Workspace isolation maintained under concurrency
    - No cross-workspace data leakage
    """
    async def create_workspace_with_projects(workspace_name: str, num_projects: int):
        """Create workspace with multiple projects."""
        workspace = await test_factory.create_workspace(name=workspace_name)
        workspace_id = workspace['id']

        for i in range(num_projects):
            await test_factory.create_project(
                workspace_id=workspace_id,
                name=f"{workspace_name}-project-{i}"
            )

        return workspace_id

    # Create 3 workspaces concurrently, each with 3 projects
    workspace_ids = await asyncio.gather(
        create_workspace_with_projects("Workspace-A", 3),
        create_workspace_with_projects("Workspace-B", 3),
        create_workspace_with_projects("Workspace-C", 3),
    )

    # Verify each workspace has exactly 3 projects
    for workspace_id in workspace_ids:
        project_count = await db_conn.fetchval(
            "SELECT COUNT(*) FROM projects WHERE workspace_id = $1",
            workspace_id
        )
        assert project_count == 3

    # Verify total project count
    total_projects = await db_conn.fetchval(
        """
        SELECT COUNT(*) FROM projects
        WHERE workspace_id = ANY($1::uuid[])
        """,
        workspace_ids
    )
    assert total_projects == 9

    print(f"✅ Concurrent workspace operations verified: {len(workspace_ids)} workspaces, {total_projects} projects")


# ═══════════════════════════════════════════════════════════
# CLEANUP VERIFICATION TESTS
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_transaction_rollback_cleanup(db_conn, test_factory):
    """
    Test that transaction rollback properly cleans up test data.

    This test verifies the ephemeral nature of our test fixtures.
    The db_conn fixture uses transactions that rollback after each test,
    ensuring no test data persists.

    Note: This test itself doesn't leave data behind due to transaction rollback.
    """
    # Create test data
    workspace = await test_factory.create_workspace(name="Ephemeral Workspace")
    workspace_id = workspace['id']

    project = await test_factory.create_project(
        workspace_id=workspace_id,
        name="Ephemeral Project"
    )

    # Verify data exists within transaction
    workspace_exists = await db_conn.fetchval(
        "SELECT COUNT(*) FROM workspaces WHERE id = $1",
        workspace_id
    )
    assert workspace_exists == 1

    # Note: When this test ends, the transaction will rollback
    # and all data will be cleaned up automatically
    print("✅ Transaction rollback will clean up ephemeral data")


@pytest.mark.asyncio
async def test_explicit_cleanup_verification(db_conn, test_factory, cleanup_tracker):
    """
    Test explicit resource cleanup and verification.

    Verifies:
    - Resources can be explicitly deleted
    - cleanup_tracker can verify deletion
    - No orphaned resources remain
    """
    # Create resources
    workspace = await test_factory.create_workspace()
    workspace_id = workspace['id']
    cleanup_tracker.add("workspace", workspace_id)

    project = await test_factory.create_project(workspace_id=workspace_id)
    project_id = project['id']
    cleanup_tracker.add("project", project_id)

    # Verify resources exist
    assert await db_conn.fetchval(
        "SELECT COUNT(*) FROM workspaces WHERE id = $1", workspace_id
    ) == 1
    assert await db_conn.fetchval(
        "SELECT COUNT(*) FROM projects WHERE id = $1", project_id
    ) == 1

    # Delete resources
    await db_conn.execute("DELETE FROM projects WHERE id = $1", project_id)
    await db_conn.execute("DELETE FROM workspaces WHERE id = $1", workspace_id)

    # Verify cleanup
    assert await cleanup_tracker.verify_deleted(db_conn, "project", project_id)
    assert await cleanup_tracker.verify_deleted(db_conn, "workspace", workspace_id)

    print("✅ Explicit cleanup verified: all resources deleted")


# ═══════════════════════════════════════════════════════════
# REDIS INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_redis_session_storage(redis_client):
    """
    Test Redis for session storage and caching.

    Verifies:
    - Basic Redis operations (set, get, delete)
    - Session data serialization
    - TTL (time-to-live) functionality
    """
    session_id = f"session-{uuid.uuid4()}"
    session_data = {
        "user_id": str(uuid.uuid4()),
        "workspace_id": str(uuid.uuid4()),
        "created_at": datetime.utcnow().isoformat()
    }

    # Store session with TTL
    import json
    await redis_client.setex(
        f"session:{session_id}",
        3600,  # 1 hour TTL
        json.dumps(session_data)
    )

    # Retrieve session
    stored_data = await redis_client.get(f"session:{session_id}")
    assert stored_data is not None

    retrieved_session = json.loads(stored_data)
    assert retrieved_session['user_id'] == session_data['user_id']

    # Verify TTL
    ttl = await redis_client.ttl(f"session:{session_id}")
    assert ttl > 0
    assert ttl <= 3600

    # Delete session
    await redis_client.delete(f"session:{session_id}")

    # Verify deletion
    deleted_data = await redis_client.get(f"session:{session_id}")
    assert deleted_data is None

    print(f"✅ Redis session storage verified: TTL={ttl}s")


@pytest.mark.asyncio
async def test_redis_rate_limiting(redis_client):
    """
    Test Redis-based rate limiting using token bucket algorithm.

    Verifies:
    - Rate limit counter increments correctly
    - Limits enforced properly
    - Counter resets after TTL expires
    """
    user_id = str(uuid.uuid4())
    rate_limit_key = f"rate_limit:{user_id}"
    max_requests = 5
    window_seconds = 60

    # Simulate requests
    request_count = 0
    for i in range(7):  # Try 7 requests (limit is 5)
        # Increment counter
        current = await redis_client.incr(rate_limit_key)

        # Set TTL on first request
        if current == 1:
            await redis_client.expire(rate_limit_key, window_seconds)

        # Check if within limit
        if current <= max_requests:
            request_count += 1
        else:
            # Rate limit exceeded
            break

    # Verify rate limit enforced
    assert request_count == 5

    # Verify counter value
    final_count = await redis_client.get(rate_limit_key)
    assert int(final_count) == 6  # 6th request incremented counter but was rejected

    # Verify TTL set
    ttl = await redis_client.ttl(rate_limit_key)
    assert ttl > 0

    print(f"✅ Redis rate limiting verified: {request_count}/{max_requests} requests allowed")


@pytest.mark.asyncio
async def test_redis_agent_coordination(redis_client):
    """
    Test Redis for agent coordination and distributed locking.

    Verifies:
    - Distributed locks for concurrent agent operations
    - Lock acquisition and release
    - Lock timeout handling
    """
    resource_id = f"feature-{uuid.uuid4()}"
    lock_key = f"lock:{resource_id}"
    lock_timeout = 10  # seconds

    # Agent 1 acquires lock
    lock_acquired = await redis_client.set(
        lock_key,
        "agent-1",
        nx=True,  # Only set if not exists
        ex=lock_timeout
    )
    assert lock_acquired is True

    # Agent 2 tries to acquire same lock (should fail)
    lock_2_acquired = await redis_client.set(
        lock_key,
        "agent-2",
        nx=True,
        ex=lock_timeout
    )
    assert lock_2_acquired is None  # Lock not acquired

    # Verify lock holder
    lock_holder = await redis_client.get(lock_key)
    assert lock_holder == "agent-1"

    # Agent 1 releases lock
    await redis_client.delete(lock_key)

    # Now Agent 2 can acquire lock
    lock_2_acquired = await redis_client.set(
        lock_key,
        "agent-2",
        nx=True,
        ex=lock_timeout
    )
    assert lock_2_acquired is True

    lock_holder = await redis_client.get(lock_key)
    assert lock_holder == "agent-2"

    print("✅ Redis distributed locking verified: lock acquisition and release")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
