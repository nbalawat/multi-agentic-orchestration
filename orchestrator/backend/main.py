#!/usr/bin/env python3
"""
Orchestrator 3 Stream Backend
FastAPI server for managing orchestrator agent workflows with PostgreSQL backend
"""

import asyncio
import argparse
import os
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from pathlib import Path
import json
import time

from rich.table import Table
from rich.console import Console

# Import our custom modules
from modules import config
from modules.logger import get_logger
from modules.websocket_manager import get_websocket_manager
from modules import database
from modules.error_types import ErrorCode, ErrorResponse
from modules.orchestrator_service import OrchestratorService, get_orchestrator_tools
from modules.agent_manager import AgentManager
from modules.orch_database_models import OrchestratorAgent
from modules.rapids_database import (
    create_workspace as db_create_workspace,
    get_workspace as db_get_workspace,
    list_workspaces as db_list_workspaces,
    create_project as db_create_project,
    get_project as db_get_project,
    list_projects as db_list_projects,
    update_project_phase as db_update_project_phase,
    list_project_phases as db_list_project_phases,
    create_feature as db_create_feature,
    list_features as db_list_features,
    update_feature_status as db_update_feature_status,
    init_project_phases as db_init_project_phases,
)
from modules.workspace_manager import WorkspaceManager
from modules.plugin_loader import PluginLoader
from modules.feature_dag import FeatureDAG
from modules.project_state import ProjectState
from modules.phase_engine import PhaseEngine

logger = get_logger()
ws_manager = get_websocket_manager()
console = Console()  # For startup table display only

# Parse CLI arguments before creating app
parser = argparse.ArgumentParser(description="Orchestrator 3 Stream Backend")
parser.add_argument(
    "--session", type=str, help="Resume existing orchestrator session (session ID)"
)
parser.add_argument(
    "--cwd", type=str, help="Set working directory for orchestrator and agents"
)
args, unknown = parser.parse_known_args()

# Store parsed args for lifespan
CLI_SESSION_ID = args.session
CLI_WORKING_DIR = args.cwd

# Set working directory (use CLI arg or default from config)
if CLI_WORKING_DIR:
    config.set_working_dir(CLI_WORKING_DIR)
else:
    # Use default from ORCHESTRATOR_WORKING_DIR env var or config
    logger.info(f"Using default working directory: {config.get_working_dir()}")


# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events"""
    # Startup
    logger.startup(
        {
            "Service": "Orchestrator 3 Stream Backend",
            "Description": "PostgreSQL-backed multi-agent orchestration",
            "Backend URL": config.BACKEND_URL,
            "WebSocket URL": config.WEBSOCKET_URL,
            "Database": "PostgreSQL (NeonDB)",
            "Logs Directory": str(config.LOG_DIR),
            "Working Directory": config.get_working_dir(),
        }
    )

    # Initialize database connection pool
    logger.info("Initializing database connection pool...")
    await database.init_pool(database_url=config.DATABASE_URL)
    logger.success("Database connection pool initialized")

    # Validate or load orchestrator
    if CLI_SESSION_ID:
        logger.info(f"Looking up orchestrator with session: {CLI_SESSION_ID}")
        orchestrator_data = await database.get_orchestrator_by_session(CLI_SESSION_ID)

        if not orchestrator_data:
            logger.error(f"❌ Session ID not found: {CLI_SESSION_ID}")
            logger.info("Checking if this is a legacy session or orchestrator ID...")

            # Try to find any orchestrator for debugging
            all_orchestrators = await database.get_orchestrator()
            if all_orchestrators:
                logger.info(f"Found orchestrator in database:")
                logger.info(f"  ID: {all_orchestrators.get('id')}")
                logger.info(f"  Session ID: {all_orchestrators.get('session_id')}")
                logger.info(f"\nTo resume, use: --session {all_orchestrators.get('session_id')}")

            raise ValueError(
                f"Session ID '{CLI_SESSION_ID}' not found in orchestrator_agents.session_id.\n\n"
                f"This usually happens when:\n"
                f"  1. The session_id has not been set yet (run without --session first)\n"
                f"  2. Database tables were recreated (data loss)\n"
                f"  3. Session ID was mistyped\n\n"
                f"Solution: Remove the --session argument to start a fresh session."
            )

        # Parse to Pydantic model
        orchestrator = OrchestratorAgent(**orchestrator_data)
        logger.success(f"✅ Resumed orchestrator with session: {CLI_SESSION_ID}")
        logger.info(f"  Orchestrator ID: {orchestrator.id}")
        logger.info(
            f"  Total tokens: {orchestrator.input_tokens + orchestrator.output_tokens}"
        )
        logger.info(f"  Total cost: ${orchestrator.total_cost:.4f}")
    else:
        # No --session provided: Always create new orchestrator
        logger.info("Creating new orchestrator session...")

        # Read system prompt from file
        system_prompt_content = Path(config.ORCHESTRATOR_SYSTEM_PROMPT_PATH).read_text()

        orchestrator_data = await database.create_new_orchestrator(
            system_prompt=system_prompt_content,
            working_dir=config.get_working_dir(),
        )
        # Parse to Pydantic model
        orchestrator = OrchestratorAgent(**orchestrator_data)
        logger.success(f"✅ New orchestrator created: {orchestrator.id}")
        logger.info(f"  Session ID: {orchestrator.session_id or 'Not set yet (will be set after first interaction)'}")
        logger.info(f"  Status: {orchestrator.status}")

    # Initialize agent manager (scoped to this orchestrator)
    logger.info("Initializing agent manager...")
    agent_manager = AgentManager(
        orchestrator_agent_id=orchestrator.id,
        ws_manager=ws_manager,
        logger=logger,
        working_dir=config.get_working_dir()
    )
    logger.success(f"Agent manager initialized for orchestrator {orchestrator.id}")

    # Initialize orchestrator service with agent manager
    logger.info("Initializing orchestrator service...")
    orchestrator_service = OrchestratorService(
        ws_manager=ws_manager,
        logger=logger,
        agent_manager=agent_manager,
        session_id=CLI_SESSION_ID or orchestrator.session_id,
        working_dir=config.get_working_dir(),
    )

    # Store in app state for access in endpoints
    app.state.orchestrator_service = orchestrator_service
    app.state.orchestrator = orchestrator
    app.state.agent_manager = agent_manager

    # Initialize RAPIDS workspace/plugin infrastructure
    logger.info("Initializing PluginLoader and WorkspaceManager...")
    plugins_dir = Path(config.get_working_dir()) / ".claude" / "rapids-plugins"
    plugin_loader = PluginLoader(plugins_dir=plugins_dir)
    plugin_loader.discover_plugins()
    workspace_manager = WorkspaceManager(plugin_loader=plugin_loader)
    app.state.plugin_loader = plugin_loader
    app.state.workspace_manager = workspace_manager
    logger.success("PluginLoader and WorkspaceManager initialized")

    # Wire workspace/plugin context into orchestrator service for system prompt injection
    orchestrator_service.workspace_manager = workspace_manager
    orchestrator_service.plugin_loader = plugin_loader
    logger.info("Wired workspace_manager + plugin_loader into OrchestratorService for context injection")

    # Also wire into agent_manager for phase-aware agent creation
    agent_manager.workspace_manager = workspace_manager
    agent_manager.plugin_loader = plugin_loader
    logger.info("Wired workspace_manager + plugin_loader into AgentManager")

    logger.success("Backend initialization complete")

    yield  # Server runs

    # Shutdown
    logger.info("Closing database connection pool...")
    await database.close_pool()
    logger.shutdown()


# Create FastAPI app with lifespan
app = FastAPI(title="Orchestrator 3 Stream API", version="1.0.0", lifespan=lifespan)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,  # From .env configuration
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════
# REQUEST ID MIDDLEWARE
# ═══════════════════════════════════════════════════════════


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """
    Attach a unique request ID to every HTTP request.

    Reads X-Request-ID from incoming headers if provided (allows client-side
    tracing), otherwise generates a new UUID.  The request_id is stored in
    request.state so route handlers can reference it, and echoed back in the
    X-Request-ID response header.
    """
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ═══════════════════════════════════════════════════════════
# GLOBAL EXCEPTION HANDLERS
# ═══════════════════════════════════════════════════════════


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Return standardized error response format for all HTTP exceptions.

    Converts FastAPI HTTPException to our ErrorResponse model so all
    error responses share the same structure (status, error.code,
    error.message, request_id).
    """
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))

    # Map HTTP status codes to error codes
    status_to_code = {
        400: ErrorCode.VALIDATION_ERROR,
        401: ErrorCode.UNAUTHORIZED,
        403: ErrorCode.FORBIDDEN,
        404: ErrorCode.NOT_FOUND,
        500: ErrorCode.INTERNAL_ERROR,
    }
    error_code = status_to_code.get(exc.status_code, ErrorCode.INTERNAL_ERROR)

    error_response = ErrorResponse.create(
        code=error_code,
        message=str(exc.detail),
        request_id=request_id,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response.model_dump(),
        headers={"X-Request-ID": request_id},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Catch-all handler for unhandled exceptions.

    Logs the full traceback and returns a sanitized 500 error response
    that does not leak internal details to clients.
    """
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    logger.error(
        f"Unhandled exception on {request.method} {request.url.path} "
        f"[request_id={request_id}]: {type(exc).__name__}: {exc}"
    )

    error_response = ErrorResponse.create(
        code=ErrorCode.INTERNAL_ERROR,
        message="An unexpected error occurred. Please try again or contact support.",
        request_id=request_id,
        details={"error_type": type(exc).__name__},
    )
    return JSONResponse(
        status_code=500,
        content=error_response.model_dump(),
        headers={"X-Request-ID": request_id},
    )


# ═══════════════════════════════════════════════════════════
# REQUEST/RESPONSE MODELS
# ═══════════════════════════════════════════════════════════


class LoadChatRequest(BaseModel):
    """Request model for loading chat history"""

    orchestrator_agent_id: str
    limit: Optional[int] = 50


class SendChatRequest(BaseModel):
    """Request model for sending chat message"""

    message: str
    orchestrator_agent_id: str


# ═══════════════════════════════════════════════════════════
# API ROUTES
# ═══════════════════════════════════════════════════════════


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    logger.http_request("GET", "/health", 200)
    return {
        "status": "healthy",
        "service": "orchestrator-3-stream",
        "websocket_connections": ws_manager.get_connection_count(),
    }


@app.get("/api/circuit-breakers")
async def get_circuit_breaker_status():
    """
    Get the current status of all registered circuit breakers.

    Returns state, failure counts, and timing information for each
    circuit breaker in the system. Useful for operational monitoring.
    """
    from modules.circuit_breaker import get_circuit_breaker_registry
    registry = get_circuit_breaker_registry()
    statuses = registry.get_all_status()
    return {
        "status": "success",
        "circuit_breakers": statuses,
    }


@app.get("/api/active-context")
async def get_active_context():
    """Get the active workspace, project, and phase context."""
    try:
        wm: WorkspaceManager = app.state.workspace_manager
        result = {
            "workspace": None,
            "project": None,
            "phase": None,
        }

        if wm._active_workspace_id:
            result["workspace"] = {
                "id": str(wm._active_workspace_id),
            }

        if wm._active_project_id:
            ctx = wm._project_contexts.get(wm._active_project_id, {})
            result["project"] = {
                "id": str(wm._active_project_id),
                "name": ctx.get("name", "unknown"),
                "repo_path": ctx.get("repo_path", ""),
                "archetype": ctx.get("archetype", ""),
            }

            # Get phase info from .rapids/state.json
            repo_path = ctx.get("repo_path", "")
            if repo_path:
                try:
                    from modules.project_state import ProjectState
                    ps = ProjectState(repo_path)
                    state = ps.load_state()
                    current_phase = state.get("current_phase", "not_started")
                    phases = state.get("phases", {})
                    result["phase"] = {
                        "current": current_phase,
                        "status": phases.get(current_phase, {}).get("status", "unknown"),
                        "all_phases": {p: info.get("status", "not_started") for p, info in phases.items()},
                    }
                except Exception:
                    pass

        return {"status": "success", **result}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.get("/get_orchestrator")
async def get_orchestrator_info():
    """
    Get orchestrator agent information including system metadata.

    Fetches fresh data from database to ensure session_id is always current.
    Returns orchestrator ID, session, costs, metadata, slash commands, and templates.
    """
    try:
        logger.http_request("GET", "/get_orchestrator")

        # Refresh orchestrator from database to get current session_id
        orchestrator_id = app.state.orchestrator.id
        orchestrator_data = await database.get_orchestrator_by_id(orchestrator_id)

        if not orchestrator_data:
            logger.error(f"Orchestrator not found in database: {orchestrator_id}")
            raise HTTPException(status_code=404, detail="Orchestrator not found")

        # Update app.state with fresh data (keeps in-memory cache synchronized)
        orchestrator = OrchestratorAgent(**orchestrator_data)
        app.state.orchestrator = orchestrator

        # Discover slash commands
        slash_commands = discover_slash_commands(config.get_working_dir())

        # Get agent templates from SubagentRegistry
        from modules.subagent_loader import SubagentRegistry
        registry = SubagentRegistry(config.get_working_dir(), logger)
        templates = registry.list_templates()

        # Get orchestrator tools
        orchestrator_tools = get_orchestrator_tools()

        # Prepare metadata with fallback for system_message_info
        metadata = orchestrator.metadata or {}

        # If system_message_info doesn't exist, create fallback from current state
        if not metadata.get("system_message_info"):
            metadata["system_message_info"] = {
                "session_id": orchestrator.session_id,
                "cwd": orchestrator.working_dir or config.get_working_dir(),
                "captured_at": None,  # Indicates this is fallback data
                "subtype": "fallback"  # Indicates this wasn't from a SystemMessage
            }

        logger.http_request("GET", "/get_orchestrator", 200)
        return {
            "status": "success",
            "orchestrator": {
                "id": str(orchestrator.id),
                "session_id": orchestrator.session_id,
                "status": orchestrator.status,
                "working_dir": orchestrator.working_dir,
                "input_tokens": orchestrator.input_tokens,
                "output_tokens": orchestrator.output_tokens,
                "total_cost": float(orchestrator.total_cost),
                "metadata": metadata,  # Include metadata with fallback
            },
            "slash_commands": slash_commands,  # List of available commands
            "agent_templates": templates,      # List of available templates
            "orchestrator_tools": orchestrator_tools,  # NEW: List of management tools
        }
    except Exception as e:
        logger.error(f"Failed to get orchestrator info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get_headers")
async def get_headers():
    """
    Get header information for the frontend including active project context.
    """
    try:
        logger.http_request("GET", "/get_headers")

        cwd = config.get_working_dir()

        # Get active project context from workspace manager
        active_project = None
        active_workspace = None
        wm: WorkspaceManager = app.state.workspace_manager
        if wm:
            project_id = wm.get_active_project_id()
            workspace_id = wm.get_active_workspace_id()
            if project_id:
                try:
                    proj = await wm.get_active_project()
                    if proj:
                        # Convert to dict if needed
                        if hasattr(proj, "model_dump"):
                            proj = proj.model_dump()
                        elif hasattr(proj, "dict"):
                            proj = proj.dict()
                        active_project = {
                            "id": proj.get("id", project_id),
                            "name": proj.get("name", "unknown"),
                            "current_phase": proj.get("current_phase", "unknown"),
                            "archetype": proj.get("archetype", ""),
                            "repo_path": proj.get("repo_path", ""),
                            "status": proj.get("status", "active"),
                        }
                except Exception:
                    pass
            if workspace_id:
                try:
                    from modules.rapids_database import get_workspace
                    ws = await get_workspace(workspace_id)
                    if ws:
                        if hasattr(ws, "model_dump"):
                            ws = ws.model_dump()
                        elif hasattr(ws, "dict"):
                            ws = ws.dict()
                        elif not isinstance(ws, dict):
                            ws = dict(ws)
                        active_workspace = {
                            "id": ws.get("id", workspace_id),
                            "name": ws.get("name", "unknown"),
                        }
                except Exception:
                    pass

        logger.http_request("GET", "/get_headers", 200)
        return {
            "status": "success",
            "cwd": cwd,
            "active_project": active_project,
            "active_workspace": active_workspace,
        }
    except Exception as e:
        logger.error(f"Failed to get headers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/project_dashboard")
async def get_project_dashboard():
    """
    Get a dashboard view of all workspaces, projects, and their current phases.
    Used by the frontend to show project context at a glance.
    """
    try:
        logger.http_request("GET", "/api/project_dashboard")

        wm: WorkspaceManager = app.state.workspace_manager
        active_project_id = wm.get_active_project_id() if wm else None

        # Get all workspaces
        from modules.rapids_database import list_workspaces as db_list_workspaces
        workspaces = await db_list_workspaces()

        dashboard = []
        for ws in workspaces:
            if hasattr(ws, "model_dump"):
                ws = ws.model_dump()
            elif hasattr(ws, "dict"):
                ws = ws.dict()
            elif not isinstance(ws, dict):
                ws = dict(ws)

            ws_id = str(ws.get("id", ""))
            from modules.rapids_database import list_projects as db_list_projects_by_ws
            projects = await db_list_projects_by_ws(uuid.UUID(ws_id))

            project_list = []
            for p in projects:
                if hasattr(p, "model_dump"):
                    p = p.model_dump()
                elif hasattr(p, "dict"):
                    p = p.dict()
                elif not isinstance(p, dict):
                    p = dict(p)

                pid = str(p.get("id", ""))
                project_list.append({
                    "id": pid,
                    "name": p.get("name", "unknown"),
                    "current_phase": p.get("current_phase", "research"),
                    "archetype": p.get("archetype", ""),
                    "status": p.get("status", "active"),
                    "is_active": pid == str(active_project_id) if active_project_id else False,
                })

            dashboard.append({
                "id": ws_id,
                "name": ws.get("name", "unknown"),
                "projects": project_list,
            })

        logger.http_request("GET", "/api/project_dashboard", 200)
        return {"status": "success", "dashboard": dashboard}
    except Exception as e:
        logger.error(f"Failed to get project dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
# SLASH COMMAND DISCOVERY
# ═══════════════════════════════════════════════════════════

# Import slash command discovery from parser module
from modules.slash_command_parser import discover_slash_commands


class OpenFileRequest(BaseModel):
    """Request model for opening a file in IDE"""
    file_path: str


@app.post("/api/open-file")
async def open_file_in_ide(request: OpenFileRequest):
    """
    Open a file in the configured IDE (Cursor or VS Code).

    Opens the file using the IDE command specified in config.IDE_COMMAND.
    """
    try:
        import subprocess

        logger.http_request("POST", "/api/open-file")

        if not config.IDE_ENABLED:
            logger.http_request("POST", "/api/open-file", 403)
            return {
                "status": "error",
                "message": "IDE integration is disabled in configuration"
            }

        file_path = request.file_path

        # Validate file exists
        if not os.path.exists(file_path):
            logger.http_request("POST", "/api/open-file", 404)
            return {"status": "error", "message": f"File not found: {file_path}"}

        # Build IDE command
        ide_cmd = config.IDE_COMMAND
        full_command = [ide_cmd, file_path]

        logger.info(f"Opening file in {ide_cmd}: {file_path}")

        # Execute IDE command
        result = subprocess.run(
            full_command,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            logger.http_request("POST", "/api/open-file", 200)
            return {
                "status": "success",
                "message": f"Opened {file_path} in {ide_cmd}",
                "file_path": file_path
            }
        else:
            logger.error(f"Failed to open file in IDE: {result.stderr}")
            logger.http_request("POST", "/api/open-file", 500)
            return {
                "status": "error",
                "message": f"Failed to open file in IDE: {result.stderr}"
            }

    except subprocess.TimeoutExpired:
        logger.error("IDE command timed out")
        logger.http_request("POST", "/api/open-file", 500)
        return {"status": "error", "message": "IDE command timed out"}
    except FileNotFoundError:
        logger.error(f"IDE command not found: {config.IDE_COMMAND}")
        logger.http_request("POST", "/api/open-file", 500)
        return {
            "status": "error",
            "message": f"IDE command not found: {config.IDE_COMMAND}. Please ensure it's installed and in PATH."
        }
    except Exception as e:
        logger.error(f"Failed to open file in IDE: {e}")
        logger.http_request("POST", "/api/open-file", 500)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/load_chat")
async def load_chat(request: LoadChatRequest):
    """
    Load chat history for orchestrator agent.

    Returns:
        - messages: List of chat messages
        - turn_count: Total number of messages
    """
    try:
        logger.http_request("POST", "/load_chat")

        service: OrchestratorService = app.state.orchestrator_service
        result = await service.load_chat_history(
            orchestrator_agent_id=request.orchestrator_agent_id, limit=request.limit
        )

        logger.http_request("POST", "/load_chat", 200)
        return {
            "status": "success",
            "messages": result["messages"],
            "turn_count": result["turn_count"],
        }

    except Exception as e:
        logger.error(f"Failed to load chat history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/send_chat")
async def send_chat(request: SendChatRequest):
    """
    Send message to orchestrator agent.

    Message is processed with streaming via WebSocket.
    This endpoint returns immediately after starting execution.

    Returns:
        - status: success/error
        - message: Confirmation message
    """
    try:
        logger.http_request("POST", "/send_chat")

        service: OrchestratorService = app.state.orchestrator_service

        # Process message asynchronously (streaming via WebSocket)
        asyncio.create_task(
            service.process_user_message(
                user_message=request.message,
                orchestrator_agent_id=request.orchestrator_agent_id,
            )
        )

        logger.http_request("POST", "/send_chat", 200)
        return {
            "status": "success",
            "message": "Message received, processing with streaming",
        }

    except Exception as e:
        logger.error(f"Failed to send chat message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get_events")
async def get_events_endpoint(
    agent_id: Optional[str] = None,
    task_slug: Optional[str] = None,
    event_types: str = "all",
    limit: int = 50,
    offset: int = 0,
):
    """
    Get events from all sources for EventStream component.

    Query params:
        - agent_id: Optional filter by agent UUID
        - task_slug: Optional filter by task
        - event_types: Comma-separated list or "all" (default: "all")
        - limit: Max events to return (default 50)
        - offset: Pagination offset (default 0)

    Returns:
        - status: success/error
        - events: List of unified events with sourceType field
        - count: Total event count
    """
    try:
        logger.http_request("GET", "/get_events")

        # Parse event types (default: agent_logs and orchestrator_chat only, no system_logs)
        requested_types = (
            event_types.split(",")
            if event_types != "all"
            else ["agent_logs", "orchestrator_chat"]
        )

        all_events = []

        # Fetch agent logs
        if "agent_logs" in requested_types:
            agent_uuid = uuid.UUID(agent_id) if agent_id else None
            if agent_uuid:
                agent_logs = await database.get_agent_logs(
                    agent_id=agent_uuid, task_slug=task_slug, limit=limit, offset=offset
                )
            else:
                agent_logs = await database.list_agent_logs(
                    orchestrator_agent_id=app.state.orchestrator.id,
                    limit=limit,
                    offset=offset
                )

            # Add sourceType field
            for log in agent_logs:
                log["sourceType"] = "agent_log"
                all_events.append(log)

        # Fetch system logs
        if "system_logs" in requested_types:
            system_logs = await database.list_system_logs(limit=limit, offset=offset)
            for log in system_logs:
                log["sourceType"] = "system_log"
                all_events.append(log)

        # Fetch orchestrator chat (filtered by current orchestrator)
        if "orchestrator_chat" in requested_types:
            chat_logs = await database.list_orchestrator_chat(
                orchestrator_agent_id=app.state.orchestrator.id,
                limit=limit,
                offset=offset
            )
            for log in chat_logs:
                log["sourceType"] = "orchestrator_chat"
                all_events.append(log)

        # Sort by timestamp (newest first for limiting)
        all_events.sort(
            key=lambda x: x.get("timestamp") or x.get("created_at"), reverse=True
        )

        # Apply limit to get most recent events
        all_events = all_events[:limit]

        # Reverse to show oldest at top, newest at bottom
        all_events.reverse()

        # Convert UUIDs and datetimes to strings for JSON
        for event in all_events:
            for key, value in list(event.items()):
                if isinstance(value, uuid.UUID):
                    event[key] = str(value)
                elif hasattr(value, "isoformat"):
                    event[key] = value.isoformat()

        logger.http_request("GET", "/get_events", 200)
        return {"status": "success", "events": all_events, "count": len(all_events)}

    except Exception as e:
        logger.error(f"Failed to get events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/list_agents")
async def list_agents_endpoint():
    """
    List all active agents for sidebar display.

    Returns:
        - status: success/error
        - agents: List of agent objects enriched with log_count from agent_logs table
    """
    try:
        logger.http_request("GET", "/list_agents")

        agents = await database.list_agents(
            orchestrator_agent_id=app.state.orchestrator.id,
            archived=False
        )

        # Serialize Pydantic models to dicts
        agents_data = [agent.model_dump() for agent in agents]

        # Enrich each agent with log count from agent_logs table
        async with database.get_connection() as conn:
            for agent_data in agents_data:
                agent_id = agent_data["id"]

                # Count logs for this agent from agent_logs table
                log_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM agent_logs WHERE agent_id = $1", agent_id
                )
                agent_data["log_count"] = log_count or 0

        logger.http_request("GET", "/list_agents", 200)
        return {"status": "success", "agents": agents_data}

    except Exception as e:
        logger.error(f"Failed to list agents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates and chat messages"""

    await ws_manager.connect(websocket)

    try:
        while True:
            # Keep connection alive and receive any client messages
            data = await websocket.receive_text()

            # Log received message
            if data:
                logger.debug(f"📥 Received WebSocket message: {data[:100]}")

                # Try to parse as JSON for structured messages
                try:
                    message = json.loads(data)

                    # Route message based on type
                    if isinstance(message, dict) and "type" in message:
                        msg_type = message.get("type")

                        if msg_type == "ping":
                            # Respond with pong for client-initiated pings
                            await websocket.send_json({
                                "type": "pong",
                                "timestamp": message.get("timestamp"),
                                "server_timestamp": datetime.now().isoformat(),
                            })
                            logger.debug("Sent pong in response to client ping")

                        elif msg_type == "pong":
                            # Client responded to our server-initiated ping
                            await ws_manager.handle_pong(websocket)

                        else:
                            # Log other message types for future event handlers
                            logger.debug(f"Received WebSocket message type: {msg_type}")

                except json.JSONDecodeError:
                    # Not JSON, treat as plain text (keep alive ping)
                    pass

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


# ═══════════════════════════════════════════════════════════
# RAPIDS REQUEST/RESPONSE MODELS
# ═══════════════════════════════════════════════════════════


class CreateWorkspaceRequest(BaseModel):
    """Request model for creating a workspace."""
    name: str
    description: Optional[str] = None


class CreateProjectRequest(BaseModel):
    """Request model for onboarding a project."""
    name: str
    repo_path: str
    archetype: str
    repo_url: Optional[str] = None
    plugin_id: Optional[str] = None


class CreateFeatureRequest(BaseModel):
    """Request model for creating a feature."""
    name: str
    description: Optional[str] = None
    depends_on: Optional[List[str]] = None
    acceptance_criteria: Optional[List[str]] = None
    priority: Optional[int] = 0
    estimated_complexity: Optional[str] = None
    spec_file: Optional[str] = None


class UpdateFeatureStatusRequest(BaseModel):
    """Request model for updating a feature's status."""
    status: str
    assigned_agent_id: Optional[str] = None


class PhaseActionRequest(BaseModel):
    """Request model for phase actions (start/complete)."""
    force: Optional[bool] = False


# ═══════════════════════════════════════════════════════════
# RAPIDS WORKSPACE ENDPOINTS
# ═══════════════════════════════════════════════════════════


@app.get("/api/workspaces")
async def list_workspaces():
    """List all workspaces."""
    try:
        logger.http_request("GET", "/api/workspaces")
        workspaces = await db_list_workspaces()
        logger.http_request("GET", "/api/workspaces", 200)
        return {
            "status": "success",
            "workspaces": [w.model_dump(mode="json") for w in workspaces],
        }
    except Exception as e:
        logger.error(f"Failed to list workspaces: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/workspaces", status_code=201)
async def create_workspace(request: CreateWorkspaceRequest):
    """Create a new workspace."""
    try:
        logger.http_request("POST", "/api/workspaces")
        workspace = await db_create_workspace(
            name=request.name,
            description=request.description,
        )
        logger.http_request("POST", "/api/workspaces", 201)
        return {
            "status": "success",
            "workspace": workspace.model_dump(mode="json"),
        }
    except Exception as e:
        logger.error(f"Failed to create workspace: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/workspaces/{workspace_id}")
async def get_workspace(workspace_id: str):
    """Get workspace details."""
    try:
        logger.http_request("GET", f"/api/workspaces/{workspace_id}")
        workspace = await db_get_workspace(uuid.UUID(workspace_id))
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        logger.http_request("GET", f"/api/workspaces/{workspace_id}", 200)
        return {
            "status": "success",
            "workspace": workspace.model_dump(mode="json"),
        }
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workspace ID format")
    except Exception as e:
        logger.error(f"Failed to get workspace: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
# RAPIDS PROJECT ENDPOINTS
# ═══════════════════════════════════════════════════════════


@app.get("/api/workspaces/{workspace_id}/projects")
async def list_projects_in_workspace(workspace_id: str):
    """List all projects in a workspace."""
    try:
        logger.http_request("GET", f"/api/workspaces/{workspace_id}/projects")
        projects = await db_list_projects(uuid.UUID(workspace_id))
        logger.http_request("GET", f"/api/workspaces/{workspace_id}/projects", 200)
        return {
            "status": "success",
            "projects": [p.model_dump(mode="json") for p in projects],
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workspace ID format")
    except Exception as e:
        logger.error(f"Failed to list projects: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/workspaces/{workspace_id}/projects", status_code=201)
async def onboard_project(workspace_id: str, request: CreateProjectRequest):
    """Onboard a new project into a workspace."""
    try:
        logger.http_request("POST", f"/api/workspaces/{workspace_id}/projects")
        ws_id = uuid.UUID(workspace_id)

        # Verify workspace exists
        workspace = await db_get_workspace(ws_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found")

        # Create the project
        project = await db_create_project(
            workspace_id=ws_id,
            name=request.name,
            repo_path=request.repo_path,
            archetype=request.archetype,
            repo_url=request.repo_url,
            plugin_id=request.plugin_id,
        )

        # Initialize all 6 RAPIDS phases
        phases = await db_init_project_phases(project.id)

        # Initialize .rapids/ directory in the project repo
        try:
            project_state = ProjectState(
                repo_path=request.repo_path,
                project_id=str(project.id),
                archetype=request.archetype,
                plugin=request.plugin_id or request.archetype,
            )
            project_state.init_rapids_dir()
        except Exception as init_err:
            logger.warning(f"Failed to initialize .rapids/ directory: {init_err}")

        logger.http_request("POST", f"/api/workspaces/{workspace_id}/projects", 201)
        return {
            "status": "success",
            "project": project.model_dump(mode="json"),
            "phases_initialized": len(phases),
        }
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to onboard project: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/projects/{project_id}")
async def get_project(project_id: str):
    """Get project details."""
    try:
        logger.http_request("GET", f"/api/projects/{project_id}")
        project = await db_get_project(uuid.UUID(project_id))
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        logger.http_request("GET", f"/api/projects/{project_id}", 200)
        return {
            "status": "success",
            "project": project.model_dump(mode="json"),
        }
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID format")
    except Exception as e:
        logger.error(f"Failed to get project: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/projects/{project_id}/switch")
async def switch_project_context(project_id: str):
    """Switch active project context."""
    try:
        logger.http_request("POST", f"/api/projects/{project_id}/switch")
        wm: WorkspaceManager = app.state.workspace_manager
        project = await wm.switch_project(project_id)
        logger.http_request("POST", f"/api/projects/{project_id}/switch", 200)
        return {
            "status": "success",
            "message": f"Switched to project: {project.get('name', project_id)}",
            "project": project,
        }
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to switch project context: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
# RAPIDS PHASE ENDPOINTS
# ═══════════════════════════════════════════════════════════


@app.post("/api/answer_question")
async def answer_question(request: Request):
    """
    Receive user answers to AskUserQuestion from the frontend.
    Routes answers to the correct agent or orchestrator to unblock the pending question.
    If agent_id is provided, routes to that specific agent.
    Otherwise, routes to the orchestrator.
    """
    try:
        body = await request.json()
        answers = body.get("answers", {})
        agent_id = body.get("agent_id")
        logger.http_request("POST", "/api/answer_question")

        if agent_id:
            # Route to specific agent
            agent_mgr = app.state.agent_manager
            if agent_mgr:
                await agent_mgr.answer_agent_question(agent_id, answers)
                logger.info(f"Routed answer to agent {agent_id}")
            else:
                logger.warning("No agent_manager available to route agent answer")
        else:
            # Route to orchestrator
            orch_service: OrchestratorService = app.state.orchestrator_service
            await orch_service.answer_question(answers)

        logger.http_request("POST", "/api/answer_question", 200)
        return {"status": "success", "message": "Answer received"}
    except Exception as e:
        logger.error(f"Failed to process answer: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/projects/{project_id}/phases")
async def get_project_phases(project_id: str):
    """Get all phase statuses for a project."""
    try:
        logger.http_request("GET", f"/api/projects/{project_id}/phases")
        phases = await db_list_project_phases(uuid.UUID(project_id))
        logger.http_request("GET", f"/api/projects/{project_id}/phases", 200)
        return {
            "status": "success",
            "phases": [p.model_dump(mode="json") for p in phases],
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID format")
    except Exception as e:
        logger.error(f"Failed to get project phases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/projects/{project_id}/phases/{phase}/start")
async def start_phase(
    project_id: str, phase: str, request: Optional[PhaseActionRequest] = None
):
    """Start a phase for a project."""
    try:
        logger.http_request("POST", f"/api/projects/{project_id}/phases/{phase}/start")
        force = request.force if request else False

        # Verify project exists
        project = await db_get_project(uuid.UUID(project_id))
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        # Use PhaseEngine to manage the transition
        repo_path = project.repo_path
        if repo_path:
            rapids_dir = Path(repo_path) / ".rapids"
            engine = PhaseEngine(rapids_dir=rapids_dir)
            phase_info = engine.start_phase(phase, force=force)
        else:
            phase_info = {"status": "in_progress", "phase": phase}

        # Update the project's current phase in the database
        await db_update_project_phase(uuid.UUID(project_id), phase, "in_progress")

        logger.http_request(
            "POST", f"/api/projects/{project_id}/phases/{phase}/start", 200
        )
        return {
            "status": "success",
            "phase": phase,
            "phase_info": phase_info,
        }
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to start phase: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/projects/{project_id}/phases/{phase}/complete")
async def complete_phase(
    project_id: str, phase: str, request: Optional[PhaseActionRequest] = None
):
    """Complete a phase for a project."""
    try:
        logger.http_request(
            "POST", f"/api/projects/{project_id}/phases/{phase}/complete"
        )
        force = request.force if request else False

        # Verify project exists
        project = await db_get_project(uuid.UUID(project_id))
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        # Use PhaseEngine to manage the transition
        repo_path = project.repo_path
        if repo_path:
            rapids_dir = Path(repo_path) / ".rapids"
            engine = PhaseEngine(rapids_dir=rapids_dir)
            phase_info = engine.complete_phase(phase, force=force)
        else:
            phase_info = {"status": "completed", "phase": phase}

        # Update the project's phase status in the database
        await db_update_project_phase(uuid.UUID(project_id), phase, "complete")

        logger.http_request(
            "POST", f"/api/projects/{project_id}/phases/{phase}/complete", 200
        )
        return {
            "status": "success",
            "phase": phase,
            "phase_info": phase_info,
        }
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to complete phase: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/projects/{project_id}/phases/advance")
async def advance_phase(
    project_id: str, request: Optional[PhaseActionRequest] = None
):
    """Advance to the next phase (complete current + start next)."""
    try:
        logger.http_request("POST", f"/api/projects/{project_id}/phases/advance")
        force = request.force if request else False

        # Verify project exists
        project = await db_get_project(uuid.UUID(project_id))
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        repo_path = project.repo_path
        if not repo_path:
            raise HTTPException(
                status_code=400, detail="Project has no repo_path configured"
            )

        rapids_dir = Path(repo_path) / ".rapids"
        engine = PhaseEngine(rapids_dir=rapids_dir)

        current_phase = engine.get_current_phase()
        next_phase_name = engine.get_next_phase(current_phase)

        if next_phase_name is None:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot advance: '{current_phase}' is the last RAPIDS phase",
            )

        phase_info = engine.advance_phase(force=force)

        # Update the database to reflect the new phase
        await db_update_project_phase(
            uuid.UUID(project_id), next_phase_name, "in_progress"
        )

        logger.http_request(
            "POST", f"/api/projects/{project_id}/phases/advance", 200
        )
        return {
            "status": "success",
            "previous_phase": current_phase,
            "current_phase": next_phase_name,
            "phase_info": phase_info,
        }
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to advance phase: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
# RAPIDS FEATURE ENDPOINTS
# ═══════════════════════════════════════════════════════════


@app.get("/api/projects/{project_id}/features")
async def list_project_features(project_id: str):
    """List all features for a project."""
    try:
        logger.http_request("GET", f"/api/projects/{project_id}/features")
        features = await db_list_features(uuid.UUID(project_id))
        logger.http_request("GET", f"/api/projects/{project_id}/features", 200)
        return {
            "status": "success",
            "features": [f.model_dump(mode="json") for f in features],
        }
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID format")
    except Exception as e:
        logger.error(f"Failed to list features: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/projects/{project_id}/features", status_code=201)
async def create_feature(project_id: str, request: CreateFeatureRequest):
    """Create a new feature for a project."""
    try:
        logger.http_request("POST", f"/api/projects/{project_id}/features")

        # Verify project exists
        project = await db_get_project(uuid.UUID(project_id))
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        feature = await db_create_feature(
            project_id=uuid.UUID(project_id),
            name=request.name,
            description=request.description,
            depends_on=request.depends_on,
            acceptance_criteria=request.acceptance_criteria,
            priority=request.priority or 0,
            estimated_complexity=request.estimated_complexity,
            spec_file=request.spec_file,
        )
        logger.http_request("POST", f"/api/projects/{project_id}/features", 201)
        return {
            "status": "success",
            "feature": feature.model_dump(mode="json"),
        }
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid project ID format")
    except Exception as e:
        logger.error(f"Failed to create feature: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/projects/{project_id}/dag")
async def get_feature_dag(project_id: str):
    """Get the feature DAG status for a project."""
    try:
        logger.http_request("GET", f"/api/projects/{project_id}/dag")

        # Verify project exists
        project = await db_get_project(uuid.UUID(project_id))
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        repo_path = project.repo_path
        if not repo_path:
            raise HTTPException(
                status_code=400, detail="Project has no repo_path configured"
            )

        dag_path = Path(repo_path) / ".rapids" / "plan" / "feature_dag.json"
        dag = FeatureDAG(dag_path=dag_path)

        if dag_path.exists():
            dag.load()

        logger.http_request("GET", f"/api/projects/{project_id}/dag", 200)
        return {
            "status": "success",
            "dag": dag.to_dict(),
            "summary": dag.status_summary(),
            "completion": dag.completion_percentage(),
            "feature_count": dag.feature_count,
            "ready_features": dag.get_ready_features(),
        }
    except HTTPException:
        raise
    except FileNotFoundError:
        return {
            "status": "success",
            "dag": {"features": []},
            "summary": {"planned": 0, "in_progress": 0, "complete": 0, "blocked": 0, "deferred": 0},
            "completion": 0.0,
            "feature_count": 0,
            "ready_features": [],
        }
    except Exception as e:
        logger.error(f"Failed to get feature DAG: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/projects/{project_id}/dag/validate")
async def validate_feature_dag(project_id: str):
    """Validate the feature DAG for a project."""
    try:
        logger.http_request("POST", f"/api/projects/{project_id}/dag/validate")

        # Verify project exists
        project = await db_get_project(uuid.UUID(project_id))
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        repo_path = project.repo_path
        if not repo_path:
            raise HTTPException(
                status_code=400, detail="Project has no repo_path configured"
            )

        dag_path = Path(repo_path) / ".rapids" / "plan" / "feature_dag.json"
        dag = FeatureDAG(dag_path=dag_path)

        if not dag_path.exists():
            logger.http_request(
                "POST", f"/api/projects/{project_id}/dag/validate", 200
            )
            return {
                "status": "success",
                "valid": False,
                "errors": ["feature_dag.json not found"],
            }

        dag.load()
        errors = dag.validate()

        logger.http_request(
            "POST", f"/api/projects/{project_id}/dag/validate", 200
        )
        return {
            "status": "success",
            "valid": len(errors) == 0,
            "errors": errors,
            "feature_count": dag.feature_count,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to validate feature DAG: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/projects/{project_id}/dag/features/{feature_id}/status")
async def update_feature_status(project_id: str, feature_id: str, request: Request):
    """
    Update a feature's status in the DAG file on disk.
    Used by execute_ready_features to mark features in_progress/complete/blocked.
    """
    try:
        body = await request.json()
        new_status = body.get("status")  # in_progress, complete, blocked
        agent_name = body.get("agent_name")
        reason = body.get("reason")

        logger.http_request("POST", f"/api/projects/{project_id}/dag/features/{feature_id}/status")

        project = await db_get_project(uuid.UUID(project_id))
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        repo_path = project.repo_path
        dag_path = Path(repo_path) / ".rapids" / "plan" / "feature_dag.json"
        dag = FeatureDAG(dag_path=dag_path)

        if not dag_path.exists():
            raise HTTPException(status_code=404, detail="feature_dag.json not found")

        dag.load()

        if new_status == "in_progress":
            dag.mark_in_progress(feature_id, agent_name)
        elif new_status == "complete":
            newly_ready = dag.mark_complete(feature_id)
            dag.save()
            return {
                "status": "success",
                "feature_id": feature_id,
                "new_status": "complete",
                "newly_ready": newly_ready,
            }
        elif new_status == "blocked":
            dag.mark_blocked(feature_id, reason or "Unknown error")
        else:
            raise HTTPException(status_code=400, detail=f"Invalid status: {new_status}")

        dag.save()
        logger.http_request("POST", f"/api/projects/{project_id}/dag/features/{feature_id}/status", 200)
        return {"status": "success", "feature_id": feature_id, "new_status": new_status}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update feature status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════
# RAPIDS PLUGIN ENDPOINTS
# ═══════════════════════════════════════════════════════════


@app.get("/api/plugins")
async def list_plugins():
    """List all available plugins."""
    try:
        logger.http_request("GET", "/api/plugins")
        loader: PluginLoader = app.state.plugin_loader
        plugins = loader.list_plugins()
        logger.http_request("GET", "/api/plugins", 200)
        return {
            "status": "success",
            "plugins": [p.model_dump(mode="json") for p in plugins],
        }
    except Exception as e:
        logger.error(f"Failed to list plugins: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/plugins/{name}")
async def get_plugin_details(name: str):
    """Get details for a specific plugin."""
    try:
        logger.http_request("GET", f"/api/plugins/{name}")
        loader: PluginLoader = app.state.plugin_loader
        plugin = loader.get_plugin(name)
        if plugin is None:
            raise HTTPException(status_code=404, detail=f"Plugin '{name}' not found")
        logger.http_request("GET", f"/api/plugins/{name}", 200)
        return {
            "status": "success",
            "plugin": plugin.model_dump(mode="json"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get plugin details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    # Display startup banner
    table = Table(
        title="Orchestrator 3 Stream Configuration",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Setting", style="cyan", no_wrap=True)
    table.add_column("Value", style="green")

    table.add_row("Backend URL", config.BACKEND_URL)
    table.add_row("WebSocket URL", config.WEBSOCKET_URL)
    table.add_row("Database", "PostgreSQL (NeonDB)")

    console.print(table)

    # Run the server with config ports
    uvicorn.run(app, host=config.BACKEND_HOST, port=config.BACKEND_PORT)
