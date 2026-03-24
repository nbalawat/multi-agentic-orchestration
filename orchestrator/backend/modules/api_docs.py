#!/usr/bin/env python3
"""
OpenAPI/Swagger documentation configuration for the RAPIDS Meta-Orchestrator API.

This module provides comprehensive API documentation including:
- OpenAPI metadata and tags
- Request/response examples
- SDK usage guides
- Authentication information
"""

from typing import Dict, Any, List
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════
# OPENAPI METADATA
# ═══════════════════════════════════════════════════════════

OPENAPI_METADATA = {
    "title": "RAPIDS Meta-Orchestrator API",
    "version": "1.0.0",
    "description": """
# RAPIDS Meta-Orchestrator API

The RAPIDS Meta-Orchestrator provides a comprehensive API for managing multi-project
agentic workflows using the Claude Agent SDK.

## Features

- 🏗️ **Multi-Project Workspace Management** - Organize multiple projects in workspaces
- 🤖 **Agent Orchestration** - Spawn and manage Claude AI agents with advanced capabilities
- 📊 **Phase-Based Workflow** - Research → Analysis → Plan → Implement → Deploy → Sustain
- 🔄 **Feature DAG Execution** - Autonomous parallel feature implementation with dependency tracking
- 🔌 **Archetype Plugin System** - Extend functionality with custom archetype plugins
- 💬 **Real-time Communication** - WebSocket support for live agent interaction

## Getting Started

1. **Create a Workspace**: Start by creating a workspace to organize your projects
2. **Onboard a Project**: Add a project to your workspace with its repository path
3. **Execute RAPIDS Workflow**: Progress through phases from Research to Sustain
4. **Monitor Execution**: Track feature implementation and agent activities in real-time

## Authentication

This API currently does not require authentication. Future versions may add API key support.

## Rate Limiting

No rate limiting is currently enforced. Best practice: limit to 100 requests/minute per client.

## SDK Support

Python SDK example:
```python
from httpx import AsyncClient

async with AsyncClient(base_url="http://localhost:8000") as client:
    # Create workspace
    response = await client.post("/api/workspaces", json={
        "name": "my-workspace",
        "description": "My first workspace"
    })
    workspace = response.json()

    # Onboard project
    response = await client.post(
        f"/api/workspaces/{workspace['id']}/projects",
        json={
            "name": "my-project",
            "repo_path": "/path/to/repo",
            "archetype": "greenfield"
        }
    )
    project = response.json()
```

## WebSocket Events

Connect to `/ws` for real-time updates on agent activities, phase transitions, and feature execution.

## Support

For issues and questions, see: https://github.com/your-org/rapids-meta-orchestrator
    """,
    "contact": {
        "name": "RAPIDS Meta-Orchestrator Team",
        "url": "https://github.com/your-org/rapids-meta-orchestrator",
    },
    "license_info": {
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
}


# ═══════════════════════════════════════════════════════════
# API TAGS FOR ENDPOINT ORGANIZATION
# ═══════════════════════════════════════════════════════════

OPENAPI_TAGS = [
    {
        "name": "Health",
        "description": "Health check and readiness endpoints for monitoring service status.",
    },
    {
        "name": "Orchestrator",
        "description": "Core orchestrator agent management and chat interface.",
    },
    {
        "name": "Workspaces",
        "description": "Workspace management for organizing multiple projects.",
    },
    {
        "name": "Projects",
        "description": "Project onboarding, management, and context switching.",
    },
    {
        "name": "Phases",
        "description": "RAPIDS lifecycle phase management (Research → Analysis → Plan → Implement → Deploy → Sustain).",
    },
    {
        "name": "Features",
        "description": "Feature DAG management and autonomous execution tracking.",
    },
    {
        "name": "Agents",
        "description": "Sub-agent lifecycle management and monitoring.",
    },
    {
        "name": "Plugins",
        "description": "Archetype plugin discovery and capability enumeration.",
    },
    {
        "name": "Circuit Breakers",
        "description": "Circuit breaker status monitoring for resilience management.",
    },
    {
        "name": "Utilities",
        "description": "Utility endpoints for file operations and system information.",
    },
]


# ═══════════════════════════════════════════════════════════
# PYDANTIC MODEL EXAMPLES
# ═══════════════════════════════════════════════════════════

class WorkspaceExample(BaseModel):
    """Example workspace response."""

    id: str = Field(
        ...,
        example="ws_9f8e7d6c5b4a",
        description="Unique workspace identifier"
    )
    name: str = Field(
        ...,
        example="ML Research Projects",
        description="Human-readable workspace name"
    )
    description: str | None = Field(
        None,
        example="Workspace for machine learning research and experiments",
        description="Optional workspace description"
    )
    created_at: str = Field(
        ...,
        example="2026-03-24T10:30:00Z",
        description="ISO 8601 timestamp of workspace creation"
    )
    updated_at: str = Field(
        ...,
        example="2026-03-24T10:30:00Z",
        description="ISO 8601 timestamp of last update"
    )


class ProjectExample(BaseModel):
    """Example project response."""

    id: str = Field(
        ...,
        example="proj_1a2b3c4d5e6f",
        description="Unique project identifier"
    )
    name: str = Field(
        ...,
        example="agent-memory",
        description="Project name"
    )
    workspace_id: str = Field(
        ...,
        example="ws_9f8e7d6c5b4a",
        description="Parent workspace ID"
    )
    repo_path: str = Field(
        ...,
        example="/Users/dev/projects/agent-memory",
        description="Absolute path to project repository"
    )
    archetype: str = Field(
        ...,
        example="greenfield",
        description="Project archetype (greenfield, refactor, debug, etc.)"
    )
    current_phase: str = Field(
        ...,
        example="implement",
        description="Current RAPIDS phase"
    )
    repo_url: str | None = Field(
        None,
        example="https://github.com/org/agent-memory",
        description="Optional Git repository URL"
    )


class FeatureExample(BaseModel):
    """Example feature response."""

    id: str = Field(
        ...,
        example="feat_auth_system",
        description="Feature identifier (kebab-case)"
    )
    project_id: str = Field(
        ...,
        example="proj_1a2b3c4d5e6f",
        description="Parent project ID"
    )
    name: str = Field(
        ...,
        example="Authentication System",
        description="Human-readable feature name"
    )
    description: str = Field(
        ...,
        example="Implement JWT-based authentication with role-based access control",
        description="Detailed feature description"
    )
    status: str = Field(
        ...,
        example="in_progress",
        description="Feature status: pending, ready, in_progress, verifying, complete, failed"
    )
    dependencies: List[str] = Field(
        default_factory=list,
        example=["feat_user_model", "feat_database_setup"],
        description="List of feature IDs that must complete before this feature can start"
    )
    assigned_agent_id: str | None = Field(
        None,
        example="agent_7x8y9z",
        description="Agent currently implementing this feature"
    )


class AgentExample(BaseModel):
    """Example agent response."""

    id: str = Field(
        ...,
        example="agent_7x8y9z",
        description="Unique agent identifier"
    )
    name: str = Field(
        ...,
        example="feature-builder-auth",
        description="Agent name"
    )
    status: str = Field(
        ...,
        example="active",
        description="Agent status: active, idle, completed, failed"
    )
    type: str = Field(
        ...,
        example="feature-builder",
        description="Agent type/role"
    )
    feature_id: str | None = Field(
        None,
        example="feat_auth_system",
        description="Feature being implemented (if applicable)"
    )
    created_at: str = Field(
        ...,
        example="2026-03-24T10:35:00Z",
        description="ISO 8601 timestamp of agent creation"
    )


# ═══════════════════════════════════════════════════════════
# SDK USAGE GUIDES
# ═══════════════════════════════════════════════════════════

SDK_USAGE_GUIDE = """
# SDK Usage Guide

## Python SDK

### Installation

```bash
pip install httpx pydantic
```

### Basic Usage

```python
import asyncio
from httpx import AsyncClient
from typing import Any, Dict

class RAPIDSClient:
    \"\"\"Python client for RAPIDS Meta-Orchestrator API.\"\"\"

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = AsyncClient(base_url=base_url)

    async def create_workspace(self, name: str, description: str = None) -> Dict[str, Any]:
        \"\"\"Create a new workspace.\"\"\"
        response = await self.client.post(
            "/api/workspaces",
            json={"name": name, "description": description}
        )
        response.raise_for_status()
        return response.json()

    async def onboard_project(
        self,
        workspace_id: str,
        name: str,
        repo_path: str,
        archetype: str = "greenfield",
        repo_url: str = None
    ) -> Dict[str, Any]:
        \"\"\"Onboard a new project to a workspace.\"\"\"
        response = await self.client.post(
            f"/api/workspaces/{workspace_id}/projects",
            json={
                "name": name,
                "repo_path": repo_path,
                "archetype": archetype,
                "repo_url": repo_url
            }
        )
        response.raise_for_status()
        return response.json()

    async def start_phase(self, project_id: str, phase: str) -> Dict[str, Any]:
        \"\"\"Start a RAPIDS phase for a project.\"\"\"
        response = await self.client.post(
            f"/api/projects/{project_id}/phases/{phase}/start"
        )
        response.raise_for_status()
        return response.json()

    async def get_features(self, project_id: str) -> list[Dict[str, Any]]:
        \"\"\"Get all features for a project.\"\"\"
        response = await self.client.get(f"/api/projects/{project_id}/features")
        response.raise_for_status()
        return response.json()

    async def close(self):
        \"\"\"Close the HTTP client.\"\"\"
        await self.client.aclose()


# Usage example
async def main():
    client = RAPIDSClient()

    try:
        # Create workspace
        workspace = await client.create_workspace(
            name="AI Research",
            description="Machine learning research projects"
        )
        print(f"Created workspace: {workspace['id']}")

        # Onboard project
        project = await client.onboard_project(
            workspace_id=workspace['id'],
            name="agent-memory",
            repo_path="/Users/dev/agent-memory",
            archetype="greenfield"
        )
        print(f"Onboarded project: {project['id']}")

        # Start planning phase
        await client.start_phase(project['id'], "plan")
        print("Started plan phase")

        # Get features
        features = await client.get_features(project['id'])
        print(f"Features: {len(features)}")

    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(main())
```

## JavaScript/TypeScript SDK

### Installation

```bash
npm install axios
```

### Basic Usage

```typescript
import axios, { AxiosInstance } from 'axios';

interface Workspace {
  id: string;
  name: string;
  description?: string;
  created_at: string;
  updated_at: string;
}

interface Project {
  id: string;
  name: string;
  workspace_id: string;
  repo_path: string;
  archetype: string;
  current_phase: string;
  repo_url?: string;
}

class RAPIDSClient {
  private client: AxiosInstance;

  constructor(baseURL: string = 'http://localhost:8000') {
    this.client = axios.create({ baseURL });
  }

  async createWorkspace(name: string, description?: string): Promise<Workspace> {
    const response = await this.client.post('/api/workspaces', {
      name,
      description
    });
    return response.data;
  }

  async onboardProject(
    workspaceId: string,
    name: string,
    repoPath: string,
    archetype: string = 'greenfield',
    repoUrl?: string
  ): Promise<Project> {
    const response = await this.client.post(
      `/api/workspaces/${workspaceId}/projects`,
      {
        name,
        repo_path: repoPath,
        archetype,
        repo_url: repoUrl
      }
    );
    return response.data;
  }

  async startPhase(projectId: string, phase: string): Promise<any> {
    const response = await this.client.post(
      `/api/projects/${projectId}/phases/${phase}/start`
    );
    return response.data;
  }

  async getFeatures(projectId: string): Promise<any[]> {
    const response = await this.client.get(
      `/api/projects/${projectId}/features`
    );
    return response.data;
  }
}

// Usage
const client = new RAPIDSClient();

async function main() {
  // Create workspace
  const workspace = await client.createWorkspace(
    'AI Research',
    'Machine learning research projects'
  );
  console.log(`Created workspace: ${workspace.id}`);

  // Onboard project
  const project = await client.onboardProject(
    workspace.id,
    'agent-memory',
    '/Users/dev/agent-memory',
    'greenfield'
  );
  console.log(`Onboarded project: ${project.id}`);

  // Start planning phase
  await client.startPhase(project.id, 'plan');
  console.log('Started plan phase');

  // Get features
  const features = await client.getFeatures(project.id);
  console.log(`Features: ${features.length}`);
}

main().catch(console.error);
```

## WebSocket Integration

### Python WebSocket Client

```python
import asyncio
import websockets
import json

async def listen_to_events():
    uri = "ws://localhost:8000/ws"
    async with websockets.connect(uri) as websocket:
        print("Connected to RAPIDS WebSocket")

        async for message in websocket:
            data = json.loads(message)
            event_type = data.get('type')

            if event_type == 'agent_created':
                print(f"New agent: {data['agent_id']}")
            elif event_type == 'feature_status_update':
                print(f"Feature {data['feature_id']}: {data['status']}")
            elif event_type == 'phase_transition':
                print(f"Phase changed to: {data['new_phase']}")

asyncio.run(listen_to_events())
```

## cURL Examples

### Create Workspace

```bash
curl -X POST http://localhost:8000/api/workspaces \\
  -H "Content-Type: application/json" \\
  -d '{
    "name": "AI Research",
    "description": "Machine learning projects"
  }'
```

### Onboard Project

```bash
curl -X POST http://localhost:8000/api/workspaces/ws_123/projects \\
  -H "Content-Type: application/json" \\
  -d '{
    "name": "agent-memory",
    "repo_path": "/Users/dev/agent-memory",
    "archetype": "greenfield"
  }'
```

### Start Phase

```bash
curl -X POST http://localhost:8000/api/projects/proj_456/phases/plan/start
```

### Get Features

```bash
curl http://localhost:8000/api/projects/proj_456/features
```
"""


# ═══════════════════════════════════════════════════════════
# RESPONSE EXAMPLES
# ═══════════════════════════════════════════════════════════

RESPONSE_EXAMPLES = {
    "workspace": {
        "id": "ws_9f8e7d6c5b4a",
        "name": "ML Research Projects",
        "description": "Workspace for machine learning research",
        "created_at": "2026-03-24T10:30:00Z",
        "updated_at": "2026-03-24T10:30:00Z"
    },
    "project": {
        "id": "proj_1a2b3c4d5e6f",
        "name": "agent-memory",
        "workspace_id": "ws_9f8e7d6c5b4a",
        "repo_path": "/Users/dev/projects/agent-memory",
        "archetype": "greenfield",
        "current_phase": "implement",
        "repo_url": "https://github.com/org/agent-memory"
    },
    "feature": {
        "id": "feat_auth_system",
        "project_id": "proj_1a2b3c4d5e6f",
        "name": "Authentication System",
        "description": "Implement JWT-based authentication",
        "status": "in_progress",
        "dependencies": ["feat_user_model"],
        "assigned_agent_id": "agent_7x8y9z"
    },
    "agent": {
        "id": "agent_7x8y9z",
        "name": "feature-builder-auth",
        "status": "active",
        "type": "feature-builder",
        "feature_id": "feat_auth_system",
        "created_at": "2026-03-24T10:35:00Z"
    }
}


def get_openapi_metadata() -> Dict[str, Any]:
    """Get OpenAPI metadata configuration."""
    return OPENAPI_METADATA


def get_openapi_tags() -> List[Dict[str, str]]:
    """Get OpenAPI tags for endpoint organization."""
    return OPENAPI_TAGS


def get_sdk_usage_guide() -> str:
    """Get SDK usage guide documentation."""
    return SDK_USAGE_GUIDE


def get_response_examples() -> Dict[str, Dict[str, Any]]:
    """Get response examples for documentation."""
    return RESPONSE_EXAMPLES
