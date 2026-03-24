# API Documentation Guide

## Overview

The RAPIDS Meta-Orchestrator API includes comprehensive OpenAPI/Swagger documentation with:

- **Swagger UI** at `/docs` - Interactive API explorer
- **ReDoc UI** at `/redoc` - Clean, responsive documentation
- **OpenAPI Schema** at `/openapi.json` - Machine-readable API specification
- **SDK Usage Guide** at `/api/sdk-usage` - Code examples for multiple languages
- **API Examples** at `/api/examples` - Sample responses for all endpoints

## Accessing the Documentation

### Swagger UI (`/docs`)

The interactive Swagger UI allows you to:
- Browse all available endpoints organized by tags
- View request/response schemas with examples
- Test API endpoints directly from the browser
- Download the OpenAPI specification

**Access:** `http://localhost:8000/docs`

### ReDoc UI (`/redoc`)

ReDoc provides a clean, three-panel documentation interface:
- Left panel: Navigation tree
- Center panel: Detailed endpoint documentation
- Right panel: Request/response examples

**Access:** `http://localhost:8000/redoc`

### OpenAPI JSON Schema

The raw OpenAPI 3.0 specification in JSON format:

**Access:** `http://localhost:8000/openapi.json`

## API Organization

### Tags

Endpoints are organized into the following categories:

#### Health
- `GET /health` - Basic health check
- `GET /health/live` - Liveness probe for Kubernetes
- `GET /health/ready` - Readiness probe with dependency checks

#### Orchestrator
- `GET /get_orchestrator` - Get orchestrator information
- `POST /load_chat` - Load chat history
- `POST /send_chat` - Send message to orchestrator

#### Workspaces
- `GET /api/workspaces` - List all workspaces
- `POST /api/workspaces` - Create a new workspace
- `GET /api/workspaces/{workspace_id}` - Get workspace details

#### Projects
- `GET /api/workspaces/{workspace_id}/projects` - List projects in workspace
- `POST /api/workspaces/{workspace_id}/projects` - Onboard a new project
- `GET /api/projects/{project_id}` - Get project details
- `POST /api/projects/{project_id}/switch` - Switch active project

#### Phases
- `GET /api/projects/{project_id}/phases` - Get all phase statuses
- `POST /api/projects/{project_id}/phases/{phase}/start` - Start a phase
- `POST /api/projects/{project_id}/phases/{phase}/complete` - Complete a phase
- `POST /api/projects/{project_id}/phases/advance` - Advance to next phase

#### Features
- `GET /api/projects/{project_id}/features` - List all features
- `POST /api/projects/{project_id}/features` - Create a new feature
- `GET /api/projects/{project_id}/dag` - Get feature dependency graph
- `POST /api/projects/{project_id}/dag/validate` - Validate feature DAG

#### Agents
- `GET /list_agents` - List all active agents

#### Plugins
- `GET /api/plugins` - List all available plugins
- `GET /api/plugins/{name}` - Get plugin details

#### Circuit Breakers
- `GET /api/circuit-breakers` - Get circuit breaker status

#### Utilities
- `GET /api/sdk-usage` - Get SDK usage guide
- `GET /api/examples` - Get API response examples

## SDK Usage Examples

### Python

Retrieve SDK examples:

```bash
curl http://localhost:8000/api/sdk-usage | jq -r '.content'
```

Or programmatically:

```python
import httpx

async with httpx.AsyncClient() as client:
    response = await client.get("http://localhost:8000/api/sdk-usage")
    guide = response.json()["content"]
    print(guide)
```

### Example Response

The SDK usage guide includes:
- Python SDK with `httpx`
- JavaScript/TypeScript SDK with `axios`
- WebSocket integration examples
- cURL examples for all major endpoints

## Request/Response Examples

### Get API Examples

```bash
curl http://localhost:8000/api/examples
```

**Response:**

```json
{
  "status": "success",
  "examples": {
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
      "current_phase": "implement"
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
}
```

## Pydantic Model Examples

All request models include:
- Field descriptions
- Example values
- Validation constraints
- Optional/required indicators

Example from CreateWorkspaceRequest:

```python
class CreateWorkspaceRequest(BaseModel):
    name: str = Field(
        ...,
        description="Human-readable workspace name",
        example="ML Research Projects",
        min_length=1,
        max_length=255
    )
    description: Optional[str] = Field(
        None,
        description="Optional description of workspace purpose",
        example="Workspace for machine learning research"
    )
```

## Response Schemas

All endpoints return structured responses with:
- `status` field indicating success/error
- Data payload in descriptive fields
- Consistent error format

### Success Response Example

```json
{
  "status": "success",
  "workspace": {
    "id": "ws_123",
    "name": "My Workspace",
    "created_at": "2026-03-24T10:00:00Z"
  }
}
```

### Error Response Example

```json
{
  "detail": "Workspace not found"
}
```

## OpenAPI Metadata

The API includes comprehensive metadata:

- **Title:** RAPIDS Meta-Orchestrator API
- **Version:** 1.0.0
- **Description:** Multi-project agentic workflow orchestration
- **Contact:** GitHub repository
- **License:** MIT

## Testing the Documentation

### Start the Backend

```bash
cd /path/to/agentic-meta-orchestrator
uv run python orchestrator/backend/main.py
```

### Access Documentation

1. **Swagger UI:** Open `http://localhost:8000/docs` in your browser
2. **ReDoc:** Open `http://localhost:8000/redoc` in your browser
3. **OpenAPI JSON:** `curl http://localhost:8000/openapi.json | jq .`

### Run Documentation Tests

```bash
uv run pytest orchestrator/backend/tests/test_api_documentation.py -v
```

## Extending the Documentation

### Adding Examples to New Endpoints

1. Import `Field` from pydantic:
   ```python
   from pydantic import BaseModel, Field
   ```

2. Add examples to model fields:
   ```python
   class MyRequest(BaseModel):
       name: str = Field(
           ...,
           description="Resource name",
           example="my-resource"
       )
   ```

3. Add tags and descriptions to endpoints:
   ```python
   @app.post(
       "/api/my-endpoint",
       tags=["MyTag"],
       summary="Short summary",
       description="Detailed description of what this endpoint does.",
   )
   async def my_endpoint(request: MyRequest):
       ...
   ```

### Adding New Tags

Edit `orchestrator/backend/modules/api_docs.py`:

```python
OPENAPI_TAGS = [
    # ... existing tags ...
    {
        "name": "NewTag",
        "description": "Description of this category of endpoints.",
    },
]
```

### Adding SDK Examples

Edit the `SDK_USAGE_GUIDE` string in `orchestrator/backend/modules/api_docs.py` to include new examples.

## Best Practices

1. **Always include examples** in Pydantic models
2. **Use descriptive tags** to group related endpoints
3. **Write clear descriptions** for both summaries and detailed descriptions
4. **Include response examples** in endpoint decorators
5. **Keep SDK guide updated** when adding new major features
6. **Test documentation** after making changes

## Troubleshooting

### Documentation not showing up

- Ensure the backend is running
- Check that `/docs` and `/redoc` URLs are correct
- Verify no firewall is blocking port 8000

### Missing examples in Swagger UI

- Check that Field examples are using valid syntax
- Verify Pydantic models are imported correctly
- Review deprecation warnings (use `json_schema_extra` for Pydantic v2)

### Tags not appearing

- Ensure tags are defined in `OPENAPI_TAGS`
- Verify endpoint decorators include the `tags` parameter
- Check that tag names match exactly (case-sensitive)

## Additional Resources

- [OpenAPI Specification](https://swagger.io/specification/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/tutorial/)
- [Pydantic Models](https://docs.pydantic.dev/)
- [Swagger UI](https://swagger.io/tools/swagger-ui/)
- [ReDoc](https://github.com/Redocly/redoc)
