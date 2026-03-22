# RAPIDS Meta-Orchestrator

**AI-powered multi-project orchestration engine built on the Claude Agent SDK.**

RAPIDS (Research → Analysis → Plan → Implement → Deploy → Sustain) is a structured lifecycle framework that guides software projects from problem discovery through production deployment using coordinated AI agents.

## What It Does

The orchestrator manages **multiple projects simultaneously**, each progressing through the RAPIDS lifecycle with specialized agents. It spawns independent Claude agents — each with their own 200k context window — that research codebases, design architectures, decompose features into dependency DAGs, implement in parallel, and deploy.

```
┌─────────────────────────────────────────────────────────┐
│                   ORCHESTRATOR AGENT                     │
│  Conducts the workflow: creates, dispatches, monitors    │
│                                                          │
│  ┌─────────┐  ┌──────────┐  ┌────────────────────────┐  │
│  │Workspace│  │ Plugin   │  │  Phase Engine           │  │
│  │Manager  │  │ Registry │  │  R → A → P → I → D → S │  │
│  └─────────┘  └──────────┘  └────────────────────────┘  │
└──────────┬───────────────────────────────────────────────┘
           │ spawns independent agents per phase
           ▼
┌──────────────────────────────────────────────────────────┐
│  INDEPENDENT AGENTS (each with own 200k context)         │
│                                                          │
│  ┌───────────┐ ┌──────────┐ ┌─────────┐ ┌───────────┐   │
│  │Researcher │ │Architect │ │Planner  │ │Builder ×3 │   │
│  │(research) │ │(analysis)│ │(plan)   │ │(parallel) │   │
│  └───────────┘ └──────────┘ └─────────┘ └───────────┘   │
└──────────────────────────────────────────────────────────┘
```

## Key Features

### Multi-Project Workspace Management
- Onboard multiple git repositories into a workspace
- Each project tracks its own RAPIDS phase independently
- Switch between projects; agents operate in project context
- **Project context bar** in UI header shows: `Workspace: name / Project: name | PHASE | archetype`

### Plugin-Driven Archetypes
- **4 archetype plugins** with specialized agents, skills, and workflows:
  - **Greenfield** — New projects from scratch (7 agents, 5 skills, 6 commands, 3 workflows)
  - **Brownfield** — Enhancing/refactoring existing codebases (6 agents, 3 skills)
  - **Data Modernization** — Database migration, ETL pipelines, schema evolution (6 agents, 3 skills)
  - **Reverse Engineering** — Documenting undocumented codebases (6 agents, 3 skills)
- Plugins follow the **Claude Code SDK format** (`.claude-plugin/plugin.json`)
- **25 agent templates** + **14 auto-invocable skills** across all plugins
- **SDK auto-discovery** — when an agent is created, the SDK automatically discovers and loads the plugin's skills, agents, and commands via `ClaudeAgentOptions(plugins=[...], setting_sources=["user", "project"])`
- **Plugin-first prompts** — agent system prompts use the plugin's agent template as PRIMARY content, with skills enumerated for the agent to invoke

### RAPIDS Lifecycle Engine
| Phase | Purpose | Output |
|-------|---------|--------|
| **Research** | Explore problem space, gather context (interactive Q&A) | `problem-statement.md`, `technology-landscape.md`, `requirements.md`, `constraints.md`, `success-metrics.md` |
| **Analysis** | Evaluate solutions, design architecture | `solution-options.md`, `solution-decision.md`, `architecture.md`, `data-model.md`, `tech-stack.md`, `risk-register.md` |
| **Plan** | Decompose into features with dependency DAG | `feature_dag.json`, `specification.md`, `features/<name>/spec.md`, `features/<name>/acceptance-criteria.md` |
| **Implement** | Parallel execution honoring DAG dependencies | Code, tests, integration verification |
| **Deploy** | CI/CD, infrastructure, deployment automation | Deployment artifacts, runbooks |
| **Sustain** | Monitoring, alerting, continuous improvement | Dashboards, alerting rules |

### Parallel Feature Execution
- Feature DAG defines dependency-ordered execution waves
- Independent features execute in parallel (configurable `max_parallel`)
- Each feature agent gets a fresh 200k context with only its spec
- **Verified E2E**: 2 builder agents working simultaneously, writing code + tests, all 14 tests passing

### Real-Time UI Dashboard
- **Left panel**: Agent cards with status (IDLE/EXECUTING), context window usage (e.g. 5k/200k), per-agent cost, event counters (responses, tools, hooks, thinking)
- **Center panel**: Live event stream with interleaved activity from all agents, filterable by agent name and event type (RESPONSE, TOOL, THINKING, HOOK)
- **Right panel**: Orchestrator chat with markdown rendering, thinking blocks, tool use cards
- **Header**: Project context bar (`Workspace: demo / Project: task-api | IMPLEMENT | greenfield`), active agent count, total logs, total cost
- **Command input**: `Cmd+K` to open, `Enter` to send, shows available tools and active agents
- WebSocket-based real-time streaming with auto-reconnect

## Architecture

### Agent Model: Independent Agents (Not SDK Sub-agents)
The orchestrator creates **fully independent agents**, each with its own `ClaudeSDKClient` session:
- Each agent gets a **fresh 200k context window** — no context sharing with the orchestrator
- Agents are **independently monitored** — status, cost, context usage, event counters
- Communication via **MCP tools** (`command_agent`, `check_agent_status`) — message passing, not context sharing
- **Plugin auto-discovery** — each agent's `ClaudeAgentOptions` includes the project's plugin for SDK-native skill/agent/command loading
- Agents can invoke plugin skills like `/greenfield:web-research` autonomously

### Tech Stack
| Component | Technology |
|-----------|-----------|
| Backend | Python 3.12+, FastAPI, Claude Agent SDK |
| Frontend | Vue 3, TypeScript, Pinia, Vite |
| Database | PostgreSQL 16 (10 tables, 14 migrations) |
| AI | Claude Sonnet 4.5 (orchestrator + agents) |
| Transport | WebSocket (real-time), REST (management) |

### Project Structure
```
orchestrator/
├── backend/
│   ├── main.py                    # FastAPI app, 24+ endpoints, lifespan management
│   ├── modules/
│   │   ├── agent_manager.py       # Agent lifecycle, 22 MCP tools, phase-aware prompt building
│   │   ├── orchestrator_service.py # Claude SDK orchestrator, system prompt with PLUGIN_CATALOG
│   │   ├── plugin_loader.py       # PluginLoader + PluginRegistry (multi-plugin discovery, capability catalog)
│   │   ├── workspace_manager.py   # Project/workspace management, project context caching
│   │   ├── phase_engine.py        # RAPIDS state machine with entry/exit criteria
│   │   ├── feature_dag.py         # DAG-based parallel execution with wave grouping
│   │   ├── autonomous_executor.py # Parallel feature implementation with git worktrees
│   │   ├── workflow_runner.py     # Interactive section-by-section workflow execution
│   │   ├── websocket_manager.py   # Real-time event broadcasting to frontend
│   │   ├── plugin_security.py     # RBAC, sandboxing, path safety, tool allowlists
│   │   └── slash_command_parser.py # Parse command .md files with YAML frontmatter
│   └── prompts/
│       ├── orchestrator_agent_system_prompt.md
│       └── phase_prompts/         # Per-phase prompt templates (research, analysis, plan, implement, deploy, sustain)
├── frontend/
│   └── src/
│       ├── components/            # 15+ Vue components (AgentList, EventStream, OrchestratorChat, ProjectContextBar, etc.)
│       ├── stores/                # Pinia state management (orchestratorStore, projectStore, workspaceStore)
│       ├── services/              # API client, WebSocket, agent/event/project/workspace services
│       └── composables/           # useEventStreamFilter, useHeaderBar, useAgentPulse, useKeyboardShortcuts
├── db/
│   ├── migrations/                # 14 SQL migration files (0-13)
│   ├── models.py                  # Pydantic models for all tables
│   └── rapids_models.py          # RAPIDS-specific models (workspaces, projects, phases, features)
└── .claude/
    └── rapids-plugins/            # Archetype plugins (SDK-compatible)
        ├── greenfield/            # 7 agents, 5 skills, 6 commands, 3 workflows
        ├── brownfield/            # 6 agents, 3 skills
        ├── data-modernization/    # 6 agents, 3 skills
        └── reverse-engineering/   # 6 agents, 3 skills
```

## Quick Start

### Prerequisites
- Python 3.12+ with [Astral UV](https://docs.astral.sh/uv/)
- Node.js 22+ (frontend)
- PostgreSQL 16 (Docker recommended)
- Anthropic API key

### Setup

```bash
# Clone
git clone git@github.com:nbalawat/multi-agentic-orchestration.git
cd multi-agentic-orchestration

# Install Python dependencies
uv sync

# Create .env from sample
cp .env.sample .env
# Edit .env: add ANTHROPIC_API_KEY and DATABASE_URL

# Start PostgreSQL (Docker)
docker run -d --name rapids-postgres \
  -e POSTGRES_USER=rapids \
  -e POSTGRES_PASSWORD=rapids_dev_2024 \
  -e POSTGRES_DB=rapids_orchestrator \
  -p 5434:5432 \
  postgres:16-alpine

# Run migrations
for f in orchestrator/db/migrations/*.sql; do
  docker exec -i rapids-postgres psql -U rapids -d rapids_orchestrator < "$f"
done

# Start backend
cd orchestrator/backend
uv run uvicorn main:app --host 127.0.0.1 --port 9403 --reload

# Start frontend (separate terminal)
cd orchestrator/frontend
npm install
npx vite --host 127.0.0.1 --port 5175
```

Open http://127.0.0.1:5175 — the orchestrator is ready.

### First Run

1. Press `Cmd+K` to open the command input
2. Type: *"Create a workspace called 'my-projects'. Then onboard the project at /path/to/your/repo with archetype greenfield."*
3. The orchestrator creates the workspace, onboards the project, and is ready for RAPIDS phases
4. Type: *"Start the Research phase and create a research agent"*
5. Watch the research agent explore the codebase and produce artifacts in `.rapids/research/`

### E2E Verified Workflow
The following workflow has been tested end-to-end:

1. **Clean slate** → Empty UI with "No active project"
2. **Create workspace** → `Workspace: demo` appears in header
3. **Onboard project** (greenfield archetype) → `Project: task-api | RESEARCH | greenfield` in header
4. **Research phase** → Research agent spawns, explores codebase, produces 5 research artifacts
5. **Analysis phase** → Analyst agent creates 6 analysis artifacts (solution options, architecture, tech stack)
6. **Plan phase** → Planner agent produces feature_dag.json with 4 features + per-feature specs
7. **Implement phase** → `execute_ready_features(max_parallel=2)` spawns 2 builder agents simultaneously
8. **Parallel execution** → Both builders work concurrently, writing code + tests (481 lines, 14 tests all passing)
9. **UI shows everything** → Agent cards with live stats, interleaved event stream, cost tracking

## Plugin System

Plugins define **how each RAPIDS phase works** for a specific project archetype. The orchestrator discovers plugins automatically and uses them to configure agents.

### Plugin Structure (SDK-Compatible)
```
my-plugin/
├── .claude-plugin/
│   └── plugin.json         # SDK manifest (required for auto-discovery)
├── plugin.json              # RAPIDS manifest (phases, criteria, default agents, skills)
├── agents/                  # Agent templates (YAML frontmatter + markdown system prompt)
│   ├── researcher.md        # Research phase agent
│   └── architect.md         # Analysis phase agent
├── skills/                  # Auto-invocable skills (SDK SKILL.md format)
│   ├── web-research/
│   │   └── SKILL.md         # Invoked as /plugin-name:web-research
│   └── domain-analysis/
│       └── SKILL.md
├── commands/                # Slash commands (legacy format)
│   └── research.md
└── workflows/               # Guided workflow templates for convergence phases
    └── research-workflow.md
```

### How Plugins Load
1. `PluginRegistry` scans `.claude/rapids-plugins/` at startup — discovers all plugins
2. Orchestrator system prompt includes `{{PLUGIN_CATALOG}}` listing all plugins + capabilities
3. When an agent is created for a phase, the project's plugin is passed to `ClaudeAgentOptions(plugins=[...])`
4. The Claude SDK **automatically discovers** skills, agents, and commands from the plugin
5. Agent system prompt includes `## Available Skills` section listing all invocable skills with descriptions
6. Agents can invoke skills like `/greenfield:web-research` autonomously based on context

### Plugin Capabilities (Current)

| Plugin | Agents | Skills | Commands | Workflows |
|--------|--------|--------|----------|-----------|
| **greenfield** | researcher, architect, planner, feature-builder, tester, deployer, monitor | web-research, domain-analysis, solution-design, feature-decomposition, spec-writing | /research, /analyze, /plan, /implement, /deploy, /sustain | research, analysis, plan |
| **brownfield** | codebase-analyst, refactoring-architect, incremental-planner, enhancement-builder, deployer, monitor | codebase-exploration, tech-debt-analysis, impact-analysis | — | — |
| **data-modernization** | data-archeologist, schema-designer, migration-planner, migration-executor, migration-deployer, data-monitor | schema-profiling, data-lineage-tracing, migration-sequencing | — | — |
| **reverse-engineering** | code-detective, system-mapper, documentation-planner, documentation-writer, docs-publisher, knowledge-maintainer | code-archaeology, architecture-recovery, api-surface-mapping | — | — |

### Creating a New Plugin
1. Create a directory in `.claude/rapids-plugins/your-archetype/`
2. Add `plugin.json` (RAPIDS manifest) with phases, default agents, entry/exit criteria, skills, prompt supplements
3. Add `.claude-plugin/plugin.json` (SDK manifest) — minimal: `{"name": "your-archetype", "description": "...", "version": "1.0.0"}`
4. Create agent templates in `agents/<agent-name>.md` with YAML frontmatter (name, description, model, tools, color) + markdown system prompt
5. Create skills in `skills/<skill-name>/SKILL.md` with description in frontmatter
6. The orchestrator discovers it automatically on next restart

## API Reference

### Management Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/get_orchestrator` | GET | Get orchestrator state |
| `/send_chat` | POST | Send message to orchestrator |
| `/list_agents` | GET | List all agents with stats |
| `/get_events` | GET | Get event history (pagination supported) |
| `/get_headers` | GET | Get header data (workspace, project, phase) |

### Workspace & Project Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/workspaces` | POST | Create workspace |
| `/api/workspaces` | GET | List workspaces |
| `/api/projects` | POST | Onboard project (creates project + initializes .rapids/ + phases) |
| `/api/projects/{id}` | GET | Get project details |
| `/api/projects/{id}/switch` | POST | Switch active project context |

### RAPIDS Phase Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/phases/{project_id}/start` | POST | Start a phase (validates entry criteria) |
| `/api/phases/{project_id}/complete` | POST | Complete a phase (validates exit criteria) |
| `/api/phases/{project_id}/advance` | POST | Complete current + start next phase |

### Feature & DAG Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/projects/{id}/features` | GET | List features for a project |
| `/api/projects/{id}/features` | POST | Create a feature (priority: int, depends_on: list) |
| `/api/projects/{id}/dag` | GET | Get feature DAG from .rapids/plan/feature_dag.json |
| `/api/projects/{id}/dag/validate` | GET | Validate DAG (acyclicity, dependency resolution) |
| `/api/projects/{id}/dag/features/{fid}/status` | POST | Update feature status |

### Plugin Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/plugins` | GET | List all discovered plugins |
| `/api/plugins/{name}` | GET | Get plugin details + capabilities |

### WebSocket
Connect to `ws://127.0.0.1:9403/ws` for real-time events:
- `orchestrator_chat` — Chat messages (user ↔ orchestrator)
- `thinking_block` — Agent reasoning / chain-of-thought
- `tool_use_block` — Tool invocations with parameters
- `agent_log` — Agent activity events (tool use, hooks, responses)
- `agent_created` / `agent_updated` / `agent_status_change` — Agent lifecycle
- `dag_progress` — Feature DAG execution progress
- `system_log` — System-level events

## MCP Tools (Orchestrator)

The orchestrator exposes **22 MCP tools** to Claude, organized by domain:

### Agent Management
| Tool | Purpose |
|------|---------|
| `create_agent` | Spawn a new agent. Supports `phase` + `project_id` for auto-configured plugin-aware prompts with skills |
| `command_agent` | Send instructions to an existing agent |
| `check_agent_status` | Monitor agent progress, view recent logs |
| `list_agents` | View all active agents with stats |
| `delete_agent` | Remove an agent |
| `interrupt_agent` | Interrupt a running agent |

### Workspace & Project
| Tool | Purpose |
|------|---------|
| `create_workspace` | Create a new workspace |
| `list_workspaces` | List all workspaces |
| `onboard_project` | Onboard a git repo as a project with archetype |
| `list_projects` | List all projects in workspace |
| `switch_project` | Switch active project context |
| `get_project_status` | Get project phase status and details |

### RAPIDS Lifecycle
| Tool | Purpose |
|------|---------|
| `start_phase` | Start a RAPIDS phase (with entry criteria validation) |
| `complete_phase` | Complete current phase (with exit criteria validation) |
| `advance_phase` | Complete current + start next phase |

### Feature DAG
| Tool | Purpose |
|------|---------|
| `list_features` | List features for a project |
| `create_feature` | Create a feature (auto-converts priority strings: high→1, medium→2, low→3) |
| `get_feature_dag_status` | Inspect DAG: ready features, parallel groups, completion status |
| `execute_ready_features` | Launch parallel builder agents for ready features (configurable `max_parallel`) |

### Plugin & Observability
| Tool | Purpose |
|------|---------|
| `list_plugin_capabilities` | Inspect any plugin's agents, skills, commands, workflows, phases |
| `read_system_logs` | View system logs with filtering |
| `report_cost` | Get token usage and cost breakdown |

## Version History

| Version | Tag | Description |
|---------|-----|-------------|
| v0.1.0 | `v0.1.0` | Baseline — RAPIDS orchestrator with phase prompts, workspace management, feature DAG |
| v0.2.0 | `v0.2.0` | Plugin-driven orchestration: PluginRegistry, 4 archetypes, capability catalog |
| Latest | HEAD | SDK-native auto-discovery (25 agents, 14 skills), skill injection into agent prompts, feature creation fixes, E2E verified parallel implementation |

## Known Issues & Roadmap

### Current Limitations
- Research/Analysis phases run non-interactively (agent explores and produces artifacts without Q&A). Interactive Q&A prompt exists but needs agent-level `ask_user` MCP tool for direct user communication.
- Workspace/project context can be lost on backend restart (in-memory cache). Re-switch to project to restore.
- O-Agent counters (responses, tools, hooks, thinking) don't increment for orchestrator's own events — only for sub-agent activity.

### Planned
- Agent-level `ask_user` MCP tool for interactive RAP phases (route questions through WebSocket to frontend)
- Automatic wave progression in DAG execution (Wave 2 starts when Wave 1 completes)
- Multi-project simultaneous operation (project A in Implement, project B in Research)
- Plugin marketplace / remote plugin installation
- Cost budgets per agent (`max_budget_usd` in ClaudeAgentOptions)

## License

Private — All rights reserved.
