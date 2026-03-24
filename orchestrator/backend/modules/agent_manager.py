"""
Agent Manager Module

Centralize agent lifecycle management, tool registration, and background execution.
Implements 20 management tools for the orchestrator agent (8 core + 12 RAPIDS).
"""

import json
import threading
import asyncio
import uuid
import os
from typing import Callable, Dict, Any, List, Optional
from datetime import datetime, timezone
from pathlib import Path
import re

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    ResultMessage,
    tool,
    create_sdk_mcp_server,
    HookMatcher,
)

from .database import (
    create_agent,
    get_agent,
    get_agent_by_name,
    list_agents,
    update_agent_session,
    update_agent_status,
    update_agent_costs,
    delete_agent,
    get_tail_summaries,
    get_tail_raw,
    get_latest_task_slug,
    insert_prompt,
    insert_message_block,
    update_prompt_summary,
    update_log_summary,
)
from .single_agent_prompt import summarize_event
from .command_agent_hooks import (
    create_pre_tool_hook,
    create_post_tool_hook,
    create_user_prompt_hook,
    create_stop_hook,
    create_subagent_stop_hook,
    create_pre_compact_hook,
    create_post_tool_file_tracking_hook,
)
from .websocket_manager import WebSocketManager
from .logger import OrchestratorLogger
from . import config
from .file_tracker import FileTracker
from .subagent_loader import SubagentRegistry
import httpx

# RAPIDS DB functions are NOT used directly by MCP tools (they run in a subprocess).
# MCP tools call the FastAPI HTTP API instead. These imports are kept for non-MCP usage.
from .rapids_database import (
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

# Base URL for MCP tools to call FastAPI endpoints (tools run in SDK subprocess)
_API_BASE = f"http://{config.BACKEND_HOST}:{config.BACKEND_PORT}"
from .workspace_manager import WorkspaceManager
from .plugin_loader import PluginLoader
from .feature_dag import FeatureDAG, FeatureNode
from .project_state import ProjectState
from .phase_engine import PhaseEngine
from .git_worktree import GitWorktreeManager


class AgentManager:
    """
    Manages agent lifecycle, tool registration, and background execution.
    """

    def __init__(
        self,
        orchestrator_agent_id: uuid.UUID,
        ws_manager: WebSocketManager,
        logger: OrchestratorLogger,
        working_dir: Optional[str] = None,
    ):
        """
        Initialize Agent Manager.

        Args:
            orchestrator_agent_id: UUID of the orchestrator agent (for scoping agents)
            ws_manager: WebSocket manager for broadcasting
            logger: Logger instance
            working_dir: Optional working directory override
        """
        self.orchestrator_agent_id = orchestrator_agent_id
        self.ws_manager = ws_manager
        self.logger = logger
        self.working_dir = working_dir or config.get_working_dir()
        self.active_clients: Dict[str, ClaudeSDKClient] = {}
        self.active_clients_lock = threading.Lock()

        # File tracking registry (keyed by agent_id)
        self.file_trackers: Dict[str, FileTracker] = {}

        # Per-agent pending question futures (keyed by agent_id string)
        self._pending_agent_questions: Dict[str, asyncio.Future] = {}

        # Builder agent registry: tracks feature-to-agent mappings for auto-merge
        # Key: agent_name, Value: {feature_id, project_id, repo_path, worktree_path, worktree_branch}
        self._builder_registry: Dict[str, Dict[str, str]] = {}

        # Callback fired when an agent completes — used to notify the orchestrator
        self._on_agent_complete_callback: Optional[Callable] = None

        # RAPIDS workspace/plugin managers (optional, set after init)
        self.workspace_manager: Optional['WorkspaceManager'] = None
        self.plugin_loader: Optional['PluginLoader'] = None

        # Subagent template registry
        self.subagent_registry = SubagentRegistry(self.working_dir, self.logger)
        template_count = len(self.subagent_registry._templates)
        if template_count > 0:
            self.logger.info(f"Subagent registry initialized with {template_count} template(s)")
        else:
            self.logger.warning("⚠️  No subagent templates available. Agents must be created manually.")

        self.logger.info(
            f"AgentManager initialized for orchestrator {orchestrator_agent_id}"
        )

    def set_on_agent_complete(self, callback: Callable) -> None:
        """Register a callback fired when any sub-agent finishes its task."""
        self._on_agent_complete_callback = callback

    async def load_persisted_agents(self) -> List[Dict]:
        """Load non-archived, non-completed agents from DB across all orchestrators.

        On restart, a new orchestrator is created, so we need to check agents
        from previous orchestrators too. Returns summaries so the orchestrator
        can decide whether to resume them.
        """
        from .database import get_connection

        recovered = []
        try:
            async with get_connection() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM agents "
                    "WHERE archived = false "
                    "AND status NOT IN ('completed', 'complete') "
                    "ORDER BY updated_at DESC"
                )
                agents_data = [dict(r) for r in rows]
        except Exception as e:
            self.logger.error(f"Failed to load persisted agents: {e}")
            return recovered

        for agent_data in agents_data:
            agent_id = agent_data.get("id")
            status = agent_data.get("status", "idle")

            # Mark executing agents as idle (they were mid-task when backend died)
            if status == "executing":
                try:
                    await update_agent_status(agent_id, "idle")
                except Exception:
                    pass
                status = "idle"

            # Parse metadata if needed
            metadata = agent_data.get("metadata", {})
            if isinstance(metadata, str):
                import json
                metadata = json.loads(metadata)

            recovered.append({
                "id": str(agent_id),
                "name": agent_data.get("name", "unknown"),
                "model": agent_data.get("model", "sonnet"),
                "system_prompt": agent_data.get("system_prompt"),
                "working_dir": agent_data.get("working_dir"),
                "status": status,
                "session_id": agent_data.get("session_id"),
                "metadata": metadata,
            })

            # Rebuild builder registry from persisted metadata
            builder_info = metadata.get("builder_info")
            if builder_info and agent_data.get("name", "").startswith("builder-"):
                self._builder_registry[agent_data["name"]] = builder_info
                self.logger.info(f"Restored builder registry: {agent_data['name']} → feature {builder_info.get('feature_name', '?')}")

        return recovered

    def create_management_tools(self) -> List:
        """
        Create 20 management tools for orchestrator (8 core + 12 RAPIDS).

        Returns:
            List of tool callables decorated with @tool
        """

        @tool(
            "create_agent",
            "Create a new agent. REQUIRED: name. OPTIONAL: system_prompt, model, subagent_template, phase, project_id. "
            "When phase and project_id are provided, the agent gets an auto-constructed prompt with full project context, "
            "phase-specific instructions, plugin workflow guidance, and artifact paths. "
            "Use 'fast' for haiku model.",
            {"name": str, "system_prompt": str, "model": str, "subagent_template": str, "phase": str, "project_id": str},
        )
        async def create_agent_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            """Tool for creating new agents"""
            try:
                name = args.get("name")
                system_prompt = args.get("system_prompt", "")
                model_input = args.get("model")  # None means "auto-select"
                subagent_template = args.get("subagent_template")
                phase = args.get("phase")
                project_id = args.get("project_id")

                # Auto-select model by phase when no explicit model provided
                if model_input is None:
                    model_input = (
                        config.get_model_for_phase(phase)
                        if phase
                        else config.DEFAULT_AGENT_MODEL
                    )

                # Model alias mapping
                model_aliases = {
                    "opus": "claude-opus-4-20250514",
                    "sonnet": "claude-sonnet-4-5-20250929",
                    "haiku": "claude-haiku-4-5-20251001",
                    "fast": "claude-haiku-4-5-20251001",  # Alias for haiku
                }

                # Resolve model alias or use as-is
                model = (
                    model_aliases.get(model_input.lower(), model_input)
                    if isinstance(model_input, str)
                    else model_input
                )

                # Validate required fields
                if not name:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": "Error: 'name' is required",
                            }
                        ],
                        "is_error": True,
                    }

                # If phase and project_id provided, auto-construct comprehensive prompt
                if phase and project_id:
                    self.logger.info(f"Building phase-aware prompt for {phase}/{project_id}")
                    system_prompt = self.build_phase_agent_prompt(phase, project_id)
                    self.logger.info(f"Phase prompt built: {len(system_prompt)} chars for {phase}")
                    # Pass phase metadata through to create_agent for SDK plugin loading
                    if not subagent_template:
                        subagent_template = None  # Ensure clean path
                    # We'll pass archetype via a special convention in the model field
                    # Actually, modify create_agent to accept phase_metadata
                    _phase_metadata = {"phase": phase, "project_id": project_id}
                    # Get archetype from workspace context
                    if hasattr(self, 'workspace_manager') and self.workspace_manager:
                        ctx = self.workspace_manager._project_contexts.get(project_id, {})
                        _phase_metadata["archetype"] = ctx.get("archetype", ctx.get("plugin_id", ""))
                elif not system_prompt and not subagent_template:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": "Error: Provide system_prompt, subagent_template, or phase+project_id",
                            }
                        ],
                        "is_error": True,
                    }

                # Pass phase metadata if available (for SDK plugin auto-discovery)
                phase_meta = locals().get('_phase_metadata', {})
                result = await self.create_agent(name, system_prompt, model, subagent_template, phase_metadata=phase_meta)

                if result["ok"]:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"✅ Created agent '{name}'\n"
                                f"ID: {result['agent_id']}\n"
                                f"Session: {result['session_id']}\n"
                                f"Model: {model}",
                            }
                        ]
                    }
                else:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"❌ Failed: {result.get('error', 'Unknown error')}",
                            }
                        ],
                        "is_error": True,
                    }

            except Exception as e:
                self.logger.error(f"create_agent tool error: {e}", exc_info=True)
                return {
                    "content": [{"type": "text", "text": f"❌ Error: {str(e)}"}],
                    "is_error": True,
                }

        @tool(
            "list_agents",
            "List all active agents",
            {},
        )
        async def list_agents_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            """Tool for listing agents"""
            try:
                agents = await list_agents(self.orchestrator_agent_id, archived=False)

                if not agents:
                    return {"content": [{"type": "text", "text": "No agents found"}]}

                lines = ["📋 Active Agents:\n"]
                for agent in agents:
                    lines.append(
                        f"• {agent.name} (ID: {agent.id})\n"
                        f"  Status: {agent.status}\n"
                        f"  Model: {agent.model}\n"
                        f"  Tokens: {agent.input_tokens + agent.output_tokens}\n"
                        f"  Cost: ${agent.total_cost:.4f}\n"
                    )

                return {"content": [{"type": "text", "text": "".join(lines)}]}

            except Exception as e:
                self.logger.error(f"list_agents tool error: {e}", exc_info=True)
                return {
                    "content": [{"type": "text", "text": f"❌ Error: {str(e)}"}],
                    "is_error": True,
                }

        @tool(
            "command_agent",
            "Send a command to an agent. REQUIRED: agent_name, command.",
            {"agent_name": str, "command": str},
        )
        async def command_agent_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            """Tool for commanding agents"""
            try:
                agent_name = args.get("agent_name")
                command = args.get("command")

                if not agent_name or not command:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": "❌ Error: 'agent_name' and 'command' are required",
                            }
                        ],
                        "is_error": True,
                    }

                # Get agent by name (scoped to this orchestrator)
                agent = await get_agent_by_name(self.orchestrator_agent_id, agent_name)
                if not agent:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"❌ Agent '{agent_name}' not found",
                            }
                        ],
                        "is_error": True,
                    }

                # Command agent in background (agent.id is already UUID from Pydantic model)
                asyncio.create_task(self.command_agent(agent.id, command))

                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"✅ Command dispatched to '{agent_name}'\n"
                            f"Command: {command[:100]}{'...' if len(command) > 100 else ''}\n"
                            f"Agent will execute in background.",
                        }
                    ]
                }

            except Exception as e:
                self.logger.error(f"command_agent tool error: {e}", exc_info=True)
                return {
                    "content": [{"type": "text", "text": f"❌ Error: {str(e)}"}],
                    "is_error": True,
                }

        @tool(
            "check_agent_status",
            "Check agent status and recent activity. REQUIRED: agent_name.",
            {"agent_name": str, "tail_count": int, "offset": int, "verbose_logs": bool},
        )
        async def check_agent_status_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            """Tool for checking agent status"""
            try:
                agent_name = args.get("agent_name")
                tail_count = args.get("tail_count", 10)
                offset = args.get("offset", 0)
                verbose_logs = args.get("verbose_logs", False)

                if not agent_name:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": "❌ Error: 'agent_name' is required",
                            }
                        ],
                        "is_error": True,
                    }

                agent = await get_agent_by_name(self.orchestrator_agent_id, agent_name)
                if not agent:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"❌ Agent '{agent_name}' not found",
                            }
                        ],
                        "is_error": True,
                    }

                # Use Pydantic model properties
                task_slug = await get_latest_task_slug(agent.id)

                lines = [
                    f"📊 Agent Status: {agent.name}\n",
                    f"Status: {agent.status}\n",
                    f"Model: {agent.model}\n",
                    f"Tokens: {agent.input_tokens + agent.output_tokens}\n",
                    f"Cost: ${agent.total_cost:.4f}\n",
                ]

                if task_slug:
                    lines.append(f"\n🔍 Recent Activity (Task: {task_slug}):\n")

                    # Use verbose or summary mode
                    if verbose_logs:
                        logs = await get_tail_raw(
                            agent.id, task_slug, count=tail_count, offset=offset
                        )
                        for log in logs:
                            lines.append(
                                f"• [{log['event_type']}] {log.get('content', 'No content')}\n"
                                f"  Payload: {log.get('payload', {})}\n"
                            )
                    else:
                        logs = await get_tail_summaries(
                            agent.id, task_slug, count=tail_count, offset=offset
                        )
                        for log in logs:
                            lines.append(
                                f"• [{log['event_type']}] {log.get('summary', 'No summary')}\n"
                            )
                else:
                    lines.append("\nNo recent activity\n")

                return {"content": [{"type": "text", "text": "".join(lines)}]}

            except Exception as e:
                self.logger.error(f"check_agent_status tool error: {e}", exc_info=True)
                return {
                    "content": [{"type": "text", "text": f"❌ Error: {str(e)}"}],
                    "is_error": True,
                }

        @tool(
            "delete_agent",
            "Delete an agent. REQUIRED: agent_name.",
            {"agent_name": str},
        )
        async def delete_agent_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            """Tool for deleting agents"""
            try:
                agent_name = args.get("agent_name")

                if not agent_name:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": "❌ Error: 'agent_name' is required",
                            }
                        ],
                        "is_error": True,
                    }

                agent = await get_agent_by_name(self.orchestrator_agent_id, agent_name)
                if not agent:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"❌ Agent '{agent_name}' not found",
                            }
                        ],
                        "is_error": True,
                    }

                # Use Pydantic model properties
                await delete_agent(agent.id)

                # Clean up file tracker
                if str(agent.id) in self.file_trackers:
                    del self.file_trackers[str(agent.id)]

                # Broadcast deletion (convert UUID to string for JSON)
                await self.ws_manager.broadcast_agent_deleted(str(agent.id))

                return {
                    "content": [
                        {"type": "text", "text": f"✅ Deleted agent '{agent_name}'"}
                    ]
                }

            except Exception as e:
                self.logger.error(f"delete_agent tool error: {e}", exc_info=True)
                return {
                    "content": [{"type": "text", "text": f"❌ Error: {str(e)}"}],
                    "is_error": True,
                }

        @tool(
            "interrupt_agent",
            "Interrupt a running agent. REQUIRED: agent_name.",
            {"agent_name": str},
        )
        async def interrupt_agent_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            """Tool for interrupting agents"""
            try:
                agent_name = args.get("agent_name")

                if not agent_name:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": "❌ Error: 'agent_name' is required",
                            }
                        ],
                        "is_error": True,
                    }

                with self.active_clients_lock:
                    client = self.active_clients.get(agent_name)

                if client:
                    await client.interrupt()
                    with self.active_clients_lock:
                        del self.active_clients[agent_name]

                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"✅ Interrupted agent '{agent_name}'",
                            }
                        ]
                    }
                else:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": f"⚠️ Agent '{agent_name}' is not currently running",
                            }
                        ]
                    }

            except Exception as e:
                self.logger.error(f"interrupt_agent tool error: {e}", exc_info=True)
                return {
                    "content": [{"type": "text", "text": f"❌ Error: {str(e)}"}],
                    "is_error": True,
                }

        @tool(
            "read_system_logs",
            "Read recent system logs with filtering",
            {"offset": int, "limit": int, "message_contains": str, "level": str},
        )
        async def read_system_logs_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            """Tool for reading system logs"""
            try:
                from .database import list_system_logs

                offset = args.get("offset", 0)
                limit = args.get("limit", 50)
                message_contains = args.get("message_contains")
                level = args.get("level")

                # Fetch system logs
                logs = await list_system_logs(
                    limit=limit,
                    offset=offset,
                    message_contains=message_contains,
                    level=level,
                )

                if not logs:
                    return {
                        "content": [
                            {
                                "type": "text",
                                "text": "📋 No system logs found matching the criteria",
                            }
                        ]
                    }

                lines = [f"📋 System Logs (showing {len(logs)} of max {limit}):\n\n"]

                for log in logs:
                    timestamp = log.get("timestamp", "N/A")
                    if hasattr(timestamp, "isoformat"):
                        timestamp = timestamp.isoformat()

                    level_str = log.get("level", "INFO")
                    message = log.get("message", "")
                    summary = log.get("summary", "")

                    # Show summary if available, otherwise message
                    display_text = summary if summary else message

                    lines.append(f"[{timestamp}] {level_str}: {display_text}\n")

                return {"content": [{"type": "text", "text": "".join(lines)}]}

            except Exception as e:
                self.logger.error(f"read_system_logs tool error: {e}", exc_info=True)
                return {
                    "content": [{"type": "text", "text": f"❌ Error: {str(e)}"}],
                    "is_error": True,
                }

        @tool(
            "report_cost",
            "Report orchestrator's costs, tokens, and session ID",
            {},
        )
        async def report_cost_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            """Tool for cost reporting"""
            try:
                from .database import get_orchestrator

                # Get orchestrator agent info
                orch_data = await get_orchestrator()

                if not orch_data:
                    return {
                        "content": [
                            {"type": "text", "text": "❌ Error: Orchestrator not found"}
                        ],
                        "is_error": True,
                    }

                total_tokens = orch_data["input_tokens"] + orch_data["output_tokens"]
                context_percentage = (
                    total_tokens / 200000
                ) * 100  # 200k context window

                lines = [
                    "💰 Orchestrator Cost Report:\n\n",
                    f"Session ID: {orch_data['session_id'] or 'Not set yet'}\n",
                    f"Status: {orch_data['status']}\n\n",
                    f"Total Cost: ${orch_data['total_cost']:.4f}\n",
                    f"Input Tokens: {orch_data['input_tokens']:,}\n",
                    f"Output Tokens: {orch_data['output_tokens']:,}\n",
                    f"Total Tokens: {total_tokens:,}\n",
                    f"Context Usage: {context_percentage:.1f}%\n",
                ]

                # Add warning if approaching context limit
                if context_percentage >= 80:
                    lines.append(
                        f"\n⚠️  Warning: Context usage at {context_percentage:.1f}% - consider compacting soon\n"
                    )

                return {"content": [{"type": "text", "text": "".join(lines)}]}

            except Exception as e:
                self.logger.error(f"report_cost tool error: {e}", exc_info=True)
                return {
                    "content": [{"type": "text", "text": f"❌ Error: {str(e)}"}],
                    "is_error": True,
                }

        # ── RAPIDS Workspace / Project / Phase / Feature Tools ──────────

        @tool(
            "create_workspace",
            "Create a new RAPIDS workspace. REQUIRED: name, description.",
            {"name": str, "description": str},
        )
        async def create_workspace_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            """Tool for creating a RAPIDS workspace via HTTP API"""
            try:
                name = args.get("name")
                description = args.get("description", "")

                if not name:
                    return {
                        "content": [{"type": "text", "text": "Error: 'name' is required"}],
                        "is_error": True,
                    }

                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f"{_API_BASE}/api/workspaces",
                        json={"name": name, "description": description},
                        timeout=15.0,
                    )
                    data = resp.json()

                if resp.status_code not in (200, 201) or data.get("status") != "success":
                    return {
                        "content": [{"type": "text", "text": f"Error: {data.get('detail', 'Unknown error')}"}],
                        "is_error": True,
                    }

                ws = data["workspace"]
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Created workspace '{name}'\n"
                            f"ID: {ws['id']}\n"
                            f"Description: {description}",
                        }
                    ]
                }

            except Exception as e:
                self.logger.error(f"create_workspace tool error: {e}", exc_info=True)
                return {
                    "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                    "is_error": True,
                }

        @tool(
            "list_workspaces",
            "List all RAPIDS workspaces.",
            {},
        )
        async def list_workspaces_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            """Tool for listing RAPIDS workspaces via HTTP API"""
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"{_API_BASE}/api/workspaces", timeout=15.0)
                    data = resp.json()

                workspaces = data.get("workspaces", [])
                if not workspaces:
                    return {"content": [{"type": "text", "text": "No workspaces found. Use create_workspace to create one."}]}

                lines = ["RAPIDS Workspaces:\n"]
                for ws in workspaces:
                    lines.append(
                        f"  {ws['name']} (ID: {ws['id']})\n"
                        f"    Description: {ws.get('description', '')}\n"
                        f"    Status: {ws.get('status', 'active')}\n"
                    )

                return {"content": [{"type": "text", "text": "".join(lines)}]}

            except Exception as e:
                self.logger.error(f"list_workspaces tool error: {e}", exc_info=True)
                return {
                    "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                    "is_error": True,
                }

        @tool(
            "onboard_project",
            "Onboard a new project into a RAPIDS workspace. REQUIRED: workspace_id, name, repo_path, archetype. OPTIONAL: plugin_id.",
            {"workspace_id": str, "name": str, "repo_path": str, "archetype": str, "plugin_id": str},
        )
        async def onboard_project_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            """Tool for onboarding a project into RAPIDS via HTTP API"""
            try:
                workspace_id = args.get("workspace_id")
                name = args.get("name")
                repo_path = args.get("repo_path")
                archetype = args.get("archetype")

                if not all([workspace_id, name, repo_path, archetype]):
                    return {
                        "content": [{"type": "text", "text": "Error: workspace_id, name, repo_path, and archetype are required"}],
                        "is_error": True,
                    }

                # Validate repo_path exists
                if not Path(repo_path).exists():
                    return {
                        "content": [{"type": "text", "text": f"Error: repo_path '{repo_path}' does not exist"}],
                        "is_error": True,
                    }

                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f"{_API_BASE}/api/workspaces/{workspace_id}/projects",
                        json={"name": name, "repo_path": repo_path, "archetype": archetype},
                        timeout=15.0,
                    )
                    data = resp.json()

                if resp.status_code not in (200, 201) or data.get("status") != "success":
                    return {
                        "content": [{"type": "text", "text": f"Error: {data.get('detail', 'Unknown error')}"}],
                        "is_error": True,
                    }

                project = data["project"]
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Onboarded project '{name}'\n"
                            f"Project ID: {project['id']}\n"
                            f"Workspace: {workspace_id}\n"
                            f"Repo: {repo_path}\n"
                            f"Archetype: {archetype}\n"
                            f"Phases initialized: {data.get('phases_initialized', 6)}",
                        }
                    ]
                }

            except Exception as e:
                self.logger.error(f"onboard_project tool error: {e}", exc_info=True)
                return {
                    "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                    "is_error": True,
                }

        @tool(
            "list_projects",
            "List projects in a RAPIDS workspace. REQUIRED: workspace_id.",
            {"workspace_id": str},
        )
        async def list_projects_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            """Tool for listing projects in a workspace via HTTP API"""
            try:
                workspace_id = args.get("workspace_id")
                if not workspace_id:
                    return {
                        "content": [{"type": "text", "text": "Error: 'workspace_id' is required"}],
                        "is_error": True,
                    }

                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"{_API_BASE}/api/workspaces/{workspace_id}/projects", timeout=15.0)
                    data = resp.json()

                projects = data.get("projects", [])
                if not projects:
                    return {"content": [{"type": "text", "text": "No projects found in this workspace"}]}

                lines = ["Projects:\n"]
                for p in projects:
                    lines.append(
                        f"  {p['name']} (ID: {p['id']})\n"
                        f"    Repo: {p.get('repo_path', '')}\n"
                        f"    Archetype: {p.get('archetype', '')}\n"
                        f"    Phase: {p.get('current_phase', 'research')} [{p.get('phase_status', 'not_started')}]\n"
                    )

                return {"content": [{"type": "text", "text": "".join(lines)}]}

            except Exception as e:
                self.logger.error(f"list_projects tool error: {e}", exc_info=True)
                return {
                    "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                    "is_error": True,
                }

        @tool(
            "switch_project",
            "Switch active project context. REQUIRED: project_id.",
            {"project_id": str},
        )
        async def switch_project_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            """Tool for switching the active project context via HTTP API"""
            try:
                project_id = args.get("project_id")
                if not project_id:
                    return {
                        "content": [{"type": "text", "text": "Error: 'project_id' is required"}],
                        "is_error": True,
                    }

                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f"{_API_BASE}/api/projects/{project_id}/switch",
                        timeout=15.0,
                    )
                    data = resp.json()

                if resp.status_code not in (200, 201):
                    return {
                        "content": [{"type": "text", "text": f"Error: {data.get('detail', 'Project not found')}"}],
                        "is_error": True,
                    }

                project = data.get("project", {})
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Switched to project '{project.get('name', project_id)}'\n"
                            f"Working directory: {project.get('repo_path', 'N/A')}",
                        }
                    ]
                }

            except Exception as e:
                self.logger.error(f"switch_project tool error: {e}", exc_info=True)
                return {
                    "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                    "is_error": True,
                }

        @tool(
            "get_project_status",
            "Get project details with phase information. REQUIRED: project_id.",
            {"project_id": str},
        )
        async def get_project_status_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            """Tool for getting project status with phase info via HTTP API"""
            try:
                project_id = args.get("project_id")
                if not project_id:
                    return {
                        "content": [{"type": "text", "text": "Error: 'project_id' is required"}],
                        "is_error": True,
                    }

                async with httpx.AsyncClient() as client:
                    proj_resp = await client.get(f"{_API_BASE}/api/projects/{project_id}", timeout=15.0)
                    phase_resp = await client.get(f"{_API_BASE}/api/projects/{project_id}/phases", timeout=15.0)

                project = proj_resp.json().get("project", {})
                phases = phase_resp.json().get("phases", [])

                lines = [
                    f"Project: {project.get('name', 'N/A')}\n",
                    f"ID: {project_id}\n",
                    f"Repo: {project.get('repo_path', 'N/A')}\n",
                    f"Archetype: {project.get('archetype', 'N/A')}\n",
                    f"Current Phase: {project.get('current_phase', 'N/A')} [{project.get('phase_status', 'N/A')}]\n",
                    f"\nPhases:\n",
                ]

                for phase in phases:
                    status = phase.get("status", "pending")
                    phase_name = phase.get("phase", "unknown")
                    lines.append(f"  [{status}] {phase_name}\n")

                return {"content": [{"type": "text", "text": "".join(lines)}]}

            except Exception as e:
                self.logger.error(f"get_project_status tool error: {e}", exc_info=True)
                return {
                    "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                    "is_error": True,
                }

        @tool(
            "start_phase",
            "Start a RAPIDS phase for a project. REQUIRED: project_id, phase.",
            {"project_id": str, "phase": str},
        )
        async def start_phase_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            """Tool for starting a RAPIDS phase via HTTP API"""
            try:
                project_id = args.get("project_id")
                phase = args.get("phase")

                if not project_id or not phase:
                    return {
                        "content": [{"type": "text", "text": "Error: 'project_id' and 'phase' are required"}],
                        "is_error": True,
                    }

                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f"{_API_BASE}/api/projects/{project_id}/phases/{phase}/start",
                        timeout=15.0,
                    )
                    data = resp.json()

                if resp.status_code not in (200, 201):
                    return {
                        "content": [{"type": "text", "text": f"Error: {data.get('detail', 'Failed to start phase')}"}],
                        "is_error": True,
                    }

                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Started phase '{phase}' for project {project_id}\n"
                            f"Status: {data.get('status', 'success')}",
                        }
                    ]
                }

            except Exception as e:
                self.logger.error(f"start_phase tool error: {e}", exc_info=True)
                return {
                    "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                    "is_error": True,
                }

        @tool(
            "complete_phase",
            "Complete a RAPIDS phase for a project. REQUIRED: project_id, phase.",
            {"project_id": str, "phase": str},
        )
        async def complete_phase_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            """Tool for completing a RAPIDS phase via HTTP API"""
            try:
                project_id = args.get("project_id")
                phase = args.get("phase")

                if not project_id or not phase:
                    return {
                        "content": [{"type": "text", "text": "Error: 'project_id' and 'phase' are required"}],
                        "is_error": True,
                    }

                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f"{_API_BASE}/api/projects/{project_id}/phases/{phase}/complete",
                        timeout=15.0,
                    )
                    data = resp.json()

                if resp.status_code not in (200, 201):
                    return {
                        "content": [{"type": "text", "text": f"Error: {data.get('detail', 'Failed to complete phase')}"}],
                        "is_error": True,
                    }

                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Completed phase '{phase}' for project {project_id}\n"
                            f"Status: {data.get('status', 'success')}",
                        }
                    ]
                }

            except Exception as e:
                self.logger.error(f"complete_phase tool error: {e}", exc_info=True)
                return {
                    "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                    "is_error": True,
                }

        @tool(
            "advance_phase",
            "Complete the current RAPIDS phase and start the next one. REQUIRED: project_id.",
            {"project_id": str},
        )
        async def advance_phase_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            """Tool for advancing to the next RAPIDS phase via HTTP API"""
            try:
                project_id = args.get("project_id")
                if not project_id:
                    return {
                        "content": [{"type": "text", "text": "Error: 'project_id' is required"}],
                        "is_error": True,
                    }

                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f"{_API_BASE}/api/projects/{project_id}/phases/advance",
                        timeout=15.0,
                    )
                    data = resp.json()

                if resp.status_code not in (200, 201):
                    return {
                        "content": [{"type": "text", "text": f"Error: {data.get('detail', 'Failed to advance phase')}"}],
                        "is_error": True,
                    }

                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Advanced phase for project {project_id}\n"
                            f"Status: {data.get('status', 'success')}",
                        }
                    ]
                }

            except Exception as e:
                self.logger.error(f"advance_phase tool error: {e}", exc_info=True)
                return {
                    "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                    "is_error": True,
                }

        @tool(
            "list_features",
            "List features for a RAPIDS project. REQUIRED: project_id.",
            {"project_id": str},
        )
        async def list_features_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            """Tool for listing features in a project via HTTP API"""
            try:
                project_id = args.get("project_id")
                if not project_id:
                    return {
                        "content": [{"type": "text", "text": "Error: 'project_id' is required"}],
                        "is_error": True,
                    }

                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"{_API_BASE}/api/projects/{project_id}/features", timeout=15.0)
                    data = resp.json()

                features = data.get("features", [])
                if not features:
                    return {"content": [{"type": "text", "text": "No features found for this project"}]}

                lines = ["Features:\n"]
                for f in features:
                    status = f.get("status", "pending")
                    lines.append(
                        f"  [{status}] {f.get('name', 'unnamed')} (ID: {f['id']})\n"
                        f"    Description: {f.get('description', '')}\n"
                    )

                return {"content": [{"type": "text", "text": "".join(lines)}]}

            except Exception as e:
                self.logger.error(f"list_features tool error: {e}", exc_info=True)
                return {
                    "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                    "is_error": True,
                }

        @tool(
            "create_feature",
            "Create a feature for a RAPIDS project. REQUIRED: project_id, name, description. OPTIONAL: depends_on (comma-separated feature IDs), acceptance_criteria (comma-separated list), priority.",
            {"project_id": str, "name": str, "description": str, "depends_on": str, "acceptance_criteria": str, "priority": str},
        )
        async def create_feature_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            """Tool for creating a feature via HTTP API"""
            try:
                project_id = args.get("project_id")
                name = args.get("name")
                description = args.get("description", "")
                depends_on_str = args.get("depends_on", "")
                acceptance_criteria_str = args.get("acceptance_criteria", "")
                priority = args.get("priority", "medium")

                if not project_id or not name:
                    return {
                        "content": [{"type": "text", "text": "Error: 'project_id' and 'name' are required"}],
                        "is_error": True,
                    }

                depends_on = [d.strip() for d in depends_on_str.split(",") if d.strip()] if depends_on_str else []
                acceptance_criteria = [a.strip() for a in acceptance_criteria_str.split(",") if a.strip()] if acceptance_criteria_str else []

                # Convert priority to int (API expects integer)
                priority_map = {"critical": 0, "high": 1, "medium": 2, "low": 3, "p0": 0, "p1": 1, "p2": 2, "p3": 3}
                if isinstance(priority, str):
                    priority_int = priority_map.get(priority.lower(), 2)
                else:
                    try:
                        priority_int = int(priority)
                    except (ValueError, TypeError):
                        priority_int = 2

                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f"{_API_BASE}/api/projects/{project_id}/features",
                        json={
                            "name": name,
                            "description": description,
                            "depends_on": depends_on,
                            "acceptance_criteria": acceptance_criteria,
                            "priority": priority_int,
                        },
                        timeout=15.0,
                    )
                    data = resp.json()

                if resp.status_code not in (200, 201) or data.get("status") != "success":
                    return {
                        "content": [{"type": "text", "text": f"Error: {data.get('detail', 'Unknown error')}"}],
                        "is_error": True,
                    }

                feature = data["feature"]
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Created feature '{name}'\n"
                            f"Feature ID: {feature['id']}\n"
                            f"Project: {project_id}\n"
                            f"Priority: {priority}\n"
                            f"Dependencies: {depends_on if depends_on else 'none'}\n"
                            f"Acceptance Criteria: {len(acceptance_criteria)} item(s)",
                        }
                    ]
                }

            except Exception as e:
                self.logger.error(f"create_feature tool error: {e}", exc_info=True)
                return {
                    "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                    "is_error": True,
                }

        @tool(
            "get_feature_dag_status",
            "Get the feature DAG status for a project: total, completed, in-progress, ready features, completion %, critical path. REQUIRED: project_id.",
            {"project_id": str},
        )
        async def get_feature_dag_status_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            """Tool for getting feature DAG status"""
            try:
                project_id = args.get("project_id")

                if not project_id:
                    return {
                        "content": [{"type": "text", "text": "Error: 'project_id' is required"}],
                        "is_error": True,
                    }

                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"{_API_BASE}/api/projects/{project_id}/dag", timeout=15.0)
                    data = resp.json()

                if resp.status_code not in (200, 201):
                    return {"content": [{"type": "text", "text": f"Error: {data.get('detail', 'No features found')}"}]}

                status = data.get("dag_status", {})

                lines = [
                    f"Feature DAG Status for project {project_id}:\n",
                    f"  Total features: {status.get('total', 0)}\n",
                    f"  Completed: {status.get('completed', 0)}\n",
                    f"  In Progress: {status.get('in_progress', 0)}\n",
                    f"  Ready (unblocked): {status.get('ready', 0)}\n",
                    f"  Completion: {status.get('completion_pct', 0):.1f}%\n",
                ]

                critical_path = status.get("critical_path", [])
                if critical_path:
                    lines.append(f"  Critical Path: {' -> '.join(critical_path)}\n")

                return {"content": [{"type": "text", "text": "".join(lines)}]}

            except Exception as e:
                self.logger.error(f"get_feature_dag_status tool error: {e}", exc_info=True)
                return {
                    "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                    "is_error": True,
                }

        @tool(
            "execute_ready_features",
            "Execute all ready (unblocked) features from the DAG by creating a builder agent per feature. Features without dependencies run in parallel. Each agent gets fresh context with the feature spec.",
            {
                "project_id": str,
                "max_parallel": int,
            },
        )
        async def execute_ready_features_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            """Execute ready features by spawning builder agents in parallel"""
            try:
                project_id = args.get("project_id")
                max_parallel = args.get("max_parallel", 3)

                if not project_id:
                    return {
                        "content": [{"type": "text", "text": "Error: 'project_id' is required"}],
                        "is_error": True,
                    }

                # Get the DAG to find ready features
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"{_API_BASE}/api/projects/{project_id}/dag", timeout=15.0)
                    data = resp.json()

                if resp.status_code not in (200, 201):
                    return {"content": [{"type": "text", "text": f"Error: {data.get('detail', 'No features found')}"}]}

                # Use ready_features from DAG API (correctly computed by FeatureDAG.get_ready_features)
                ready_feature_ids = data.get("ready_features", [])
                dag_data = data.get("dag", {})
                all_features = {f["id"]: f for f in dag_data.get("features", [])}
                dag_status = data.get("dag_status", {})

                if not ready_feature_ids:
                    return {"content": [{"type": "text", "text": f"No ready features to execute. DAG: {dag_status.get('completed', 0)}/{dag_status.get('total', 0)} complete."}]}

                ready_features = [all_features[fid] for fid in ready_feature_ids if fid in all_features]

                # Filter out features that already have a builder agent registered
                active_feature_ids = {info["feature_id"] for info in self._builder_registry.values()}
                ready_features = [f for f in ready_features if f.get("id") not in active_feature_ids]

                if not ready_features:
                    return {"content": [{"type": "text", "text": "All ready features already have builder agents running."}]}

                # Limit parallelism
                features_to_execute = ready_features[:max_parallel]
                agents_created = []

                # Get project info for context
                async with httpx.AsyncClient() as client:
                    proj_resp = await client.get(f"{_API_BASE}/api/projects/{project_id}", timeout=15.0)
                    proj_data = proj_resp.json()

                project_info = proj_data.get("project", proj_data.get("data", {}))
                project_name = project_info.get("name", "unknown")
                repo_path = project_info.get("repo_path", ".")

                # Read project spec for context
                spec_content = ""
                spec_path = Path(repo_path) / ".rapids" / "plan" / "specification.md"
                if not spec_path.exists():
                    spec_path = Path(repo_path) / ".rapids" / "plan" / "spec.md"
                if spec_path.exists():
                    spec_content = spec_path.read_text()[:3000]  # Limit to 3k chars

                for feature in features_to_execute:
                    feature_id = feature.get("id", "")
                    feature_name = feature.get("name", "unnamed")
                    feature_desc = feature.get("description", "")
                    acceptance = feature.get("acceptance_criteria", [])
                    if isinstance(acceptance, list):
                        acceptance_text = "\n".join(f"  - {c}" for c in acceptance)
                    else:
                        acceptance_text = str(acceptance)

                    agent_name = f"builder-{feature_name}"[:40]

                    # Read per-feature spec if available
                    feature_spec = ""
                    for spec_dir in [
                        Path(repo_path) / ".rapids" / "plan" / "features" / feature_id,
                        Path(repo_path) / ".rapids" / "plan" / "features" / feature_name,
                    ]:
                        spec_file = spec_dir / "spec.md"
                        if spec_file.exists():
                            feature_spec = spec_file.read_text()
                            break

                    # Build comprehensive feature prompt
                    feature_prompt = (
                        f"# Feature Builder Agent — {feature_name}\n\n"
                        f"You are implementing a single feature for the **{project_name}** project.\n\n"
                        f"## Feature\n"
                        f"**ID:** {feature_id}\n"
                        f"**Name:** {feature_name}\n"
                        f"**Description:** {feature_desc}\n\n"
                        f"## Acceptance Criteria\n{acceptance_text}\n\n"
                        f"## Working Directory\n`{repo_path}`\n\n"
                    )
                    if spec_content:
                        feature_prompt += f"## Project Specification (excerpt)\n{spec_content}\n\n"
                    if feature_spec:
                        feature_prompt += f"## Feature Specification\n{feature_spec}\n\n"
                    feature_prompt += (
                        f"## Instructions\n"
                        f"1. Read the feature spec and acceptance criteria carefully\n"
                        f"2. Implement the feature following project conventions\n"
                        f"3. Write tests covering all acceptance criteria\n"
                        f"4. Run tests and ensure they pass\n"
                        f"5. When done, summarize what you implemented\n"
                    )

                    # NOTE: status is marked in_progress AFTER agent creation succeeds
                    # (inside _launch_builder) to avoid stuck features on failure

                    agents_created.append({
                        "agent": agent_name,
                        "feature": feature_name,
                        "feature_id": feature_id,
                        "status": "queued",
                        "prompt": feature_prompt,
                    })

                # Create git worktrees for parallel isolation
                from .git_worktree import GitWorktreeManager
                git_mgr = None
                try:
                    git_mgr = GitWorktreeManager(repo_path)
                    git_mgr.ensure_git_repo()
                    self.logger.info(f"GitWorktreeManager initialized for {repo_path}")
                except Exception as e:
                    self.logger.warning(f"Failed to init GitWorktreeManager: {e}. Agents will share main repo.")

                # Launch all agents in parallel using asyncio tasks
                async def _launch_builder(entry):
                    """Create and dispatch a single builder agent with worktree isolation."""
                    # Guard: skip if agent with this name already exists (prevents duplicates)
                    from .database import get_agent_by_name
                    existing = await get_agent_by_name(self.orchestrator_agent_id, entry["agent"])
                    if existing and not existing.archived:
                        self.logger.info(f"Agent '{entry['agent']}' already exists, skipping")
                        entry["status"] = "already_exists"
                        return
                    try:
                        # Create git worktree for this feature
                        worktree_path = None
                        worktree_branch = None
                        if git_mgr:
                            try:
                                wt_path = git_mgr.create_worktree(entry["feature_id"])
                                worktree_path = str(wt_path)
                                worktree_branch = f"rapids/{entry['feature_id']}"
                                entry["worktree"] = worktree_path
                                entry["branch"] = worktree_branch
                                self.logger.info(f"Created worktree for '{entry['feature_id']}' at {worktree_path}")

                                # Add worktree info to the prompt
                                entry["prompt"] += (
                                    f"\n\n## Git Worktree\n"
                                    f"You are working in an isolated git worktree on branch `{worktree_branch}`.\n"
                                    f"Working directory: `{worktree_path}`\n"
                                    f"Commit your changes to this branch when done.\n"
                                )
                            except Exception as wt_err:
                                self.logger.warning(f"Worktree creation failed for '{entry['feature_id']}': {wt_err}")

                        # Get archetype for plugin loading
                        archetype = project_info.get("archetype", "")
                        phase_meta = {
                            "phase": "implement",
                            "project_id": project_id,
                            "archetype": archetype,
                        }
                        if worktree_path:
                            phase_meta["worktree_path"] = worktree_path

                        result = await self.create_agent(
                            name=entry["agent"],
                            system_prompt=entry["prompt"],
                            model=config.get_model_for_phase("implement"),
                            phase_metadata=phase_meta,
                        )
                        entry["status"] = "created"

                        # Mark feature in_progress ONLY after agent creation succeeds
                        try:
                            async with httpx.AsyncClient() as status_client:
                                resp = await status_client.post(
                                    f"{_API_BASE}/api/projects/{project_id}/dag/features/{entry['feature_id']}/status",
                                    json={"status": "in_progress", "agent_name": entry["agent"]},
                                    timeout=10.0,
                                )
                                self.logger.info(f"[FeatureStatus] {entry['feature']} → in_progress (HTTP {resp.status_code})")
                            await self.ws_manager.broadcast({
                                "type": "feature_started",
                                "data": {
                                    "project_id": project_id,
                                    "feature_id": entry["feature_id"],
                                    "feature_name": entry["feature"],
                                    "agent_name": entry["agent"],
                                }
                            })
                        except Exception as status_err:
                            self.logger.error(f"[FeatureStatus] FAILED to mark '{entry['feature']}' in_progress: {status_err}")

                        # Dispatch the implementation task
                        agent_id_for_dispatch = result.get("agent_id") if isinstance(result, dict) else None
                        if not agent_id_for_dispatch:
                            raise RuntimeError(f"Agent creation returned no agent_id: {result}")

                        # Dispatch directly — don't use create_task (it may never run)
                        self.logger.info(f"[Dispatch] Dispatching command to builder '{entry['agent']}'...")
                        try:
                            dispatch_task = asyncio.create_task(self.command_agent(
                                agent_id=uuid.UUID(agent_id_for_dispatch),
                                command=f"Implement the '{entry['feature']}' feature. Follow the spec and acceptance criteria. Run tests when done.",
                            ))
                            # Store the task so it doesn't get garbage collected
                            entry["_dispatch_task"] = dispatch_task
                            self.logger.info(f"[Dispatch] Task created for builder '{entry['agent']}'")
                        except Exception as dispatch_err:
                            self.logger.error(f"[Dispatch] Failed for '{entry['feature']}': {dispatch_err}")
                            # Roll back feature status
                            try:
                                async with httpx.AsyncClient() as rb_client:
                                    await rb_client.post(
                                        f"{_API_BASE}/api/projects/{project_id}/dag/features/{entry['feature_id']}/status",
                                        json={"status": "planned"},
                                        timeout=10.0,
                                    )
                            except Exception:
                                pass
                        entry["status"] = "dispatched"

                        # Register builder for auto-merge on completion
                        builder_info = {
                            "feature_id": entry["feature_id"],
                            "feature_name": entry["feature"],
                            "project_id": project_id,
                            "repo_path": repo_path,
                            "worktree_path": worktree_path or "",
                            "worktree_branch": worktree_branch or "",
                        }
                        self._builder_registry[entry["agent"]] = builder_info
                        self.logger.info(f"Registered builder '{entry['agent']}' for auto-merge (feature={entry['feature_id']}, branch={worktree_branch})")

                        # Persist builder info to agent metadata for crash recovery
                        try:
                            from .database import get_connection
                            async with get_connection() as conn:
                                await conn.execute(
                                    "UPDATE agents SET metadata = metadata || $1::jsonb WHERE id = $2",
                                    json.dumps({"builder_info": builder_info}),
                                    uuid.UUID(agent_id_for_dispatch),
                                )
                            self.logger.info(f"[BuilderInfo] Persisted to agent metadata for '{entry['agent']}'")
                        except Exception as persist_err:
                            self.logger.error(f"[BuilderInfo] Failed to persist for '{entry['agent']}': {persist_err}")

                    except Exception as e:
                        entry["status"] = f"error: {str(e)}"
                        self.logger.error(f"Builder launch failed for '{entry['feature']}': {e}")

                        # Roll back: reset feature status to planned so it can be retried
                        try:
                            async with httpx.AsyncClient() as rollback_client:
                                await rollback_client.post(
                                    f"{_API_BASE}/api/projects/{project_id}/dag/features/{entry['feature_id']}/status",
                                    json={"status": "planned"},
                                    timeout=10.0,
                                )
                            self.logger.info(f"Rolled back feature '{entry['feature']}' to planned after launch failure")
                        except Exception as rb_err:
                            self.logger.error(f"Failed to roll back feature status: {rb_err}")

                        await self.ws_manager.broadcast({
                            "type": "feature_failed",
                            "data": {"project_id": project_id, "feature_id": entry["feature_id"], "error": str(e)}
                        })

                # Launch all builders concurrently
                await asyncio.gather(*[_launch_builder(entry) for entry in agents_created])

                lines = [
                    f"Executing {len(features_to_execute)} ready features (max_parallel={max_parallel}):\n\n",
                ]
                for a in agents_created:
                    lines.append(f"  - {a['feature']} → agent '{a['agent']}' [{a['status']}]\n")

                remaining = len(ready_features) - len(features_to_execute)
                if remaining > 0:
                    lines.append(f"\n{remaining} more features waiting (dependencies not yet met).\n")

                # Broadcast DAG progress
                total = dag_status.get("total", 0)
                completed = dag_status.get("completed", 0)
                in_progress = len(features_to_execute)
                await self.ws_manager.broadcast({
                    "type": "dag_progress",
                    "data": {"project_id": project_id, "total": total, "completed": completed, "in_progress": in_progress}
                })

                return {"content": [{"type": "text", "text": "".join(lines)}]}

            except Exception as e:
                self.logger.error(f"execute_ready_features tool error: {e}", exc_info=True)
                return {
                    "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                    "is_error": True,
                }

        # ═══════════════════════════════════════════════════════════
        # PLUGIN INTROSPECTION TOOL
        # ═══════════════════════════════════════════════════════════

        @tool(
            "list_plugin_capabilities",
            "List all agents, skills, commands, workflows, and phases available in a plugin. "
            "Use plugin_name to inspect a specific plugin, or omit to list all plugins. "
            "Helps you understand what resources each archetype plugin provides.",
            {"plugin_name": str},
        )
        async def list_plugin_capabilities_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            """Tool for inspecting plugin capabilities"""
            try:
                plugin_registry = getattr(self, 'plugin_registry', None)
                if plugin_registry is None:
                    return {
                        "content": [{"type": "text", "text": "Plugin registry not initialized."}],
                        "is_error": True,
                    }

                plugin_name = args.get("plugin_name", "")

                if plugin_name:
                    # Inspect specific plugin
                    caps = plugin_registry.list_capabilities(plugin_name)
                    if caps is None:
                        available = [p.name for p in plugin_registry.list_all()]
                        return {
                            "content": [{"type": "text", "text": f"Plugin '{plugin_name}' not found. Available: {', '.join(available)}"}],
                            "is_error": True,
                        }

                    lines = [
                        f"# Plugin: {caps.name} (v{caps.version})",
                        f"**Archetype:** {caps.archetype}",
                        f"**Description:** {caps.description}",
                        f"**Plugin Directory:** `{caps.plugin_dir}`",
                        "",
                        "## Phases",
                    ]
                    for phase in caps.phases:
                        phase_cfg = plugin_registry.get_phase_config(plugin_name, phase)
                        agents_str = ", ".join(phase_cfg.default_agents) if phase_cfg else "none"
                        lines.append(f"- **{phase}**: agents=[{agents_str}]")

                    if caps.agents:
                        lines.append("\n## Agents")
                        for a in caps.agents:
                            lines.append(f"- **{a['name']}** ({a['model']}): {a['description']}")

                    if caps.commands:
                        lines.append("\n## Commands")
                        for c in caps.commands:
                            lines.append(f"- `/{c}`")

                    if caps.workflows:
                        lines.append("\n## Workflows")
                        for w in caps.workflows:
                            lines.append(f"- `{w}`")

                    return {"content": [{"type": "text", "text": "\n".join(lines)}]}
                else:
                    # List all plugins
                    catalog = plugin_registry.build_plugin_catalog()
                    return {"content": [{"type": "text", "text": catalog}]}

            except Exception as e:
                self.logger.error(f"list_plugin_capabilities error: {e}", exc_info=True)
                return {
                    "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                    "is_error": True,
                }

        # ══════════════════════════════════════════════════════════
        # FEATURE LIFECYCLE MCP TOOLS
        # ══════════════════════════════════════════════════════════

        @tool(
            "create_features_batch",
            "Create multiple features with dependencies in one call. REQUIRED: project_id, features (JSON array). "
            "Each feature: {name, description, priority, depends_on: [feature_name_or_id, ...], acceptance_criteria: [...]}. "
            "Use feature names in depends_on — they will be resolved to IDs automatically.",
            {"project_id": str, "features": str},
        )
        async def create_features_batch_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            """Batch create features with dependency resolution."""
            try:
                import json as _json
                project_id = args.get("project_id")
                features_raw = args.get("features", "[]")

                if not project_id:
                    return {"content": [{"type": "text", "text": "Error: 'project_id' is required"}], "is_error": True}

                features_list = _json.loads(features_raw) if isinstance(features_raw, str) else features_raw

                # Create features in order, resolving name-based deps
                name_to_id: Dict[str, str] = {}
                created = []

                # First pass: load existing features to resolve deps to them
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"{_API_BASE}/api/projects/{project_id}/features", timeout=15.0)
                    existing = resp.json().get("features", [])
                    for f in existing:
                        name_to_id[f["name"]] = str(f["id"])

                for feat_data in features_list:
                    # Resolve depends_on names to IDs
                    raw_deps = feat_data.get("depends_on", [])
                    resolved_deps = []
                    for dep in raw_deps:
                        if dep in name_to_id:
                            resolved_deps.append(name_to_id[dep])
                        else:
                            resolved_deps.append(dep)  # assume it's already an ID

                    payload = {
                        "name": feat_data["name"],
                        "description": feat_data.get("description", ""),
                        "priority": feat_data.get("priority", 0),
                        "depends_on": resolved_deps,
                        "acceptance_criteria": feat_data.get("acceptance_criteria", []),
                        "estimated_complexity": feat_data.get("estimated_complexity"),
                    }

                    async with httpx.AsyncClient() as client:
                        resp = await client.post(
                            f"{_API_BASE}/api/projects/{project_id}/features",
                            json=payload,
                            timeout=15.0,
                        )
                        result = resp.json()
                        feat_id = result.get("feature", {}).get("id", "")
                        name_to_id[feat_data["name"]] = str(feat_id)
                        created.append(f"  - {feat_data['name']} (id: {str(feat_id)[:8]})")

                return {
                    "content": [{"type": "text", "text":
                        f"Created {len(created)} features for project {project_id}:\n" +
                        "\n".join(created)
                    }]
                }
            except Exception as e:
                self.logger.error(f"create_features_batch tool error: {e}", exc_info=True)
                return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}

        @tool(
            "get_dag_summary",
            "Get a comprehensive summary of the feature DAG: what's done, in progress, blocked, ready, completion %. REQUIRED: project_id.",
            {"project_id": str},
        )
        async def get_dag_summary_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            """Comprehensive DAG summary with per-status feature lists."""
            try:
                project_id = args.get("project_id")
                if not project_id:
                    return {"content": [{"type": "text", "text": "Error: 'project_id' is required"}], "is_error": True}

                dag = await FeatureDAG.from_database(project_id)
                summary = dag.status_summary()
                completion = dag.completion_percentage()
                groups = dag.get_parallel_groups()

                lines = [
                    f"## DAG Summary — {dag.feature_count} features\n",
                    f"Completion: {completion:.0f}%\n",
                    f"Planned: {summary.get('planned', 0)} | In Progress: {summary.get('in_progress', 0)} | "
                    f"Complete: {summary.get('complete', 0)} | Blocked: {summary.get('blocked', 0)} | "
                    f"Deferred: {summary.get('deferred', 0)}\n",
                    f"Waves: {len(groups)}\n",
                ]

                # List features by status
                for status in ["in_progress", "complete", "blocked", "planned", "deferred"]:
                    features_in_status = [f for f in dag._features.values() if f.status == status]
                    if features_in_status:
                        lines.append(f"\n### {status.upper()} ({len(features_in_status)})")
                        for f in features_in_status:
                            agent_info = f" [agent: {f.assigned_agent}]" if f.assigned_agent else ""
                            deps_info = f" (deps: {', '.join(f.depends_on)})" if f.depends_on else ""
                            lines.append(f"  - {f.name} (P{f.priority}){agent_info}{deps_info}")

                try:
                    critical_path = dag.critical_path()
                    if critical_path:
                        lines.append(f"\nCritical Path ({len(critical_path)} deep): {' → '.join(critical_path)}")
                except Exception:
                    pass

                return {"content": [{"type": "text", "text": "\n".join(lines)}]}
            except Exception as e:
                self.logger.error(f"get_dag_summary tool error: {e}", exc_info=True)
                return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}

        @tool(
            "get_ready_features",
            "Get features that are ready to execute (all dependencies satisfied, status=planned). REQUIRED: project_id.",
            {"project_id": str},
        )
        async def get_ready_features_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            """List features ready for execution."""
            try:
                project_id = args.get("project_id")
                if not project_id:
                    return {"content": [{"type": "text", "text": "Error: 'project_id' is required"}], "is_error": True}

                dag = await FeatureDAG.from_database(project_id)
                ready_ids = dag.get_ready_features()
                ready_features = [dag._features[fid] for fid in ready_ids if fid in dag._features]

                if not ready_features:
                    summary = dag.status_summary()
                    return {"content": [{"type": "text", "text":
                        f"No features ready. DAG: {summary.get('complete', 0)}/{dag.feature_count} complete, "
                        f"{summary.get('in_progress', 0)} in progress, {summary.get('blocked', 0)} blocked."
                    }]}

                lines = [f"## {len(ready_features)} features ready to execute:\n"]
                for f in sorted(ready_features, key=lambda x: x.priority):
                    deps = f", depends_on: {', '.join(f.depends_on)}" if f.depends_on else ""
                    lines.append(f"  - **{f.name}** (P{f.priority}, id: {f.id[:8]}){deps}")

                return {"content": [{"type": "text", "text": "\n".join(lines)}]}
            except Exception as e:
                self.logger.error(f"get_ready_features tool error: {e}", exc_info=True)
                return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}

        @tool(
            "get_next_wave",
            "Show what features will be unlocked after the currently in-progress features complete. REQUIRED: project_id.",
            {"project_id": str},
        )
        async def get_next_wave_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            """Predict what features unlock next based on current in-progress work."""
            try:
                project_id = args.get("project_id")
                if not project_id:
                    return {"content": [{"type": "text", "text": "Error: 'project_id' is required"}], "is_error": True}

                dag = await FeatureDAG.from_database(project_id)

                # Find in-progress features
                in_progress = [f for f in dag._features.values() if f.status == "in_progress"]
                in_progress_ids = {f.id for f in in_progress}

                if not in_progress:
                    ready = dag.get_ready_features()
                    return {"content": [{"type": "text", "text":
                        f"No features currently in progress. {len(ready)} features are ready to start."
                    }]}

                # Simulate: what becomes ready if all in-progress features complete?
                will_unlock = []
                for feat in dag._features.values():
                    if feat.status != "planned":
                        continue
                    # Check if all deps are either complete OR currently in-progress
                    all_satisfied = all(
                        dag._features.get(dep, FeatureNode(id="", name="")).status == "complete"
                        or dep in in_progress_ids
                        for dep in feat.depends_on
                    )
                    # But at least one dep is in-progress (not already all complete)
                    has_in_progress_dep = any(dep in in_progress_ids for dep in feat.depends_on)
                    if all_satisfied and has_in_progress_dep:
                        will_unlock.append(feat)

                lines = [
                    f"## Currently building ({len(in_progress)}):\n",
                ]
                for f in in_progress:
                    lines.append(f"  - {f.name} [agent: {f.assigned_agent or 'unassigned'}]")

                if will_unlock:
                    lines.append(f"\n## Will unlock when current wave completes ({len(will_unlock)}):\n")
                    for f in sorted(will_unlock, key=lambda x: x.priority):
                        blocking = [d for d in f.depends_on if d in in_progress_ids]
                        blocking_names = [dag._features[d].name for d in blocking if d in dag._features]
                        lines.append(f"  - **{f.name}** (P{f.priority}) — blocked by: {', '.join(blocking_names)}")
                else:
                    lines.append("\nNo additional features will unlock after current wave.")

                return {"content": [{"type": "text", "text": "\n".join(lines)}]}
            except Exception as e:
                self.logger.error(f"get_next_wave tool error: {e}", exc_info=True)
                return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}

        @tool(
            "get_feature_details",
            "Get detailed information about a specific feature. REQUIRED: project_id, feature_name.",
            {"project_id": str, "feature_name": str},
        )
        async def get_feature_details_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            """Deep view of a specific feature."""
            try:
                project_id = args.get("project_id")
                feature_name = args.get("feature_name", "")
                if not project_id or not feature_name:
                    return {"content": [{"type": "text", "text": "Error: 'project_id' and 'feature_name' required"}], "is_error": True}

                dag = await FeatureDAG.from_database(project_id)

                # Find by name or ID
                feat = None
                for f in dag._features.values():
                    if f.name == feature_name or f.id == feature_name or f.id.startswith(feature_name):
                        feat = f
                        break

                if not feat:
                    return {"content": [{"type": "text", "text": f"Feature '{feature_name}' not found"}], "is_error": True}

                # Get dependents (features that depend on this one)
                dependents = [f.name for f in dag._features.values() if feat.id in f.depends_on]

                # Get blocking features (incomplete deps)
                blocking = []
                for dep_id in feat.depends_on:
                    dep = dag._features.get(dep_id)
                    if dep and dep.status != "complete":
                        blocking.append(f"{dep.name} ({dep.status})")

                lines = [
                    f"## Feature: {feat.name}\n",
                    f"ID: {feat.id}",
                    f"Status: {feat.status}",
                    f"Priority: P{feat.priority}",
                    f"Category: {feat.category or 'none'}",
                    f"Complexity: {feat.estimated_complexity or 'unknown'}",
                    f"Agent: {feat.assigned_agent or 'unassigned'}",
                ]

                if feat.description:
                    lines.append(f"\nDescription: {feat.description}")

                if feat.acceptance_criteria:
                    lines.append("\nAcceptance Criteria:")
                    for ac in feat.acceptance_criteria:
                        lines.append(f"  - {ac}")

                if feat.depends_on:
                    dep_names = [dag._features[d].name if d in dag._features else d for d in feat.depends_on]
                    lines.append(f"\nDepends on: {', '.join(dep_names)}")

                if blocking:
                    lines.append(f"Blocked by: {', '.join(blocking)}")

                if dependents:
                    lines.append(f"Unlocks: {', '.join(dependents)}")

                if feat.started_at:
                    lines.append(f"\nStarted: {feat.started_at}")
                if feat.completed_at:
                    lines.append(f"Completed: {feat.completed_at}")

                return {"content": [{"type": "text", "text": "\n".join(lines)}]}
            except Exception as e:
                self.logger.error(f"get_feature_details tool error: {e}", exc_info=True)
                return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}

        @tool(
            "update_feature_status",
            "Update a feature's status. REQUIRED: project_id, feature_name, status (planned/in_progress/complete/blocked/deferred). OPTIONAL: agent_name.",
            {"project_id": str, "feature_name": str, "status": str, "agent_name": str},
        )
        async def update_feature_status_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            """Update feature status with proper DAG state management."""
            try:
                project_id = args.get("project_id")
                feature_name = args.get("feature_name", "")
                new_status = args.get("status", "")
                agent_name = args.get("agent_name")

                if not project_id or not feature_name or not new_status:
                    return {"content": [{"type": "text", "text": "Error: project_id, feature_name, and status required"}], "is_error": True}

                valid_statuses = ["planned", "in_progress", "complete", "blocked", "deferred"]
                if new_status not in valid_statuses:
                    return {"content": [{"type": "text", "text": f"Error: status must be one of {valid_statuses}"}], "is_error": True}

                dag = await FeatureDAG.from_database(project_id)

                # Find feature by name or ID
                feature_id = None
                for f in dag._features.values():
                    if f.name == feature_name or f.id == feature_name or f.id.startswith(feature_name):
                        feature_id = f.id
                        break

                if not feature_id:
                    return {"content": [{"type": "text", "text": f"Feature '{feature_name}' not found"}], "is_error": True}

                # Apply status change via DAG methods
                newly_ready = []
                if new_status == "in_progress":
                    dag.mark_in_progress(feature_id, agent_name)
                elif new_status == "complete":
                    newly_ready = dag.mark_complete(feature_id)
                elif new_status == "blocked":
                    dag.mark_blocked(feature_id, "Manually blocked")
                else:
                    dag._features[feature_id].status = new_status

                await dag.save_to_database(project_id)

                result = f"Feature '{feature_name}' → {new_status}"
                if newly_ready:
                    ready_names = [dag._features[r].name for r in newly_ready if r in dag._features]
                    result += f"\nNewly unblocked: {', '.join(ready_names)}"

                return {"content": [{"type": "text", "text": result}]}
            except Exception as e:
                self.logger.error(f"update_feature_status tool error: {e}", exc_info=True)
                return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}

        return [
            create_agent_tool,
            list_agents_tool,
            command_agent_tool,
            check_agent_status_tool,
            delete_agent_tool,
            interrupt_agent_tool,
            read_system_logs_tool,
            report_cost_tool,
            create_workspace_tool,
            list_workspaces_tool,
            onboard_project_tool,
            list_projects_tool,
            switch_project_tool,
            get_project_status_tool,
            start_phase_tool,
            complete_phase_tool,
            advance_phase_tool,
            list_features_tool,
            create_feature_tool,
            get_feature_dag_status_tool,
            execute_ready_features_tool,
            list_plugin_capabilities_tool,
            # Feature lifecycle tools
            create_features_batch_tool,
            get_dag_summary_tool,
            get_ready_features_tool,
            get_next_wave_tool,
            get_feature_details_tool,
            update_feature_status_tool,
        ]

    def _create_agent_can_use_tool(self, agent_id: uuid.UUID, agent_name: str):
        """
        Create a can_use_tool callback for a specific agent.

        Routes AskUserQuestion calls to the frontend via WebSocket,
        waits for user answers, and returns them to the agent.
        All other tools are auto-approved (per acceptEdits mode).
        """
        from claude_agent_sdk.types import PermissionResultAllow, PermissionResultDeny

        async def can_use_tool(tool_name: str, input_data: dict, context):
            if tool_name == "AskUserQuestion":
                self.logger.info(
                    f"Agent '{agent_name}' asking user a question: "
                    f"{len(input_data.get('questions', []))} questions"
                )

                # Broadcast question to frontend via WebSocket, tagged with agent info
                await self.ws_manager.broadcast({
                    "type": "ask_user_question",
                    "data": {
                        "agent_id": str(agent_id),
                        "agent_name": agent_name,
                        "questions": input_data.get("questions", []),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                })

                # Create a future to wait for the user's answer
                loop = asyncio.get_event_loop()
                future = loop.create_future()
                self._pending_agent_questions[str(agent_id)] = future

                try:
                    # Wait up to 5 minutes for user to answer
                    answers = await asyncio.wait_for(future, timeout=300)
                    self.logger.info(f"Agent '{agent_name}' received user answers: {list(answers.keys())}")

                    return PermissionResultAllow(
                        updated_input={
                            "questions": input_data.get("questions", []),
                            "answers": answers,
                        }
                    )
                except asyncio.TimeoutError:
                    self.logger.warning(f"Agent '{agent_name}' question timed out")
                    return PermissionResultDeny(
                        message="User did not respond within 5 minutes. Continue with your best judgment."
                    )
                finally:
                    self._pending_agent_questions.pop(str(agent_id), None)

            # Auto-approve all other tools
            return PermissionResultAllow(updated_input=input_data)

        return can_use_tool

    async def answer_agent_question(self, agent_id: str, answers: Dict[str, str]):
        """
        Receive user answers for a specific agent's AskUserQuestion call.

        Args:
            agent_id: UUID string of the agent that asked the question
            answers: Dict mapping question text to selected answer labels
        """
        future = self._pending_agent_questions.get(agent_id)
        if future and not future.done():
            future.set_result(answers)
            self.logger.info(f"Resolved pending question for agent {agent_id}")
        else:
            self.logger.warning(f"No pending question for agent {agent_id}")

    def build_phase_agent_prompt(self, phase: str, project_id: str) -> str:
        """
        Build a comprehensive system prompt for a phase-specific agent.

        Strategy (plugin-first):
        1. Look up project's plugin via PluginRegistry
        2. Use plugin's agent template as PRIMARY prompt (if available)
        3. Fall back to generic phase prompt template
        4. Inject project context and workflow guidance

        Args:
            phase: RAPIDS phase (research, analysis, plan, implement, deploy, sustain)
            project_id: Project UUID

        Returns:
            Complete system prompt string for the phase agent
        """
        parts = []

        # ── 1. Resolve project context ──
        project_name = "unknown"
        repo_path = ""
        archetype = ""
        plugin_name = ""
        rapids_dir = ""
        project_context_text = "No project context available."

        if hasattr(self, 'workspace_manager') and self.workspace_manager:
            ctx = self.workspace_manager._project_contexts.get(project_id, {})
            project_name = ctx.get("name", "unknown")
            repo_path = ctx.get("repo_path", "")
            archetype = ctx.get("archetype", "")
            # Resolve plugin_name: prefer plugin_id, fall back to archetype
            raw_plugin = ctx.get("plugin_id", "") or ""
            plugin_name = raw_plugin if raw_plugin and raw_plugin.lower() != "none" else archetype
            rapids_dir = f"{repo_path}/.rapids"

            project_context_text = (
                f"**Project:** {project_name}\n"
                f"**Repository:** `{repo_path}`\n"
                f"**Archetype:** {archetype}\n"
                f"**Plugin:** {plugin_name}\n"
                f"**RAPIDS Directory:** `{rapids_dir}`\n"
                f"**Phase Artifacts Directory:** `{rapids_dir}/{phase}/`\n"
                f"\nAll artifacts MUST be saved to `{rapids_dir}/{phase}/`."
            )

        # ── 2. Try plugin agent template FIRST (plugin-driven) ──
        plugin_agent_used = False
        plugin_registry = getattr(self, 'plugin_registry', None)

        self.logger.info(
            f"[build_phase_agent_prompt] plugin_registry={plugin_registry is not None}, "
            f"plugin_name='{plugin_name}', archetype='{archetype}', project_name='{project_name}'"
        )

        if plugin_registry and plugin_name:
            # Get the plugin's default agents for this phase
            phase_agents = plugin_registry.get_phase_agents(plugin_name, phase)
            if phase_agents:
                # Use the first (primary) agent template
                agent_tmpl = phase_agents[0]
                if agent_tmpl.system_prompt:
                    parts.append(agent_tmpl.system_prompt)
                    parts.append("\n\n---\n\n")
                    plugin_agent_used = True
                    self.logger.info(
                        f"Using plugin agent template '{agent_tmpl.name}' from '{plugin_name}' for {phase} phase"
                    )

        # ── 3. Load generic phase prompt (primary if no plugin agent, supplement if plugin used) ──
        phase_prompt_path = Path(__file__).parent.parent / "prompts" / "phase_prompts" / f"{phase}_prompt.md"
        if phase_prompt_path.exists():
            phase_prompt = phase_prompt_path.read_text()
        else:
            phase_prompt = f"You are executing the **{phase.capitalize()}** phase of the RAPIDS workflow."
            self.logger.warning(f"Phase prompt not found: {phase_prompt_path}")

        # Substitute template variables
        phase_prompt = phase_prompt.replace("{{PROJECT_NAME}}", project_name)
        phase_prompt = phase_prompt.replace("{{PROJECT_CONTEXT}}", project_context_text)

        # ── 4. Load workflow guidance from plugin ──
        plugin_supplement = ""
        if plugin_registry and plugin_name:
            try:
                workflow_path = plugin_registry.get_phase_workflow_path(plugin_name, phase)
                if workflow_path and workflow_path.exists():
                    workflow_text = workflow_path.read_text()
                    plugin_supplement = (
                        f"\n## Guided Workflow ({plugin_name} archetype)\n\n"
                        f"Follow this workflow structure for the {phase} phase:\n\n"
                        f"{workflow_text}"
                    )
                    self.logger.info(f"Loaded workflow guidance from {workflow_path}")
            except Exception as e:
                self.logger.warning(f"Failed to load workflow for {phase}/{plugin_name}: {e}")

        # Also inject the plugin's prompt_supplement if available
        if plugin_registry and plugin_name:
            phase_config = plugin_registry.get_phase_config(plugin_name, phase)
            if phase_config and phase_config.prompt_supplement:
                plugin_supplement += f"\n\n## Archetype Context ({plugin_name})\n\n{phase_config.prompt_supplement}"

        phase_prompt = phase_prompt.replace("{{PLUGIN_SUPPLEMENT}}", plugin_supplement)

        parts.append(phase_prompt)

        # ── 5. Enumerate available skills from plugin for agent awareness ──
        if plugin_registry and plugin_name:
            caps = plugin_registry.list_capabilities(plugin_name)
            if caps and caps.skills:
                skills_section = ["\n\n## Available Skills"]
                skills_section.append(
                    "You have access to the following skills via the Skill tool. "
                    "Use them when they match your current task — invoke with `/plugin:skill-name` "
                    "or let Claude auto-invoke based on context.\n"
                )
                for skill_name in caps.skills:
                    # Read the skill description from SKILL.md frontmatter
                    skill_desc = ""
                    skill_dir = plugin_registry.get_plugin_dir(plugin_name)
                    if skill_dir:
                        skill_md = skill_dir / "skills" / skill_name / "SKILL.md"
                        if skill_md.exists():
                            try:
                                content = skill_md.read_text()
                                if content.startswith("---"):
                                    fm_end = content.find("---", 3)
                                    if fm_end != -1:
                                        import yaml as _yaml
                                        fm = _yaml.safe_load(content[3:fm_end])
                                        skill_desc = fm.get("description", "") if isinstance(fm, dict) else ""
                            except Exception:
                                pass
                    skills_section.append(f"- **/{plugin_name}:{skill_name}** — {skill_desc}")

                parts.append("\n".join(skills_section))
                self.logger.info(f"Injected {len(caps.skills)} skill descriptions into agent prompt")

        # 6. Append existing artifacts context
        if repo_path:
            artifacts_dir = Path(repo_path) / ".rapids" / phase
            if artifacts_dir.exists():
                existing = [f.name for f in artifacts_dir.iterdir() if f.is_file()]
                if existing:
                    parts.append(f"\n\n## Existing Artifacts\nThese files already exist in `.rapids/{phase}/`: {', '.join(existing)}")

        return "\n".join(parts)

    async def create_agent(
        self, name: str, system_prompt: str, model: Optional[str] = None,
        subagent_template: Optional[str] = None, phase_metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Create a new agent.

        Args:
            name: Unique agent name
            system_prompt: Agent's system prompt (can be empty if using template)
            model: Optional model override
            subagent_template: Optional template name to use
            phase_metadata: Optional dict with phase, project_id, archetype for SDK plugin loading

        Returns:
            Dict with ok, agent_id, session_id, or error
        """
        try:
            # Handle template-based creation
            metadata = phase_metadata or {}
            allowed_tools = None  # Will use defaults if not specified

            if subagent_template:
                self.logger.info(f"Creating agent '{name}' using template '{subagent_template}'")

                # Fetch template
                template = self.subagent_registry.get_template(subagent_template)

                if not template:
                    # Template not found - provide helpful error
                    available = self.subagent_registry.get_available_names()
                    available_str = ', '.join(available) if available else 'None - create templates in .claude/agents/'
                    self.logger.error(f"❌ Template '{subagent_template}' not found")
                    self.logger.info(f"Available templates: {available_str}")
                    return {
                        "ok": False,
                        "error": f"Template '{subagent_template}' not found. Available: {available_str}",
                        "suggestion": "Create templates in .claude/agents/ directory or use manual agent creation"
                    }

                # Apply template configuration
                system_prompt = template.prompt_body
                if template.frontmatter.model:
                    model = template.frontmatter.model
                allowed_tools = template.frontmatter.tools

                # Add template metadata
                metadata = {
                    "template_name": template.frontmatter.name,
                    "template_color": template.frontmatter.color,
                }

                # Log template application
                if template.frontmatter.tools:
                    tool_count = len(template.frontmatter.tools)
                    self.logger.info(f"Applying template '{template.frontmatter.name}': {tool_count} tools, model={model or 'default'}")
                else:
                    self.logger.info(f"Applying template '{template.frontmatter.name}': all default tools, model={model or 'default'}")

            # Check if agent name already exists (scoped to this orchestrator)
            existing = await get_agent_by_name(self.orchestrator_agent_id, name)
            if existing:
                self.logger.warning(f"Attempted to create agent with duplicate name: {name}")
                return {
                    "ok": False,
                    "error": f"❌ Agent name '{name}' is already in use. Please choose a different name."
                }

            # Create agent in database (scoped to this orchestrator)
            # Use worktree path as working_dir if available (for parallel feature isolation)
            db_working_dir = metadata.get("worktree_path", self.working_dir)
            agent_id = await create_agent(
                orchestrator_agent_id=self.orchestrator_agent_id,
                name=name,
                model=model or config.DEFAULT_AGENT_MODEL,
                system_prompt=system_prompt,
                working_dir=db_working_dir,
                metadata=metadata,
            )

            # Initialize file tracker for this agent
            self.file_trackers[str(agent_id)] = FileTracker(
                agent_id, name, self.working_dir
            )

            # Initialize agent with greeting
            task_slug = f"{name}-greeting"
            entry_counter = {"count": 0}

            hooks_dict = self._build_hooks_for_agent(
                agent_id, name, task_slug, entry_counter
            )

            # Determine allowed tools
            if allowed_tools is not None:
                # Use tools from template
                tools_to_use = allowed_tools
            else:
                # Default allowed tools - comprehensive set for general work
                tools_to_use = [
                    "Read",
                    "Write",
                    "Edit",
                    "Bash",
                    "Glob",
                    "Grep",
                    "Task",
                    "WebFetch",
                    "WebSearch",
                    "BashOutput",
                    "SlashCommand",
                    "TodoWrite",
                    "KillShell",
                    "AskUserQuestion",
                    "Skill",
                ]

            default_disallowed = ["NotebookEdit", "ExitPlanMode"]

            # Pass auth credentials to ensure subprocess has access
            env_vars = {}
            if "ANTHROPIC_API_KEY" in os.environ:
                env_vars["ANTHROPIC_API_KEY"] = os.environ["ANTHROPIC_API_KEY"]
            if "CLAUDE_CODE_OAUTH_TOKEN" in os.environ:
                env_vars["CLAUDE_CODE_OAUTH_TOKEN"] = os.environ["CLAUDE_CODE_OAUTH_TOKEN"]

            # Only add can_use_tool for interactive agents (not builder agents)
            # Builder agents (name starts with "builder-") run autonomously
            # Use worktree path as cwd if available (for parallel feature isolation)
            agent_cwd = metadata.get("worktree_path", self.working_dir)

            agent_options = {
                "system_prompt": system_prompt,
                "model": model or config.DEFAULT_AGENT_MODEL,
                "cwd": agent_cwd,
                "hooks": hooks_dict,
                "allowed_tools": tools_to_use,
                "disallowed_tools": default_disallowed,
                "permission_mode": "acceptEdits",
                "env": env_vars,
                "setting_sources": ["user", "project"],  # Required for SDK skill auto-discovery
            }

            # Inject feature management MCP tools for phase agents with a project_id
            phase_project_id = metadata.get("project_id")
            if phase_project_id:
                feature_tools = self._create_feature_tools(phase_project_id)
                features_mcp = create_sdk_mcp_server(
                    name="features", version="1.0.0", tools=feature_tools
                )
                agent_options["mcp_servers"] = {"features": features_mcp}
                # Add feature tool names to allowed tools
                feature_tool_names = [
                    "mcp__features__create_features",
                    "mcp__features__list_project_features",
                    "mcp__features__validate_feature_dag",
                    "mcp__features__delete_feature",
                ]
                tools_to_use.extend(feature_tool_names)
                agent_options["allowed_tools"] = tools_to_use
                self.logger.info(f"Injected feature MCP tools for agent '{name}' (project: {phase_project_id})")
            if agent_cwd != self.working_dir:
                self.logger.info(f"Agent '{name}' will work in worktree: {agent_cwd}")

            # Load plugin for SDK auto-discovery of skills, agents, commands
            # This makes plugin skills invocable by the agent (e.g. /greenfield:web-research)
            plugin_registry = getattr(self, 'plugin_registry', None)
            if plugin_registry and metadata.get("archetype"):
                plugin_dir = plugin_registry.get_plugin_dir(metadata["archetype"])
                if plugin_dir:
                    agent_options["plugins"] = [{"type": "local", "path": str(plugin_dir)}]
                    # Also include Skill in allowed tools so agent can invoke skills
                    if "Skill" not in tools_to_use:
                        tools_to_use.append("Skill")
                        agent_options["allowed_tools"] = tools_to_use
                    self.logger.info(f"Loaded SDK plugin for agent '{name}': {plugin_dir}")

            if not name.startswith("builder-"):
                agent_options["can_use_tool"] = self._create_agent_can_use_tool(agent_id, name)

            options = ClaudeAgentOptions(**agent_options)

            async with ClaudeSDKClient(options=options) as client:
                await client.query("Ready. Awaiting instructions.")

                session_id = await self._process_agent_messages(
                    client, agent_id, name, task_slug, entry_counter
                )

            # Update session in database
            await update_agent_session(agent_id, session_id)

            # Broadcast creation
            await self.ws_manager.broadcast_agent_created(
                {
                    "id": str(agent_id),
                    "name": name,
                    "model": model or config.DEFAULT_AGENT_MODEL,
                    "status": "idle",
                }
            )

            self.logger.info(f"Created agent '{name}' with ID {agent_id}")

            return {"ok": True, "agent_id": str(agent_id), "session_id": session_id}

        except Exception as e:
            self.logger.error(f"Failed to create agent: {e}", exc_info=True)
            return {"ok": False, "error": str(e)}

    async def command_agent(
        self, agent_id: uuid.UUID, command: str, task_slug: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send command to agent.

        Args:
            agent_id: UUID of agent
            command: Command text
            task_slug: Optional task identifier

        Returns:
            Dict with ok, task_slug, or error
        """
        try:
            agent = await get_agent(agent_id)
            if not agent:
                return {"ok": False, "error": "Agent not found"}

            # Ensure file tracker exists for this agent
            if str(agent_id) not in self.file_trackers:
                self.file_trackers[str(agent_id)] = FileTracker(
                    agent_id, agent.name, agent.working_dir or self.working_dir
                )

            # Generate task slug if not provided
            if not task_slug:
                # Create slug from command (first 50 chars, kebab-case)
                slug_base = re.sub(r"[^a-z0-9]+", "-", command[:50].lower()).strip("-")
                task_slug = f"{slug_base}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

            entry_counter = {"count": 0}

            # Insert prompt to database
            prompt_id = await insert_prompt(
                agent_id=agent_id,
                task_slug=task_slug,
                author="orchestrator_agent",
                prompt_text=command,
                session_id=agent.session_id,
            )

            # Generate AI summary in background
            asyncio.create_task(self._summarize_and_update_prompt(prompt_id, command))

            # Build hooks — include cleanup hook so agent gets archived on completion
            hooks_dict = self._build_hooks_for_agent(
                agent_id, agent.name, task_slug, entry_counter,
                include_cleanup=True,
            )

            # Default allowed tools - comprehensive set for general work
            default_allowed = [
                "Read",
                "Write",
                "Edit",
                "Bash",
                "Glob",
                "Grep",
                "Task",
                "WebFetch",
                "WebSearch",
                "BashOutput",
                "SlashCommand",
                "TodoWrite",
                "KillShell",
                "AskUserQuestion",
                "Skill",
            ]

            default_disallowed = ["NotebookEdit", "ExitPlanMode"]

            # Pass auth credentials to ensure subprocess has access
            env_vars = {}
            if "ANTHROPIC_API_KEY" in os.environ:
                env_vars["ANTHROPIC_API_KEY"] = os.environ["ANTHROPIC_API_KEY"]
            if "CLAUDE_CODE_OAUTH_TOKEN" in os.environ:
                env_vars["CLAUDE_CODE_OAUTH_TOKEN"] = os.environ["CLAUDE_CODE_OAUTH_TOKEN"]

            # Build options with session resume (use Pydantic model properties)
            options = ClaudeAgentOptions(
                system_prompt=agent.system_prompt,
                model=agent.model,
                cwd=agent.working_dir,
                resume=agent.session_id,
                hooks=hooks_dict,
                max_turns=config.MAX_AGENT_TURNS,
                allowed_tools=default_allowed,
                disallowed_tools=default_disallowed,
                permission_mode="acceptEdits",
                env=env_vars,  # Ensure API key is available to subprocess
                setting_sources=["project"],  # Load CLAUDE.md and slash commands
            )

            # Update status to executing
            await update_agent_status(agent_id, "executing")
            await self.ws_manager.broadcast_agent_status_change(
                str(agent_id), "idle", "executing"
            )

            # Execute agent
            async with ClaudeSDKClient(options=options) as client:
                # Track in active clients for interrupt
                with self.active_clients_lock:
                    self.active_clients[agent.name] = client

                await client.query(command)

                session_id = await self._process_agent_messages(
                    client, agent_id, agent.name, task_slug, entry_counter
                )

                # Remove from active clients
                with self.active_clients_lock:
                    self.active_clients.pop(agent.name, None)

            # Update session and status
            await update_agent_session(agent_id, session_id)

            self.logger.info(f"Agent '{agent.name}' completed task: {task_slug}")

            # ── Auto-merge for builder agents ──
            builder_info = self._builder_registry.get(agent.name)
            if builder_info and builder_info.get("worktree_path"):
                asyncio.create_task(
                    self._auto_merge_and_progress(agent.name, builder_info)
                )

            # Agent cleanup (mark completed + archive) is handled by the Stop hook's
            # cleanup callback (_create_cleanup_hook). This runs when the Claude SDK
            # session actually ends, which is the definitive signal.

            # Notify orchestrator ONLY for non-builder agents.
            if self._on_agent_complete_callback and not builder_info:
                summary = f"Agent '{agent.name}' has completed its task (task: {task_slug})."
                asyncio.create_task(
                    self._on_agent_complete_callback(agent.name, summary)
                )

            return {"ok": True, "task_slug": task_slug}

        except Exception as e:
            self.logger.error(f"Failed to command agent: {e}", exc_info=True)
            await update_agent_status(agent_id, "blocked")
            return {"ok": False, "error": str(e)}

    async def _auto_merge_and_progress(self, agent_name: str, builder_info: Dict[str, str]):
        """
        Auto-merge a completed builder's worktree branch and trigger next wave.

        Steps:
        1. Merge the feature branch (rapids/<feature-id>) into main
        2. Update the feature status in the DAG to 'complete'
        3. Clean up the worktree
        4. Check for newly unblocked features
        5. Launch next wave if features are ready
        6. Broadcast progress to frontend
        """
        from .git_worktree import GitWorktreeManager
        import httpx

        feature_id = builder_info["feature_id"]
        feature_name = builder_info.get("feature_name", feature_id)
        project_id = builder_info["project_id"]
        repo_path = builder_info["repo_path"]
        worktree_branch = builder_info.get("worktree_branch", "")

        self.logger.info(f"[AutoMerge] Starting merge for feature '{feature_id}' (branch: {worktree_branch})")

        # 1. Merge worktree branch back to main
        merge_success = False
        merge_message = ""
        try:
            git_mgr = GitWorktreeManager(repo_path)
            success, msg = git_mgr.merge_worktree(feature_id, delete_after=True)
            merge_success = success
            merge_message = msg
            if success:
                self.logger.info(f"[AutoMerge] Merged '{feature_id}': {msg}")
            else:
                self.logger.warning(f"[AutoMerge] Merge conflict for '{feature_id}': {msg}")
        except Exception as e:
            merge_message = f"Merge failed: {e}"
            self.logger.error(f"[AutoMerge] Merge exception for '{feature_id}': {e}")

        # 2. Update feature status in DAG
        _API_BASE = f"http://127.0.0.1:{config.BACKEND_PORT}"
        try:
            async with httpx.AsyncClient() as client:
                new_status = "complete" if merge_success else "blocked"
                await client.post(
                    f"{_API_BASE}/api/projects/{project_id}/dag/features/{feature_id}/status",
                    json={"status": new_status},
                    timeout=10.0,
                )
                self.logger.info(f"[AutoMerge] DAG updated: {feature_id} → {new_status}")
        except Exception as e:
            self.logger.error(f"[AutoMerge] Failed to update DAG for '{feature_id}': {e}")

        # 3. Broadcast merge result to frontend
        await self.ws_manager.broadcast({
            "type": "feature_merged" if merge_success else "feature_merge_failed",
            "data": {
                "project_id": project_id,
                "feature_id": feature_id,
                "feature_name": feature_name,
                "agent_name": agent_name,
                "branch": worktree_branch,
                "message": merge_message,
                "success": merge_success,
            }
        })

        # 3b. Send merge notification as a chat message so it's visible in the UI
        from datetime import datetime, timezone
        merge_icon = "✅" if merge_success else "❌"
        merge_chat_msg = (
            f"{merge_icon} **Feature Merged:** `{feature_name}`\n"
            f"Branch: `{worktree_branch}` → main\n"
            f"{merge_message}"
        ) if merge_success else (
            f"{merge_icon} **Merge Failed:** `{feature_name}`\n"
            f"Branch: `{worktree_branch}`\n"
            f"{merge_message}"
        )
        await self.ws_manager.broadcast({
            "type": "orchestrator_chat",
            "message": {
                "id": str(uuid.uuid4()),
                "orchestrator_agent_id": str(self.orchestrator_agent_id),
                "sender_type": "system",
                "receiver_type": "user",
                "message": merge_chat_msg,
                "agent_id": None,
                "metadata": {
                    "event": "feature_merged" if merge_success else "feature_merge_failed",
                    "feature_id": feature_id,
                    "feature_name": feature_name,
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        })

        # 4. Clean up builder registry
        self._builder_registry.pop(agent_name, None)

        # 5. Check for newly unblocked features and launch next wave
        if merge_success:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{_API_BASE}/api/projects/{project_id}/dag",
                        timeout=10.0,
                    )
                    dag_data = resp.json()

                ready_features = dag_data.get("ready_features", [])
                dag_status = dag_data.get("dag_status", {})
                total = dag_status.get("total", 0)
                completed = dag_status.get("completed", 0)
                in_progress = dag_status.get("in_progress", 0)

                self.logger.info(
                    f"[AutoMerge] DAG progress: {completed}/{total} complete, "
                    f"{in_progress} in progress, {len(ready_features)} ready"
                )

                # Broadcast progress
                await self.ws_manager.broadcast({
                    "type": "dag_progress",
                    "data": {
                        "project_id": project_id,
                        "total": total,
                        "completed": completed,
                        "in_progress": in_progress,
                        "ready": len(ready_features),
                    }
                })

                # If there are ready features and no running builders, launch next wave
                running_builders = len([
                    b for b in self._builder_registry.values()
                    if b["project_id"] == project_id
                ])

                if ready_features and running_builders == 0:
                    self.logger.info(
                        f"[AutoMerge] Wave complete! Launching next wave: "
                        f"{len(ready_features)} features ready"
                    )
                    # Broadcast wave transition
                    await self.ws_manager.broadcast({
                        "type": "wave_transition",
                        "data": {
                            "project_id": project_id,
                            "completed_feature": feature_id,
                            "next_features": ready_features,
                            "total": total,
                            "completed": completed,
                        }
                    })

                    # Send wave transition chat notification
                    ready_names = []
                    for rid in ready_features:
                        for f in dag_data.get("dag", {}).get("features", []):
                            if f.get("id") == rid:
                                ready_names.append(f.get("name", rid[:8]))
                                break
                    await self.ws_manager.broadcast({
                        "type": "orchestrator_chat",
                        "message": {
                            "id": str(uuid.uuid4()),
                            "orchestrator_agent_id": str(self.orchestrator_agent_id),
                            "sender_type": "system",
                            "receiver_type": "user",
                            "message": (
                                f"🔄 **Wave Complete** — {completed}/{total} features done\n"
                                f"Next up: {', '.join(ready_names[:5])}"
                                + (f" and {len(ready_names) - 5} more" if len(ready_names) > 5 else "")
                            ),
                            "agent_id": None,
                            "metadata": {"event": "wave_transition"},
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    })

                    # Wave transition is handled via WebSocket events + chat notifications.
                    # Do NOT call _on_agent_complete_callback here — it injects messages
                    # into the orchestrator conversation causing re-execution loops.

                elif completed == total:
                    self.logger.info(f"[AutoMerge] All features complete! DAG 100%")
                    await self.ws_manager.broadcast({
                        "type": "dag_complete",
                        "data": {
                            "project_id": project_id,
                            "total": total,
                            "message": f"All {total} features implemented and merged!",
                        }
                    })
                    # Send completion chat notification
                    await self.ws_manager.broadcast({
                        "type": "orchestrator_chat",
                        "message": {
                            "id": str(uuid.uuid4()),
                            "orchestrator_agent_id": str(self.orchestrator_agent_id),
                            "sender_type": "system",
                            "receiver_type": "user",
                            "message": (
                                f"🎉 **Implementation Complete!**\n\n"
                                f"All **{total}** features have been implemented and merged to main.\n"
                                f"The project is ready to advance to the **Deploy** phase."
                            ),
                            "agent_id": None,
                            "metadata": {"event": "dag_complete", "total": total},
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    })

            except Exception as e:
                self.logger.error(f"[AutoMerge] Failed to check next wave: {e}")

    def _create_feature_tools(self, project_id: str) -> List:
        """Create feature management MCP tools scoped to a specific project.

        These tools are injected into planner/phase agents so they can
        create and manage features directly in the database.
        """

        @tool(
            "create_features",
            "Create multiple features with dependencies for the project. "
            "Pass a JSON array of features. Each feature: {name, description, priority (int), "
            "depends_on: [feature_name, ...], acceptance_criteria: [...], estimated_complexity: 'low'|'medium'|'high'}. "
            "Use feature NAMES (not IDs) in depends_on — they resolve automatically.",
            {"features": str},
        )
        async def create_features_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            try:
                import json as _json
                features_raw = args.get("features", "[]")
                features_list = _json.loads(features_raw) if isinstance(features_raw, str) else features_raw

                if not features_list:
                    return {"content": [{"type": "text", "text": "Error: features array is empty"}], "is_error": True}

                # Resolve name-based dependencies
                name_to_id: Dict[str, str] = {}

                # Load existing features first
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"{_API_BASE}/api/projects/{project_id}/features", timeout=15.0)
                    for f in resp.json().get("features", []):
                        name_to_id[f["name"]] = str(f["id"])

                created = []
                for feat in features_list:
                    # Resolve depends_on names to IDs
                    raw_deps = feat.get("depends_on", [])
                    resolved_deps = [name_to_id.get(d, d) for d in raw_deps]

                    payload = {
                        "name": feat["name"],
                        "description": feat.get("description", ""),
                        "priority": feat.get("priority", 0),
                        "depends_on": resolved_deps,
                        "acceptance_criteria": feat.get("acceptance_criteria", []),
                        "estimated_complexity": feat.get("estimated_complexity"),
                    }

                    async with httpx.AsyncClient() as client:
                        resp = await client.post(
                            f"{_API_BASE}/api/projects/{project_id}/features",
                            json=payload, timeout=15.0,
                        )
                        result = resp.json()
                        fid = result.get("feature", {}).get("id", "")
                        name_to_id[feat["name"]] = str(fid)
                        created.append(f"  - {feat['name']} (id: {str(fid)[:8]})")

                return {"content": [{"type": "text", "text":
                    f"Created {len(created)} features:\n" + "\n".join(created)
                }]}
            except Exception as e:
                self.logger.error(f"create_features tool error: {e}", exc_info=True)
                return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}

        @tool(
            "list_project_features",
            "List all features for this project with their status, dependencies, and priority.",
            {},
        )
        async def list_features_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            try:
                dag = await FeatureDAG.from_database(project_id)
                if dag.feature_count == 0:
                    return {"content": [{"type": "text", "text": "No features yet. Use create_features to add them."}]}

                lines = [f"## {dag.feature_count} features:\n"]
                for f in sorted(dag._features.values(), key=lambda x: x.priority):
                    deps = f", deps: [{', '.join(f.depends_on)}]" if f.depends_on else ""
                    lines.append(f"  - **{f.name}** (P{f.priority}, {f.status}){deps}")

                summary = dag.status_summary()
                lines.append(f"\nSummary: {summary}")
                return {"content": [{"type": "text", "text": "\n".join(lines)}]}
            except Exception as e:
                return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}

        @tool(
            "validate_feature_dag",
            "Validate the feature DAG: check for cycles, missing dependencies, and structural issues.",
            {},
        )
        async def validate_dag_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            try:
                dag = await FeatureDAG.from_database(project_id)
                if dag.feature_count == 0:
                    return {"content": [{"type": "text", "text": "No features to validate."}]}

                errors = dag.validate()
                if not errors:
                    groups = dag.get_parallel_groups()
                    return {"content": [{"type": "text", "text":
                        f"DAG is valid. {dag.feature_count} features in {len(groups)} waves. "
                        f"Ready to execute: {len(dag.get_ready_features())} features."
                    }]}
                else:
                    return {"content": [{"type": "text", "text":
                        f"DAG has {len(errors)} issues:\n" + "\n".join(f"  - {e}" for e in errors)
                    }], "is_error": True}
            except Exception as e:
                return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}

        @tool(
            "delete_feature",
            "Delete a feature by name. REQUIRED: feature_name.",
            {"feature_name": str},
        )
        async def delete_feature_tool(args: Dict[str, Any]) -> Dict[str, Any]:
            try:
                feature_name = args.get("feature_name", "")
                if not feature_name:
                    return {"content": [{"type": "text", "text": "Error: feature_name is required"}], "is_error": True}

                # Find feature by name
                dag = await FeatureDAG.from_database(project_id)
                feature_id = None
                for f in dag._features.values():
                    if f.name == feature_name:
                        feature_id = f.id
                        break

                if not feature_id:
                    return {"content": [{"type": "text", "text": f"Feature '{feature_name}' not found"}], "is_error": True}

                # Delete from DB
                from .database import get_connection
                async with get_connection() as conn:
                    await conn.execute(
                        "DELETE FROM features WHERE id = $1 AND project_id = $2",
                        uuid.UUID(feature_id), uuid.UUID(project_id),
                    )

                return {"content": [{"type": "text", "text": f"Deleted feature '{feature_name}'"}]}
            except Exception as e:
                return {"content": [{"type": "text", "text": f"Error: {str(e)}"}], "is_error": True}

        return [create_features_tool, list_features_tool, validate_dag_tool, delete_feature_tool]

    def _create_cleanup_hook(self, agent_id: uuid.UUID, agent_name: str):
        """Create a Stop hook that handles ALL post-completion work.

        This is the SINGLE definitive cleanup point. When an agent stops:
        1. Mark the agent as completed + archive it
        2. For builders: mark the feature as complete in the DB
        3. For builders: trigger auto-merge if worktree exists
        4. Broadcast all events to frontend
        """
        async def cleanup_hook(
            input_data: Dict[str, Any],
            tool_use_id: Optional[str],
            context: Any,
        ) -> Dict[str, Any]:
            self.logger.info(f"[Cleanup] === START cleanup for '{agent_name}' (id={agent_id}) ===")

            # Step 1: Load builder_info BEFORE archiving
            builder_info = self._builder_registry.pop(agent_name, None)
            if builder_info:
                self.logger.info(f"[Cleanup] Found builder_info in memory registry for '{agent_name}'")
            else:
                self.logger.info(f"[Cleanup] No memory registry entry, loading from DB for '{agent_name}' (id={agent_id})...")
                try:
                    from .database import get_connection
                    async with get_connection() as conn:
                        # Query by name (most recent) as fallback — agent_id may be stale
                        row = await conn.fetchrow(
                            "SELECT metadata FROM agents WHERE id = $1", agent_id
                        )
                        if not row:
                            row = await conn.fetchrow(
                                "SELECT metadata FROM agents WHERE name = $1 ORDER BY created_at DESC LIMIT 1",
                                agent_name,
                            )
                    if row and row["metadata"]:
                        meta = row["metadata"]
                        if isinstance(meta, str):
                            meta = json.loads(meta)
                        if isinstance(meta, dict):
                            builder_info = meta.get("builder_info")
                        self.logger.info(f"[Cleanup] DB metadata: builder_info={'FOUND' if builder_info else 'NOT found'}")
                    else:
                        self.logger.warning(f"[Cleanup] No DB row found for agent '{agent_name}'")
                except Exception as e:
                    self.logger.error(f"[Cleanup] DB metadata load FAILED: {e}")

            # Step 2: Archive the agent (each step independent — errors don't block others)
            try:
                await update_agent_status(agent_id, "completed")
                await delete_agent(agent_id)
                self.logger.info(f"[Cleanup] Agent '{agent_name}' archived")
            except Exception as e:
                self.logger.error(f"[Cleanup] Archive failed: {e}")

            try:
                await self.ws_manager.broadcast_agent_status_change(
                    str(agent_id), "executing", "completed"
                )
                await self.ws_manager.broadcast({
                    "type": "agent_deleted",
                    "data": {"agent_id": str(agent_id), "agent_name": agent_name},
                })
            except Exception as e:
                self.logger.error(f"[Cleanup] Broadcast failed: {e}")

            # Step 3: For builder agents — mark feature complete
            if builder_info:
                feature_id = builder_info.get("feature_id", "")
                feature_name = builder_info.get("feature_name", "")
                project_id = builder_info.get("project_id", "")

                self.logger.info(f"[Cleanup] Builder '{agent_name}' → feature '{feature_name}' (fid={feature_id[:8]}, pid={project_id[:8]})")

                # Mark feature as complete in DB
                try:
                    from .rapids_database import update_feature_dag_status
                    result = await update_feature_dag_status(
                        uuid.UUID(project_id), feature_id, "complete",
                        assigned_agent=agent_name,
                    )
                    self.logger.info(f"[Cleanup] Feature '{feature_name}' → COMPLETE (result={'ok' if result else 'None'})")
                except Exception as feat_err:
                    self.logger.error(f"[Cleanup] Feature update FAILED: {feat_err}", exc_info=True)

                # Broadcast feature merged (runs regardless of DB update success)
                try:
                    await self.ws_manager.broadcast({
                        "type": "feature_merged",
                        "data": {
                            "project_id": project_id,
                            "feature_id": feature_id,
                            "feature_name": feature_name,
                            "agent_name": agent_name,
                            "success": True,
                            "message": f"Feature '{feature_name}' completed by {agent_name}",
                        }
                    })

                    from datetime import datetime, timezone
                    await self.ws_manager.broadcast({
                        "type": "orchestrator_chat",
                        "message": {
                            "id": str(uuid.uuid4()),
                            "orchestrator_agent_id": str(self.orchestrator_agent_id),
                            "sender_type": "system",
                            "receiver_type": "user",
                            "message": f"✅ **Feature Complete:** `{feature_name}` — by {agent_name}",
                            "agent_id": None,
                            "metadata": {"event": "feature_merged", "feature_id": feature_id},
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    })
                except Exception as bc_err:
                    self.logger.error(f"[Cleanup] Broadcast failed: {bc_err}")

                # Check DAG progress and broadcast
                try:
                    dag = await FeatureDAG.from_database(project_id)
                    summary = dag.status_summary()
                    total = dag.feature_count
                    completed = summary.get("complete", 0)
                    ready = dag.get_ready_features()

                    self.logger.info(f"[Cleanup] DAG: {completed}/{total} complete, {len(ready)} ready")

                    await self.ws_manager.broadcast({
                        "type": "dag_progress",
                        "data": {
                            "project_id": project_id,
                            "total": total,
                            "completed": completed,
                            "in_progress": summary.get("in_progress", 0),
                            "ready": len(ready),
                        }
                    })

                    if completed == total and total > 0:
                        await self.ws_manager.broadcast({
                            "type": "dag_complete",
                            "data": {"project_id": project_id, "total": total},
                        })
                        await self.ws_manager.broadcast({
                            "type": "orchestrator_chat",
                            "message": {
                                "id": str(uuid.uuid4()),
                                "orchestrator_agent_id": str(self.orchestrator_agent_id),
                                "sender_type": "system",
                                "receiver_type": "user",
                                "message": f"🎉 **All {total} features complete!** Ready to advance to Deploy.",
                                "agent_id": None,
                                "metadata": {"event": "dag_complete"},
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            },
                        })
                    elif ready:
                        await self.ws_manager.broadcast({
                            "type": "wave_transition",
                            "data": {
                                "project_id": project_id,
                                "next_features": ready,
                                "total": total,
                                "completed": completed,
                            },
                        })
                except Exception as dag_err:
                    self.logger.error(f"[Cleanup] DAG progress check failed: {dag_err}")

            else:
                self.logger.info(f"[Cleanup] No builder_info found — non-builder agent '{agent_name}', skip feature update")

            self.logger.info(f"[Cleanup] === END cleanup for '{agent_name}' ===")
            return {}

        return cleanup_hook

    def _build_hooks_for_agent(
        self,
        agent_id: uuid.UUID,
        agent_name: str,
        task_slug: str,
        entry_counter: Dict[str, int],
        include_cleanup: bool = False,
    ) -> Dict[str, Any]:
        """
        Build hooks dictionary for agent.

        Args:
            agent_id: UUID of agent
            agent_name: Name of the agent
            task_slug: Task identifier
            entry_counter: Mutable counter dict

        Returns:
            Hooks dict for ClaudeAgentOptions
        """
        # Get file tracker for this agent
        file_tracker = self.file_trackers.get(str(agent_id))

        # Build PostToolUse hooks list
        post_tool_hooks = [
            create_post_tool_hook(
                agent_id,
                agent_name,
                task_slug,
                entry_counter,
                self.logger,
                self.ws_manager,
            )
        ]

        # Add file tracking hook if file_tracker exists
        if file_tracker:
            post_tool_hooks.append(
                create_post_tool_file_tracking_hook(
                    file_tracker,
                    agent_id,
                    agent_name,
                    self.logger,
                )
            )

        return {
            "PreToolUse": [
                HookMatcher(
                    hooks=[
                        create_pre_tool_hook(
                            agent_id,
                            agent_name,
                            task_slug,
                            entry_counter,
                            self.logger,
                            self.ws_manager,
                        )
                    ]
                )
            ],
            "PostToolUse": [HookMatcher(hooks=post_tool_hooks)],
            "UserPromptSubmit": [
                HookMatcher(
                    hooks=[
                        create_user_prompt_hook(
                            agent_id,
                            agent_name,
                            task_slug,
                            entry_counter,
                            self.logger,
                            self.ws_manager,
                        )
                    ]
                )
            ],
            "Stop": [
                HookMatcher(
                    hooks=[
                        create_stop_hook(
                            agent_id,
                            agent_name,
                            task_slug,
                            entry_counter,
                            self.logger,
                            self.ws_manager,
                        ),
                    ] + ([self._create_cleanup_hook(agent_id, agent_name)] if include_cleanup else [])
                )
            ],
            "SubagentStop": [
                HookMatcher(
                    hooks=[
                        create_subagent_stop_hook(
                            agent_id,
                            agent_name,
                            task_slug,
                            entry_counter,
                            self.logger,
                            self.ws_manager,
                        )
                    ]
                )
            ],
            "PreCompact": [
                HookMatcher(
                    hooks=[
                        create_pre_compact_hook(
                            agent_id,
                            agent_name,
                            task_slug,
                            entry_counter,
                            self.logger,
                            self.ws_manager,
                        )
                    ]
                )
            ],
        }

    async def _process_agent_messages(
        self,
        client: ClaudeSDKClient,
        agent_id: uuid.UUID,
        agent_name: str,
        task_slug: str,
        entry_counter: Dict[str, int],
    ) -> Optional[str]:
        """
        Process agent messages and log to database.

        Args:
            client: Claude SDK client
            agent_id: UUID of agent
            agent_name: Name of agent
            task_slug: Task identifier
            entry_counter: Mutable counter

        Returns:
            Final session_id
        """
        session_id = None
        total_input_tokens = 0
        total_output_tokens = 0
        total_cost = 0.0
        estimated_output_chars = 0  # Track chars for incremental token estimate
        last_text_block_id = None  # Track last TextBlock for file tracking attachment
        text_block_count = 0
        thinking_block_count = 0
        tool_use_block_count = 0

        try:
            self.logger.debug(f"[AgentManager] Starting message processing for agent={agent_name} task={task_slug}")
            async for message in client.receive_response():
                self.logger.debug(f"[AgentManager] Received message type: {type(message).__name__}")

                if isinstance(message, SystemMessage):
                    # SystemMessage has subtype and data fields (not content)
                    # Log it with full details to understand what's happening
                    subtype = getattr(message, 'subtype', 'unknown')
                    data = getattr(message, 'data', {})

                    self.logger.warning(
                        f"[AgentManager] SystemMessage received for agent={agent_name} task={task_slug}:\n"
                        f"  Subtype: {subtype}\n"
                        f"  Data: {data}\n"
                    )

                    # SystemMessages are informational - log but don't process as agent output
                    continue

                if isinstance(message, AssistantMessage):
                    self.logger.debug(f"[AgentManager] AssistantMessage has {len(message.content)} blocks")
                    for block in message.content:
                        entry_index = entry_counter["count"]
                        entry_counter["count"] += 1
                        self.logger.debug(f"[AgentManager] Processing block type: {type(block).__name__}")

                        if isinstance(block, TextBlock):
                            text_block_count += 1
                            block_id = await insert_message_block(
                                agent_id=agent_id,
                                task_slug=task_slug,
                                entry_index=entry_index,
                                block_type="text",
                                content=block.text,
                                payload={"text": block.text},
                            )

                            # Track this as the last TextBlock for file tracking attachment
                            last_text_block_id = block_id

                            # Spawn async summarization
                            asyncio.create_task(
                                self._summarize_and_update_block(
                                    block_id, agent_id, "text", {"content": block.text}
                                )
                            )

                            # Broadcast agent text response via WebSocket
                            await self.ws_manager.broadcast_agent_log(
                                {
                                    "id": str(block_id),
                                    "agent_id": str(agent_id),
                                    "agent_name": agent_name,
                                    "task_slug": task_slug,
                                    "entry_index": entry_index,
                                    "event_category": "response",
                                    "event_type": "TextBlock",
                                    "content": block.text,
                                    "summary": block.text,
                                    "payload": {"text": block.text},
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                }
                            )
                            self.logger.debug(
                                f"Broadcast TextBlock for agent {agent_name}"
                            )

                            # Accumulate chars for incremental token estimate
                            estimated_output_chars += len(block.text)

                        elif isinstance(block, ThinkingBlock):
                            thinking_block_count += 1
                            block_id = await insert_message_block(
                                agent_id=agent_id,
                                task_slug=task_slug,
                                entry_index=entry_index,
                                block_type="thinking",
                                content=block.thinking,
                                payload={"thinking": block.thinking},
                            )

                            # Spawn async summarization
                            asyncio.create_task(
                                self._summarize_and_update_block(
                                    block_id,
                                    agent_id,
                                    "thinking",
                                    {"content": block.thinking},
                                )
                            )

                            # Accumulate chars for token estimate
                            estimated_output_chars += len(block.thinking)

                            # Broadcast agent thinking via WebSocket
                            await self.ws_manager.broadcast_agent_log(
                                {
                                    "id": str(block_id),
                                    "agent_id": str(agent_id),
                                    "agent_name": agent_name,
                                    "task_slug": task_slug,
                                    "entry_index": entry_index,
                                    "event_category": "response",
                                    "event_type": "ThinkingBlock",
                                    "content": block.thinking,
                                    "summary": "[Agent is thinking]",
                                    "payload": {"thinking": block.thinking},
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                }
                            )
                            self.logger.debug(
                                f"Broadcast ThinkingBlock for agent {agent_name}"
                            )

                        elif isinstance(block, ToolUseBlock):
                            tool_use_block_count += 1
                            block_id = await insert_message_block(
                                agent_id=agent_id,
                                task_slug=task_slug,
                                entry_index=entry_index,
                                block_type="tool_use",
                                content=None,
                                payload={
                                    "tool_name": block.name,
                                    "tool_input": block.input,
                                    "tool_use_id": block.id,
                                },
                            )

                            # Spawn async summarization
                            asyncio.create_task(
                                self._summarize_and_update_block(
                                    block_id,
                                    agent_id,
                                    "tool_use",
                                    {
                                        "tool_name": block.name,
                                        "tool_input": block.input,
                                    },
                                )
                            )

                            # Broadcast agent tool use via WebSocket
                            await self.ws_manager.broadcast_agent_log(
                                {
                                    "id": str(block_id),
                                    "agent_id": str(agent_id),
                                    "agent_name": agent_name,
                                    "task_slug": task_slug,
                                    "entry_index": entry_index,
                                    "event_category": "response",
                                    "event_type": "ToolUseBlock",
                                    "content": f"[Tool] {block.name}",
                                    "summary": f"Using tool: {block.name}",
                                    "payload": {
                                        "tool_name": block.name,
                                        "tool_input": block.input,
                                        "tool_use_id": block.id,
                                    },
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                }
                            )
                            # Broadcast incremental token estimate every few tool calls
                            estimated_output_chars += len(str(block.input))
                            if tool_use_block_count % 3 == 0:
                                est_tokens = estimated_output_chars // 4  # ~4 chars per token
                                await self.ws_manager.broadcast_agent_updated(
                                    agent_id=str(agent_id),
                                    agent_data={
                                        "input_tokens": est_tokens,  # Rough estimate
                                        "output_tokens": est_tokens,
                                        "total_cost": est_tokens * 0.000003 * 2,  # Rough sonnet pricing
                                    }
                                )

                            self.logger.debug(
                                f"Broadcast ToolUseBlock for agent {agent_name}"
                            )

                elif isinstance(message, ResultMessage):
                    session_id = message.session_id
                    self.logger.info(
                        f"[ResultMessage] Agent={agent_name} "
                        f"total_cost_usd={getattr(message, 'total_cost_usd', 'N/A')} "
                        f"usage={message.usage} "
                        f"num_turns={getattr(message, 'num_turns', 'N/A')} "
                        f"is_error={getattr(message, 'is_error', 'N/A')}"
                    )

                    # Capture file changes for this agent and broadcast as separate event
                    file_tracker = self.file_trackers.get(str(agent_id))
                    if file_tracker and last_text_block_id:
                        try:
                            # Generate summaries (async)
                            modified_files_summary = (
                                await file_tracker.generate_file_changes_summary()
                            )
                            read_files_summary = (
                                file_tracker.generate_read_files_summary()
                            )

                            # Only broadcast if there are file operations
                            if modified_files_summary or read_files_summary:
                                # Import Pydantic model for type safety
                                from .file_tracker import AgentLogMetadata
                                import uuid

                                # Build metadata using Pydantic model
                                file_metadata = AgentLogMetadata(
                                    file_changes=modified_files_summary,
                                    read_files=read_files_summary,
                                    total_files_modified=len(modified_files_summary),
                                    total_files_read=len(read_files_summary),
                                    generated_at=datetime.now(timezone.utc).isoformat(),
                                )

                                # IMPORTANT: Update the TextBlock in database with file tracking data
                                # This ensures file changes persist and show up on page refresh
                                from .database import update_log_payload
                                await update_log_payload(
                                    last_text_block_id,
                                    file_metadata.model_dump()
                                )

                                # Broadcast as separate FileTrackingBlock event for real-time WebSocket updates
                                await self.ws_manager.broadcast_agent_log(
                                    {
                                        "id": str(uuid.uuid4()),  # New unique ID for this event
                                        "parent_log_id": str(last_text_block_id),  # Link to parent TextBlock
                                        "agent_id": str(agent_id),
                                        "agent_name": agent_name,
                                        "task_slug": task_slug,
                                        "event_category": "file_tracking",
                                        "event_type": "FileTrackingBlock",
                                        "content": f"📂 {len(modified_files_summary)} modified, {len(read_files_summary)} read",
                                        "summary": f"File tracking: {len(modified_files_summary)} modified, {len(read_files_summary)} read",
                                        "payload": file_metadata.model_dump(),
                                        "timestamp": datetime.now(
                                            timezone.utc
                                        ).isoformat(),
                                    }
                                )

                                self.logger.info(
                                    f"[FileTracker] Agent={agent_name} Modified={len(modified_files_summary)} Read={len(read_files_summary)} | Stored in DB"
                                )
                        except Exception as e:
                            self.logger.error(
                                f"Error capturing file changes: {e}", exc_info=True
                            )

                    # Extract cost from top-level field first (preferred)
                    total_cost = getattr(message, "total_cost_usd", None) or 0.0

                    # Extract token counts from usage dict/object
                    if message.usage:
                        usage = message.usage
                        if isinstance(usage, dict):
                            total_input_tokens = usage.get("input_tokens", 0)
                            total_output_tokens = usage.get("output_tokens", 0)
                            # Fall back to usage cost if top-level is None/0.0
                            if total_cost == 0.0:
                                total_cost = usage.get("total_cost_usd", 0.0)
                        else:
                            total_input_tokens = getattr(usage, "input_tokens", 0)
                            total_output_tokens = getattr(usage, "output_tokens", 0)
                            # Fall back to usage cost if top-level is None/0.0
                            if total_cost == 0.0:
                                total_cost = getattr(usage, "total_cost_usd", 0.0)

            # Update costs in database
            self.logger.info(
                f"[CostUpdate] Agent={agent_name} in={total_input_tokens} out={total_output_tokens} cost=${total_cost:.4f}"
            )
            if total_input_tokens or total_output_tokens:
                await update_agent_costs(
                    agent_id, total_input_tokens, total_output_tokens, total_cost
                )

                # Fetch updated agent to get cumulative totals
                updated_agent = await get_agent(agent_id)

                if updated_agent:
                    # Broadcast updated token/cost data to frontend
                    await self.ws_manager.broadcast_agent_updated(
                        agent_id=str(agent_id),
                        agent_data={
                            "input_tokens": updated_agent.input_tokens,
                            "output_tokens": updated_agent.output_tokens,
                            "total_cost": float(updated_agent.total_cost)
                        }
                    )

                    self.logger.debug(
                        f"Broadcast token update for agent {updated_agent.name} ({agent_id}): "
                        f"in={updated_agent.input_tokens}, out={updated_agent.output_tokens}, "
                        f"cost=${float(updated_agent.total_cost):.4f}"
                    )

        except Exception as e:
            self.logger.error(f"Error processing agent messages: {e}", exc_info=True)
            raise  # Re-raise to let command_agent handle the error properly

        finally:
            # Log summary of what we processed
            self.logger.info(
                f"[AgentManager] Processed agent={agent_name} task={task_slug}: "
                f"TextBlocks={text_block_count}, ThinkingBlocks={thinking_block_count}, "
                f"ToolUseBlocks={tool_use_block_count}"
            )

        return session_id

    # ═══════════════════════════════════════════════════════════
    # HELPER METHODS - AI Summarization
    # ═══════════════════════════════════════════════════════════

    async def _summarize_and_update_prompt(
        self, prompt_id: uuid.UUID, prompt_text: str
    ) -> None:
        """
        Generate AI summary for prompt and update database (background task).

        Args:
            prompt_id: UUID of the prompt to update
            prompt_text: The prompt text content
        """
        try:
            # Build event data for summarization
            event_data = {"prompt": prompt_text}

            # Generate AI summary (uses Claude Haiku for speed/cost)
            summary = await summarize_event(event_data, "UserPromptSubmit")

            # Update database with summary (only if non-empty)
            if summary and summary.strip():
                await update_prompt_summary(prompt_id, summary)
                self.logger.debug(
                    f"[AgentManager:Summary] Generated summary for prompt_id={prompt_id}: {summary}"
                )
            else:
                self.logger.warning(
                    f"[AgentManager:Summary] Empty summary for prompt_id={prompt_id}"
                )

        except Exception as e:
            self.logger.error(
                f"[AgentManager:Summary] Failed for prompt_id={prompt_id}: {e}"
            )

    async def _summarize_and_update_block(
        self,
        block_id: uuid.UUID,
        agent_id: uuid.UUID,
        block_type: str,
        event_data: Dict[str, Any],
    ) -> None:
        """
        Generate AI summary for message block and update database (background task).

        Args:
            block_id: UUID of the block to update
            agent_id: UUID of the agent this block belongs to
            block_type: Type of block (text, thinking, tool_use)
            event_data: Event data for summarization
        """
        try:
            # Generate AI summary (uses Claude Haiku for speed/cost)
            summary = await summarize_event(event_data, block_type)

            # Update database with summary (only if non-empty)
            if summary and summary.strip():
                await update_log_summary(block_id, summary)
                self.logger.debug(
                    f"[AgentManager:Summary] Generated summary for block_id={block_id}: {summary}"
                )

                # Broadcast the latest summary for this agent to frontend
                await self.ws_manager.broadcast_agent_summary_update(
                    agent_id=str(agent_id), summary=summary
                )
            else:
                self.logger.warning(
                    f"[AgentManager:Summary] Empty summary for block_id={block_id}"
                )

        except Exception as e:
            self.logger.error(
                f"[AgentManager:Summary] Failed for block_id={block_id}: {e}"
            )
