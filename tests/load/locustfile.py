#!/usr/bin/env python3
"""
Load and Performance Tests for RAPIDS Meta-Orchestrator
Uses Locust for load testing with configurable scenarios.

Target: 1000 req/s with p95 latency < 300ms
"""

import json
import random
import uuid
from typing import Any, Dict, List
from locust import HttpUser, task, between, events, TaskSet
from locust.runners import MasterRunner, WorkerRunner


# Test data generators
class TestDataGenerator:
    """Generate realistic test data for orchestrator operations"""

    @staticmethod
    def workspace_name() -> str:
        """Generate unique workspace name"""
        return f"workspace_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def project_data() -> Dict[str, Any]:
        """Generate project onboarding data"""
        return {
            "name": f"project_{uuid.uuid4().hex[:8]}",
            "repo_path": f"/tmp/test-repo-{uuid.uuid4().hex[:8]}",
            "archetype": random.choice(["greenfield", "brownfield", "data-modernization", "reverse-engineering"]),
            "description": f"Test project for load testing - {uuid.uuid4().hex[:8]}"
        }

    @staticmethod
    def feature_data() -> Dict[str, Any]:
        """Generate feature data"""
        return {
            "name": f"feature_{uuid.uuid4().hex[:8]}",
            "description": f"Load test feature - {uuid.uuid4().hex}",
            "priority": random.randint(1, 3),
            "depends_on": []
        }

    @staticmethod
    def chat_message() -> Dict[str, Any]:
        """Generate chat message"""
        messages = [
            "What is the current status of the orchestrator?",
            "List all active agents",
            "Show me the project dashboard",
            "What plugins are available?",
            "Get the feature DAG status"
        ]
        return {
            "message": random.choice(messages),
            "stream": False
        }


class WorkspaceOperations(TaskSet):
    """Task set for workspace-related operations"""

    @task(3)
    def list_workspaces(self):
        """List all workspaces"""
        with self.client.get(
            "/api/workspaces",
            catch_response=True,
            name="/api/workspaces [LIST]"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got status code {response.status_code}")

    @task(1)
    def create_workspace(self):
        """Create a new workspace"""
        workspace_name = TestDataGenerator.workspace_name()
        with self.client.post(
            "/api/workspaces",
            json={"name": workspace_name, "description": "Load test workspace"},
            catch_response=True,
            name="/api/workspaces [CREATE]"
        ) as response:
            if response.status_code == 201:
                data = response.json()
                # Store workspace ID for later use
                if hasattr(self.user, 'workspace_ids'):
                    self.user.workspace_ids.append(data.get('id'))
                response.success()
            else:
                response.failure(f"Got status code {response.status_code}")

    @task(2)
    def get_workspace(self):
        """Get workspace details"""
        if hasattr(self.user, 'workspace_ids') and self.user.workspace_ids:
            workspace_id = random.choice(self.user.workspace_ids)
            with self.client.get(
                f"/api/workspaces/{workspace_id}",
                catch_response=True,
                name="/api/workspaces/{id} [GET]"
            ) as response:
                if response.status_code == 200:
                    response.success()
                else:
                    response.failure(f"Got status code {response.status_code}")


class ProjectOperations(TaskSet):
    """Task set for project-related operations"""

    @task(5)
    def get_project_dashboard(self):
        """Get project dashboard"""
        with self.client.get(
            "/api/project_dashboard",
            catch_response=True,
            name="/api/project_dashboard [GET]"
        ) as response:
            if response.status_code in [200, 404]:  # 404 is ok if no project is active
                response.success()
            else:
                response.failure(f"Got status code {response.status_code}")

    @task(3)
    def list_features(self):
        """List project features"""
        if hasattr(self.user, 'project_ids') and self.user.project_ids:
            project_id = random.choice(self.user.project_ids)
            with self.client.get(
                f"/api/projects/{project_id}/features",
                catch_response=True,
                name="/api/projects/{id}/features [LIST]"
            ) as response:
                if response.status_code == 200:
                    response.success()
                else:
                    response.failure(f"Got status code {response.status_code}")

    @task(2)
    def get_feature_dag(self):
        """Get feature DAG"""
        if hasattr(self.user, 'project_ids') and self.user.project_ids:
            project_id = random.choice(self.user.project_ids)
            with self.client.get(
                f"/api/projects/{project_id}/dag",
                catch_response=True,
                name="/api/projects/{id}/dag [GET]"
            ) as response:
                if response.status_code in [200, 404]:  # 404 is ok if DAG doesn't exist
                    response.success()
                else:
                    response.failure(f"Got status code {response.status_code}")

    @task(2)
    def get_project_phases(self):
        """List project phases"""
        if hasattr(self.user, 'project_ids') and self.user.project_ids:
            project_id = random.choice(self.user.project_ids)
            with self.client.get(
                f"/api/projects/{project_id}/phases",
                catch_response=True,
                name="/api/projects/{id}/phases [LIST]"
            ) as response:
                if response.status_code == 200:
                    response.success()
                else:
                    response.failure(f"Got status code {response.status_code}")

    @task(1)
    def get_execution_status(self):
        """Get execution status"""
        if hasattr(self.user, 'project_ids') and self.user.project_ids:
            project_id = random.choice(self.user.project_ids)
            with self.client.get(
                f"/api/projects/{project_id}/execution-status",
                catch_response=True,
                name="/api/projects/{id}/execution-status [GET]"
            ) as response:
                if response.status_code == 200:
                    response.success()
                else:
                    response.failure(f"Got status code {response.status_code}")


class OrchestratorOperations(TaskSet):
    """Task set for orchestrator operations"""

    @task(5)
    def health_check(self):
        """Health check endpoint"""
        with self.client.get(
            "/health",
            catch_response=True,
            name="/health [GET]"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got status code {response.status_code}")

    @task(3)
    def get_orchestrator_status(self):
        """Get orchestrator status"""
        with self.client.get(
            "/get_orchestrator",
            catch_response=True,
            name="/get_orchestrator [GET]"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got status code {response.status_code}")

    @task(4)
    def list_agents(self):
        """List all agents"""
        with self.client.get(
            "/list_agents",
            catch_response=True,
            name="/list_agents [GET]"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got status code {response.status_code}")

    @task(3)
    def get_events(self):
        """Get events with pagination"""
        params = {
            "limit": random.randint(10, 50),
            "offset": random.randint(0, 100)
        }
        with self.client.get(
            "/get_events",
            params=params,
            catch_response=True,
            name="/get_events [GET]"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got status code {response.status_code}")

    @task(2)
    def get_active_context(self):
        """Get active context"""
        with self.client.get(
            "/api/active-context",
            catch_response=True,
            name="/api/active-context [GET]"
        ) as response:
            if response.status_code in [200, 404]:  # 404 is ok if no context
                response.success()
            else:
                response.failure(f"Got status code {response.status_code}")

    @task(1)
    def list_plugins(self):
        """List available plugins"""
        with self.client.get(
            "/api/plugins",
            catch_response=True,
            name="/api/plugins [LIST]"
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Got status code {response.status_code}")


class ReadOnlyUser(HttpUser):
    """
    Read-only user simulating monitoring/dashboard queries.
    High frequency, low resource usage.
    """
    wait_time = between(0.1, 0.5)  # Fast polling

    tasks = {
        OrchestratorOperations: 7,
        ProjectOperations: 3
    }

    def on_start(self):
        """Initialize user session"""
        self.workspace_ids: List[str] = []
        self.project_ids: List[str] = []
        # Pre-populate with some IDs if available
        self._load_existing_resources()

    def _load_existing_resources(self):
        """Load existing workspace/project IDs"""
        try:
            # Get workspaces
            response = self.client.get("/api/workspaces")
            if response.status_code == 200:
                workspaces = response.json()
                self.workspace_ids = [w['id'] for w in workspaces if 'id' in w]
        except Exception:
            pass  # Continue with empty lists


class MixedUser(HttpUser):
    """
    Mixed read/write user simulating normal usage.
    Medium frequency, mixed operations.
    """
    wait_time = between(0.5, 2.0)

    tasks = {
        OrchestratorOperations: 5,
        ProjectOperations: 3,
        WorkspaceOperations: 2
    }

    def on_start(self):
        """Initialize user session"""
        self.workspace_ids: List[str] = []
        self.project_ids: List[str] = []
        self._load_existing_resources()

    def _load_existing_resources(self):
        """Load existing workspace/project IDs"""
        try:
            response = self.client.get("/api/workspaces")
            if response.status_code == 200:
                workspaces = response.json()
                self.workspace_ids = [w['id'] for w in workspaces if 'id' in w]
        except Exception:
            pass


class HeavyUser(HttpUser):
    """
    Heavy user simulating intensive operations.
    Lower frequency, resource-intensive operations.
    """
    wait_time = between(1.0, 3.0)

    tasks = {
        WorkspaceOperations: 5,
        ProjectOperations: 4,
        OrchestratorOperations: 1
    }

    def on_start(self):
        """Initialize user session"""
        self.workspace_ids: List[str] = []
        self.project_ids: List[str] = []
        self._load_existing_resources()

    def _load_existing_resources(self):
        """Load existing workspace/project IDs"""
        try:
            response = self.client.get("/api/workspaces")
            if response.status_code == 200:
                workspaces = response.json()
                self.workspace_ids = [w['id'] for w in workspaces if 'id' in w]
        except Exception:
            pass


# Event hooks for custom metrics
@events.init.add_listener
def on_locust_init(environment, **kwargs):
    """Initialize test environment"""
    if isinstance(environment.runner, MasterRunner):
        print("🚀 Locust Master initialized")
    elif isinstance(environment.runner, WorkerRunner):
        print("🔧 Locust Worker initialized")
    else:
        print("📊 Locust Standalone initialized")


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Test start hook"""
    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║          RAPIDS Meta-Orchestrator Load Test Starting            ║
╠══════════════════════════════════════════════════════════════════╣
║  Target: 1000 req/s                                             ║
║  P95 Latency: < 300ms                                           ║
║  Scenarios: Ramp-up, Sustained, Spike                           ║
╚══════════════════════════════════════════════════════════════════╝
    """)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Test stop hook - print summary"""
    stats = environment.stats

    print(f"""
╔══════════════════════════════════════════════════════════════════╗
║               Load Test Summary                                  ║
╠══════════════════════════════════════════════════════════════════╣
║  Total Requests: {stats.total.num_requests:,}
║  Failed Requests: {stats.total.num_failures:,}
║  Median Response Time: {stats.total.median_response_time:.2f}ms
║  95th Percentile: {stats.total.get_response_time_percentile(0.95):.2f}ms
║  99th Percentile: {stats.total.get_response_time_percentile(0.99):.2f}ms
║  Avg Response Time: {stats.total.avg_response_time:.2f}ms
║  RPS: {stats.total.total_rps:.2f}
╚══════════════════════════════════════════════════════════════════╝
    """)

    # Check if we met our targets
    p95 = stats.total.get_response_time_percentile(0.95)
    rps = stats.total.total_rps

    if p95 < 300:
        print("✅ P95 latency target met (< 300ms)")
    else:
        print(f"❌ P95 latency target missed: {p95:.2f}ms (target: < 300ms)")

    if rps >= 1000:
        print("✅ RPS target met (>= 1000 req/s)")
    else:
        print(f"⚠️  RPS: {rps:.2f} req/s (target: >= 1000 req/s)")
