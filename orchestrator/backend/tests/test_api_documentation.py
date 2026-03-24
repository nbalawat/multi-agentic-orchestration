#!/usr/bin/env python3
"""
Tests for API documentation feature.

Verifies that OpenAPI/Swagger documentation is properly configured
with comprehensive examples, tags, and SDK usage guides.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from main import app


class TestAPIDocumentation:
    """Test suite for API documentation endpoints."""

    @pytest.mark.asyncio
    async def test_openapi_schema_exists(self):
        """Test that OpenAPI schema is available at /openapi.json."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/openapi.json")
            assert response.status_code == 200
            schema = response.json()

            # Verify OpenAPI version
            assert "openapi" in schema
            assert schema["openapi"].startswith("3.")

            # Verify metadata
            assert "info" in schema
            info = schema["info"]
            assert info["title"] == "RAPIDS Meta-Orchestrator API"
            assert info["version"] == "1.0.0"
            assert "description" in info
            assert "RAPIDS Meta-Orchestrator" in info["description"]
            assert "contact" in info
            assert "license" in info

    @pytest.mark.asyncio
    async def test_docs_endpoint_accessible(self):
        """Test that /docs (Swagger UI) is accessible."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/docs")
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_redoc_endpoint_accessible(self):
        """Test that /redoc (ReDoc UI) is accessible."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/redoc")
            assert response.status_code == 200
            assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_openapi_tags_present(self):
        """Test that all expected tags are present in OpenAPI schema."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/openapi.json")
            schema = response.json()

            # Verify tags exist
            assert "tags" in schema
            tags = {tag["name"] for tag in schema["tags"]}

            # Expected tags
            expected_tags = {
                "Health",
                "Orchestrator",
                "Workspaces",
                "Projects",
                "Phases",
                "Features",
                "Agents",
                "Plugins",
                "Circuit Breakers",
                "Utilities",
            }

            # Check that all expected tags are present
            for expected_tag in expected_tags:
                assert expected_tag in tags, f"Tag '{expected_tag}' not found in schema"

    @pytest.mark.asyncio
    async def test_endpoint_has_tags(self):
        """Test that key endpoints have appropriate tags."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/openapi.json")
            schema = response.json()

            paths = schema["paths"]

            # Check health endpoint has Health tag
            assert "/health" in paths
            assert "get" in paths["/health"]
            assert "tags" in paths["/health"]["get"]
            assert "Health" in paths["/health"]["get"]["tags"]

            # Check workspaces endpoint has Workspaces tag
            assert "/api/workspaces" in paths
            assert "get" in paths["/api/workspaces"]
            assert "tags" in paths["/api/workspaces"]["get"]
            assert "Workspaces" in paths["/api/workspaces"]["get"]["tags"]

            # Check features endpoint has Features tag
            assert "/api/projects/{project_id}/features" in paths
            assert "get" in paths["/api/projects/{project_id}/features"]
            assert "tags" in paths["/api/projects/{project_id}/features"]["get"]
            assert "Features" in paths["/api/projects/{project_id}/features"]["get"]["tags"]

    @pytest.mark.asyncio
    async def test_pydantic_models_have_examples(self):
        """Test that Pydantic models include field examples."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/openapi.json")
            schema = response.json()

            components = schema.get("components", {})
            schemas = components.get("schemas", {})

            # Check CreateWorkspaceRequest has examples
            if "CreateWorkspaceRequest" in schemas:
                workspace_schema = schemas["CreateWorkspaceRequest"]
                properties = workspace_schema.get("properties", {})

                # Check name field has example
                if "name" in properties:
                    assert "example" in properties["name"] or "examples" in properties["name"]

            # Check CreateProjectRequest has examples
            if "CreateProjectRequest" in schemas:
                project_schema = schemas["CreateProjectRequest"]
                properties = project_schema.get("properties", {})

                # Check name field has example
                if "name" in properties:
                    assert "example" in properties["name"] or "examples" in properties["name"]

    @pytest.mark.asyncio
    async def test_sdk_usage_endpoint(self):
        """Test that SDK usage guide endpoint returns markdown content."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/sdk-usage")
            assert response.status_code == 200

            data = response.json()
            assert data["status"] == "success"
            assert "content" in data
            assert data["format"] == "markdown"

            # Verify content includes SDK examples
            content = data["content"]
            assert "Python" in content or "python" in content.lower()
            assert "JavaScript" in content or "TypeScript" in content
            assert "curl" in content.lower() or "cURL" in content
            assert "httpx" in content.lower() or "AsyncClient" in content
            assert "WebSocket" in content or "websocket" in content.lower()

    @pytest.mark.asyncio
    async def test_api_examples_endpoint(self):
        """Test that API examples endpoint returns example responses."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/examples")
            assert response.status_code == 200

            data = response.json()
            assert data["status"] == "success"
            assert "examples" in data

            examples = data["examples"]

            # Verify examples include key resource types
            assert "workspace" in examples
            assert "project" in examples
            assert "feature" in examples
            assert "agent" in examples

            # Verify workspace example has required fields
            workspace = examples["workspace"]
            assert "id" in workspace
            assert "name" in workspace
            assert "created_at" in workspace

    @pytest.mark.asyncio
    async def test_endpoint_descriptions(self):
        """Test that endpoints have comprehensive descriptions."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/openapi.json")
            schema = response.json()

            paths = schema["paths"]

            # Check that health endpoint has summary and description
            health_get = paths["/health"]["get"]
            assert "summary" in health_get
            assert "description" in health_get

            # Check that workspace list endpoint has summary and description
            if "/api/workspaces" in paths and "get" in paths["/api/workspaces"]:
                workspaces_get = paths["/api/workspaces"]["get"]
                assert "summary" in workspaces_get
                assert "description" in workspaces_get

    @pytest.mark.asyncio
    async def test_response_examples_in_schema(self):
        """Test that endpoints include response examples."""
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/openapi.json")
            schema = response.json()

            paths = schema["paths"]

            # Check health endpoint has response examples
            if "/health" in paths and "get" in paths["/health"]:
                health_get = paths["/health"]["get"]
                if "responses" in health_get and "200" in health_get["responses"]:
                    response_200 = health_get["responses"]["200"]
                    # At minimum, should have description
                    assert "description" in response_200


class TestAPIDocumentationModule:
    """Test suite for api_docs module functions."""

    def test_get_openapi_metadata(self):
        """Test that get_openapi_metadata returns correct structure."""
        from modules.api_docs import get_openapi_metadata

        metadata = get_openapi_metadata()

        assert "title" in metadata
        assert "version" in metadata
        assert "description" in metadata
        assert "contact" in metadata
        assert "license_info" in metadata

        assert metadata["title"] == "RAPIDS Meta-Orchestrator API"
        assert metadata["version"] == "1.0.0"

    def test_get_openapi_tags(self):
        """Test that get_openapi_tags returns all expected tags."""
        from modules.api_docs import get_openapi_tags

        tags = get_openapi_tags()

        assert isinstance(tags, list)
        assert len(tags) > 0

        tag_names = {tag["name"] for tag in tags}
        expected_tags = {
            "Health",
            "Orchestrator",
            "Workspaces",
            "Projects",
            "Phases",
            "Features",
            "Agents",
            "Plugins",
        }

        for expected in expected_tags:
            assert expected in tag_names

    def test_get_sdk_usage_guide(self):
        """Test that get_sdk_usage_guide returns markdown content."""
        from modules.api_docs import get_sdk_usage_guide

        guide = get_sdk_usage_guide()

        assert isinstance(guide, str)
        assert len(guide) > 0
        assert "Python" in guide or "python" in guide.lower()
        assert "JavaScript" in guide or "TypeScript" in guide
        assert "curl" in guide.lower()

    def test_get_response_examples(self):
        """Test that get_response_examples returns example data."""
        from modules.api_docs import get_response_examples

        examples = get_response_examples()

        assert isinstance(examples, dict)
        assert "workspace" in examples
        assert "project" in examples
        assert "feature" in examples
        assert "agent" in examples


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
