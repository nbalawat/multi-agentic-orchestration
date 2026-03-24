#!/usr/bin/env python3
"""
Setup test data for load testing
Creates workspaces, projects, and features for realistic load testing
"""

import argparse
import asyncio
import httpx
import sys
from typing import List, Dict, Any
from faker import Faker

fake = Faker()


class TestDataGenerator:
    """Generate test data for load testing"""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
        self.workspaces: List[Dict[str, Any]] = []
        self.projects: List[Dict[str, Any]] = []

    async def check_health(self) -> bool:
        """Check if backend is healthy"""
        try:
            response = await self.client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except Exception as e:
            print(f"❌ Backend health check failed: {e}")
            return False

    async def create_workspace(self, name: str) -> Dict[str, Any]:
        """Create a workspace"""
        payload = {
            "name": name,
            "description": f"Load test workspace - {fake.catch_phrase()}"
        }
        try:
            response = await self.client.post(
                f"{self.base_url}/api/workspaces",
                json=payload
            )
            if response.status_code == 201:
                workspace = response.json()
                print(f"✓ Created workspace: {workspace.get('name')} ({workspace.get('id')})")
                return workspace
            else:
                print(f"❌ Failed to create workspace: {response.status_code}")
                print(response.text)
                return {}
        except Exception as e:
            print(f"❌ Error creating workspace: {e}")
            return {}

    async def create_project(self, workspace_id: str, name: str) -> Dict[str, Any]:
        """Create a project"""
        archetypes = ["greenfield", "brownfield", "data-modernization", "reverse-engineering"]
        payload = {
            "name": name,
            "repo_path": f"/tmp/load-test-{name}",
            "archetype": fake.random_element(archetypes),
            "description": f"Load test project - {fake.bs()}"
        }
        try:
            response = await self.client.post(
                f"{self.base_url}/api/workspaces/{workspace_id}/projects",
                json=payload
            )
            if response.status_code == 201:
                project = response.json()
                print(f"  ✓ Created project: {project.get('name')} ({project.get('id')})")
                return project
            else:
                print(f"  ❌ Failed to create project: {response.status_code}")
                return {}
        except Exception as e:
            print(f"  ❌ Error creating project: {e}")
            return {}

    async def create_feature(self, project_id: str, name: str, priority: int) -> Dict[str, Any]:
        """Create a feature"""
        payload = {
            "name": name,
            "description": f"Load test feature - {fake.sentence()}",
            "priority": priority,
            "depends_on": []
        }
        try:
            response = await self.client.post(
                f"{self.base_url}/api/projects/{project_id}/features",
                json=payload
            )
            if response.status_code == 201:
                return response.json()
            else:
                return {}
        except Exception:
            return {}

    async def setup_test_data(self, num_workspaces: int, projects_per_workspace: int,
                             features_per_project: int) -> None:
        """Setup all test data"""
        print(f"\n🚀 Setting up test data:")
        print(f"  - Workspaces: {num_workspaces}")
        print(f"  - Projects per workspace: {projects_per_workspace}")
        print(f"  - Features per project: {features_per_project}")
        print()

        # Check backend health
        if not await self.check_health():
            print("❌ Backend is not healthy. Please start it first.")
            return

        # Create workspaces
        for i in range(num_workspaces):
            workspace_name = f"load_test_ws_{i}_{fake.word()}"
            workspace = await self.create_workspace(workspace_name)

            if workspace and 'id' in workspace:
                self.workspaces.append(workspace)

                # Create projects for this workspace
                for j in range(projects_per_workspace):
                    project_name = f"load_test_proj_{i}_{j}_{fake.word()}"
                    project = await self.create_project(workspace['id'], project_name)

                    if project and 'id' in project:
                        self.projects.append(project)

                        # Create features for this project
                        feature_count = 0
                        for k in range(features_per_project):
                            feature_name = f"feature_{k}_{fake.word()}"
                            priority = fake.random_int(min=1, max=3)
                            feature = await self.create_feature(project['id'], feature_name, priority)
                            if feature and 'id' in feature:
                                feature_count += 1

                        if feature_count > 0:
                            print(f"    ✓ Created {feature_count} features")

                # Small delay between workspaces
                await asyncio.sleep(0.1)

        print(f"\n✅ Test data setup complete!")
        print(f"  - Created {len(self.workspaces)} workspaces")
        print(f"  - Created {len(self.projects)} projects")

    async def cleanup(self):
        """Cleanup resources"""
        await self.client.aclose()


async def main():
    parser = argparse.ArgumentParser(description="Setup test data for RAPIDS load testing")
    parser.add_argument(
        "--workspaces", type=int, default=5,
        help="Number of workspaces to create (default: 5)"
    )
    parser.add_argument(
        "--projects", type=int, default=10,
        help="Number of projects per workspace (default: 10)"
    )
    parser.add_argument(
        "--features", type=int, default=5,
        help="Number of features per project (default: 5)"
    )
    parser.add_argument(
        "--host", type=str, default="http://127.0.0.1:9403",
        help="Backend URL (default: http://127.0.0.1:9403)"
    )

    args = parser.parse_args()

    generator = TestDataGenerator(args.host)
    try:
        await generator.setup_test_data(
            num_workspaces=args.workspaces,
            projects_per_workspace=args.projects,
            features_per_project=args.features
        )
    finally:
        await generator.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
        sys.exit(1)
