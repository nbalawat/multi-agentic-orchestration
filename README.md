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

### Plugin-Driven Archetypes
- **4 archetype plugins** with specialized agents, skills, and workflows:
  - **Greenfield** — New projects from scratch
  - **Brownfield** — Enhancing/refactoring existing codebases
  - **Data Modernization** — Database migration, ETL pipelines, schema evolution
  - **Reverse Engineering** — Documenting undocumented codebases
- Plugins follow the Claude Code SDK format (`.claude-plugin/plugin.json`)
- 25 agent templates + 14 auto-invocable skills across all plugins
- SDK auto-discovery — agents automatically get access to their plugin's skills

### RAPIDS Lifecycle Engine
| Phase | Purpose | Output |
|-------|---------|--------|
| **Research** | Explore problem space, gather context | `problem-statement.md`, `technology-landscape.md`, `requirements.md` |
| **Analysis** | Evaluate solutions, design architecture | `solution-decision.md`, `architecture.md`, `tech-stack.md` |
| **Plan** | Decompose into features with dependency DAG | `feature_dag.json`, `specification.md`, per-feature specs |
| **Implement** | Parallel execution honoring DAG dependencies | Code, tests, integration verification |
| **Deploy** | CI/CD, infrastructure, deployment automation | Deployment artifacts, runbooks |
| **Sustain** | Monitoring, alerting, continuous improvement | Dashboards, alerting rules |

### Parallel Feature Execution
- Feature DAG defines dependency-ordered execution waves
- Independent features execute in parallel (configurable `max_parallel`)
- Each feature agent gets a fresh 200k context with only its spec
- Automatic progression through DAG waves as features complete

### Real-Time UI Dashboard
- **Left panel**: Agent cards with status, context usage, cost, event counters
- **Center panel**: Live event stream (responses, tools, thinking, hooks)
- **Right panel**: Orchestrator chat with markdown rendering
- **Header**: Project context bar (workspace/project/phase/archetype)
- WebSocket-based real-time streaming

## Architecture

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
│   ├── main.py                    # FastAPI app, 24+ endpoints
│   ├── modules/
│   │   ├── agent_manager.py       # Agent lifecycle + 22 MCP tools
│   │   ├── orchestrator_service.py # Claude SDK orchestrator
│   │   ├── plugin_loader.py       # PluginRegistry + multi-plugin discovery
│   │   ├── workspace_manager.py   # Project/workspace management
│   │   ├── phase_engine.py        # RAPIDS state machine
│   │   ├── feature_dag.py         # DAG-based parallel execution
│   │   ├── autonomous_executor.py # Parallel feature implementation
│   │   ├── workflow_runner.py     # Interactive workflow execution
│   │   └── websocket_manager.py   # Real-time event broadcasting
│   └── prompts/
│       ├── orchestrator_agent_system_prompt.md
│       └── phase_prompts/         # Per-phase prompt templates
├── frontend/
│   └── src/
│       ├── components/            # Vue components (15+)
│       ├── stores/                # Pinia state management
│       ├── services/              # API + WebSocket services
│       └── composables/           # Reusable logic
├── db/
│   ├── migrations/                # 14 SQL migration files
│   └── models.py                  # Pydantic models
└── .claude/
    └── rapids-plugins/            # Archetype plugins
        ├── greenfield/            # 7 agents, 5 skills, 6 commands
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

## Plugin System

Plugins define **how each RAPIDS phase works** for a specific project archetype. The orchestrator discovers plugins automatically and uses them to configure agents.

### Plugin Structure (SDK-Compatible)
```
my-plugin/
├── .claude-plugin/
│   └── plugin.json         # SDK manifest (required)
├── plugin.json              # RAPIDS manifest (phases, criteria, agents)
├── agents/                  # Agent templates (YAML frontmatter + markdown)
│   ├── researcher.md
│   └── architect.md
├── skills/                  # Auto-invocable skills
│   ├── web-research/
│   │   └── SKILL.md
│   └── domain-analysis/
│       └── SKILL.md
├── commands/                # Slash commands
│   └── research.md
└── workflows/               # Guided workflow templates
    └── research-workflow.md
```

### How Plugins Load
1. `PluginRegistry` scans `.claude/rapids-plugins/` at startup
2. When an agent is created for a phase, the project's plugin is passed to `ClaudeAgentOptions`
3. The Claude SDK **automatically discovers** skills, agents, and commands from the plugin
4. Agents can invoke skills like `/greenfield:web-research` autonomously

### Creating a New Plugin
1. Create a directory in `.claude/rapids-plugins/your-archetype/`
2. Add `plugin.json` with phases, default agents, entry/exit criteria
3. Add `.claude-plugin/plugin.json` (minimal SDK manifest)
4. Create agent templates in `agents/`
5. Create skills in `skills/<name>/SKILL.md`
6. The orchestrator discovers it automatically on next startup

## API Overview

### Management Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/get_orchestrator` | GET | Get orchestrator state |
| `/send_chat` | POST | Send message to orchestrator |
| `/list_agents` | GET | List all agents |
| `/get_events` | GET | Get event history |

### Workspace Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/workspaces` | POST | Create workspace |
| `/api/workspaces` | GET | List workspaces |
| `/api/projects` | POST | Onboard project |
| `/api/projects/{id}/switch` | POST | Switch active project |

### RAPIDS Phase Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/phases/{project_id}/start` | POST | Start a phase |
| `/api/phases/{project_id}/complete` | POST | Complete a phase |
| `/api/phases/{project_id}/advance` | POST | Advance to next phase |

### Plugin Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/plugins` | GET | List all plugins |
| `/api/plugins/{name}` | GET | Get plugin details |

### WebSocket
Connect to `ws://127.0.0.1:9403/ws` for real-time events:
- `orchestrator_chat` — Chat messages
- `thinking_block` — Agent reasoning
- `tool_use_block` — Tool invocations
- `agent_log` — Agent activity events
- `agent_created` / `agent_updated` — Agent lifecycle
- `dag_progress` — Feature DAG execution progress

## MCP Tools (Orchestrator)

The orchestrator exposes 22 MCP tools to Claude:

| Tool | Purpose |
|------|---------|
| `create_agent` | Spawn a new agent (with optional phase + project_id for auto-configured prompts) |
| `command_agent` | Send instructions to an existing agent |
| `check_agent_status` | Monitor agent progress |
| `list_agents` | View all active agents |
| `delete_agent` / `interrupt_agent` | Agent lifecycle management |
| `create_workspace` / `list_workspaces` | Workspace management |
| `onboard_project` / `list_projects` | Project management |
| `switch_project` / `get_project_status` | Project context |
| `start_phase` / `complete_phase` / `advance_phase` | RAPIDS lifecycle |
| `list_features` / `create_feature` | Feature management |
| `get_feature_dag_status` | DAG inspection |
| `execute_ready_features` | Parallel feature execution |
| `list_plugin_capabilities` | Plugin introspection |
| `read_system_logs` / `report_cost` | Observability |

## Version History

| Version | Description |
|---------|-------------|
| v0.1.0 | Baseline — RAPIDS orchestrator with hardcoded phase prompts |
| v0.2.0 | Plugin-driven orchestration with PluginRegistry and 4 archetypes |
| Latest | SDK-native auto-discovery with 25 agents, 14 skills, 6 commands |

## License

Private — All rights reserved.
