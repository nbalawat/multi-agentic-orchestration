# RAPIDS Meta-Orchestrator - Quick Reference

> **Fast lookup guide** for common tasks and architecture overview

---

## 🎯 What Is This?

**RAPIDS Meta-Orchestrator** = Multi-agent AI system that manages software projects through a 6-phase lifecycle:

```
Research → Analysis → Plan → Implement → Deploy → Sustain
```

- **Meta-orchestrator** coordinates multiple specialized **sub-agents**
- **Plugins** customize behavior per project archetype (greenfield, brownfield, etc.)
- **Feature DAG** enables autonomous parallel implementation
- **Real-time WebSocket** streaming shows all agent activity

---

## 🚀 Quick Start

```bash
# 1. Setup environment
cp .env.sample .env
# Edit .env with your database URL

# 2. Start database
docker-compose up -d

# 3. Run migrations
uv run python orchestrator/db/run_migrations.py

# 4. Install frontend deps
cd orchestrator/frontend && npm install && cd ../..

# 5. Start backend (terminal 1)
cd orchestrator/backend && ./start_be.sh

# 6. Start frontend (terminal 2)
cd orchestrator/frontend && ./start_fe.sh

# 7. Open browser
# http://localhost:5175
```

---

## 📐 Architecture (30-Second Overview)

```
┌─────────────────────────────────────┐
│ Vue 3 Frontend (Port 5175)          │
│ - Chat interface                    │
│ - Project/workspace management      │
│ - Real-time agent monitoring        │
└─────────────────────────────────────┘
              ↕ WebSocket + REST
┌─────────────────────────────────────┐
│ FastAPI Backend (Port 9403)         │
│ - OrchestratorService               │
│ - AgentManager                      │
│ - PhaseEngine (RAPIDS)              │
│ - FeatureDAG                        │
│ - PluginLoader                      │
└─────────────────────────────────────┘
              ↕ asyncpg
┌─────────────────────────────────────┐
│ PostgreSQL 16 (Port 5434)           │
│ - 6 orchestration tables            │
│ - 4 RAPIDS tables                   │
│ - Full audit trail                  │
└─────────────────────────────────────┘
```

**Tech Stack:**
- Backend: Python 3.12+ (FastAPI, Claude SDK, asyncpg, Pydantic)
- Frontend: Vue 3 + TypeScript (Vite, Pinia)
- Database: PostgreSQL 16

---

## 📂 Directory Structure (Essential Paths)

```
agentic-meta-orchestrator/
│
├── orchestrator/
│   ├── backend/
│   │   ├── main.py              ← FastAPI entry point
│   │   ├── modules/             ← 26 core modules (~12,700 lines)
│   │   │   ├── orchestrator_service.py   # Meta-orchestrator
│   │   │   ├── agent_manager.py          # Sub-agent lifecycle
│   │   │   ├── phase_engine.py           # RAPIDS phases
│   │   │   ├── feature_dag.py            # Dependency execution
│   │   │   └── database.py               # PostgreSQL ops
│   │   └── tests/               ← 14 test suites
│   │
│   ├── db/
│   │   ├── models.py            ← Pydantic models (orchestration)
│   │   ├── rapids_models.py     ← Pydantic models (RAPIDS)
│   │   ├── migrations/          ← 14 SQL migration files
│   │   └── run_migrations.py    ← Migration runner
│   │
│   └── frontend/
│       ├── src/
│       │   ├── App.vue          ← Root component
│       │   ├── components/      ← 17 Vue components
│       │   ├── stores/          ← 5 Pinia stores
│       │   └── services/        ← 9 API clients
│       └── package.json
│
├── .claude/
│   └── rapids-plugins/
│       └── greenfield/          ← Example archetype plugin
│           ├── plugin.json      # Phase definitions
│           ├── agents/          # 7 agent templates
│           └── workflows/       # 3 guided workflows
│
├── workspace/                   ← Multi-project workspace
├── .env                         ← Environment config
├── docker-compose.yml           ← PostgreSQL container
└── pyproject.toml              ← Python project config
```

---

## 🗄️ Database Schema (10 Tables)

**Orchestration Layer:**
1. `orchestrator_agents` - Meta-orchestrator singleton
2. `agents` - Sub-agent registry
3. `prompts` - User/orchestrator messages
4. `agent_logs` - Event log (hooks + responses)
5. `system_logs` - Application logs
6. `orchestrator_chat` - 3-way conversation

**RAPIDS Layer:**
7. `workspaces` - Project containers
8. `projects` - Software projects with archetypes
9. `project_phases` - Phase history
10. `features` - Tasks with dependencies

---

## 🔧 Common Tasks

### Start/Stop Services

```bash
# Start database
docker-compose up -d

# Stop database
docker-compose down

# Start backend
cd orchestrator/backend && ./start_be.sh

# Start frontend
cd orchestrator/frontend && ./start_fe.sh

# Resume existing session
./start_be.sh --session <session-id>
```

### Database Operations

```bash
# Run migrations
uv run python orchestrator/db/run_migrations.py

# Verify schema
uv run python orchestrator/db/sync_models.py

# Reset database (DANGER: destroys data)
docker-compose down -v
docker-compose up -d
uv run python orchestrator/db/run_migrations.py
```

### Testing

```bash
# All tests
uv run pytest

# Specific test file
uv run pytest orchestrator/backend/tests/test_database.py

# Verbose output
uv run pytest -v -s
```

### Code Quality

```bash
# Format Python
uv run ruff format .

# Lint Python
uv run ruff check .

# Type check frontend
cd orchestrator/frontend && npm run build
```

---

## 🧩 Plugin System

**Plugin Location:** `.claude/rapids-plugins/<archetype>/`

**Plugin Structure:**
```
<archetype>/
├── plugin.json           # Phase config, entry/exit criteria
├── agents/              # Agent templates (markdown)
├── workflows/           # Guided workflows (markdown)
├── commands/            # Custom slash commands
├── skills/              # Reusable capabilities
└── hooks/               # Event handlers
```

**Built-in Plugins:**
- `greenfield` - New projects from scratch

**Create Custom Plugin:**
```bash
mkdir -p .claude/rapids-plugins/my-archetype
# Add plugin.json, agents/, workflows/
```

---

## 🤖 Management Tools (Orchestrator Commands)

The orchestrator agent has these built-in tools:

| Tool | Purpose |
|------|---------|
| `create_agent(name, ...)` | Spawn new sub-agent |
| `list_agents()` | Show all agents |
| `command_agent(name, cmd)` | Send command to agent |
| `check_agent_status(name)` | Get agent logs/status |
| `delete_agent(name)` | Remove agent |
| `interrupt_agent(name)` | Stop running agent |
| `read_system_logs(...)` | Read application logs |
| `report_cost()` | Show token usage and costs |

**Example Usage:**
```
User: Create an agent named "researcher" to investigate authentication options
Orchestrator: *calls create_agent("researcher", system_prompt="...")*

User: What's the status of the researcher?
Orchestrator: *calls check_agent_status("researcher")*
```

---

## 📊 RAPIDS Phases

| Phase | Purpose | Entry Criteria | Exit Criteria |
|-------|---------|----------------|---------------|
| **Research** | Problem understanding | None | Problem statement, technology landscape, constraints |
| **Analysis** | Architecture design | Research complete | Architecture docs, tech stack, ADRs |
| **Plan** | Feature decomposition | Analysis complete | Feature DAG, specs, acceptance criteria |
| **Implement** | Code development | Plan complete, DAG valid | All features complete, tests passing |
| **Deploy** | Infrastructure setup | Implementation complete | Deployment artifacts, CI/CD configured |
| **Sustain** | Operations | Deployment complete | Monitoring, alerting, runbooks |

**Phase Transitions:**
- Validated by `PhaseEngine`
- Entry/exit criteria checked
- History tracked in `project_phases` table
- Customizable per archetype via plugins

---

## 🔑 Key Design Patterns

### 1. Fresh-Context Agents
Each feature gets a new agent instance (no context pollution):
```
Feature A → Agent 1 (only knows Feature A)
Feature B → Agent 2 (only knows Feature B)
Feature C → Agent 3 (only knows Feature C)
```

### 2. Three-Phase Logging
```
1. Pre-execution  → Log user message to DB
2. Execution      → Stream response via WebSocket
3. Post-execution → Log response, update costs
```

### 3. Hook-Based Events
```
pre_tool_hook  → Before tool execution
post_tool_hook → After tool execution
stop_hook      → Agent completion
```

### 4. Feature DAG
```
Dependencies → Topological Sort → Parallel Execution → Integration
```

### 5. Converge-Then-Execute
```
Research → Analysis → Plan (guided workflows, converge on spec)
                       ↓
                   Implement (autonomous DAG execution)
```

---

## 🌐 API Reference

### REST Endpoints

```
GET    /api/workspaces              List workspaces
POST   /api/workspaces              Create workspace
GET    /api/projects                List projects
POST   /api/projects                Create project
GET    /api/features                List features
POST   /api/features                Create feature
POST   /api/chat                    Send chat message
GET    /api/agents                  List agents
POST   /api/agents                  Create agent
```

### WebSocket

```
ws://localhost:9403/ws

Events:
- thinking        Agent thought process
- tool_use        Tool invocation
- tool_result     Tool response
- text            Agent text response
- status          Agent status update
- cost            Token usage update
```

---

## ⚙️ Configuration

### Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:password@host:5432/rapids_orchestrator

# Ports
BACKEND_PORT=9403
FRONTEND_PORT=5175

# Model
ORCHESTRATOR_MODEL=claude-sonnet-4-5-20250929

# Logging
LOG_LEVEL=INFO
LOG_DIR=orchestrator/backend/logs
```

### Model Options

- `claude-sonnet-4-5-20250929` - **Recommended** (balanced)
- `claude-opus-4-20250514` - Maximum capability
- `claude-haiku-4-20250611` - Fast responses

---

## 📈 Project Statistics

- **~1,500** Python files (including dependencies)
- **~12,700** lines in backend modules
- **26** backend modules
- **17** Vue components
- **10** database tables
- **14** SQL migrations
- **7** specialized agents (greenfield plugin)
- **3** guided workflows

---

## 🐛 Troubleshooting

### Database Connection Failed

```bash
# Check database is running
docker ps | grep rapids-postgres

# Check connection string
echo $DATABASE_URL

# Restart database
docker-compose restart
```

### Frontend Can't Connect to Backend

```bash
# Check backend is running
curl http://localhost:9403/health

# Check ports in .env match running services
grep PORT .env

# Check CORS settings in backend/main.py
```

### Migration Errors

```bash
# Check migration files exist
ls orchestrator/db/migrations/

# Run migrations with verbose output
uv run python orchestrator/db/run_migrations.py -v

# Reset and re-migrate (DANGER)
docker-compose down -v
docker-compose up -d
uv run python orchestrator/db/run_migrations.py
```

### Agent Not Responding

```bash
# Check agent logs
uv run python -c "
from modules.database import get_agent_logs
import asyncio
asyncio.run(get_agent_logs(agent_id='...'))
"

# Check agent status
# Use orchestrator: "Check status of agent <name>"

# Interrupt stuck agent
# Use orchestrator: "Interrupt agent <name>"
```

---

## 📚 Related Documents

- **`PROJECT_OVERVIEW.md`** - Comprehensive project documentation
- **`README.md`** - Basic project introduction
- **`CLAUDE.md`** - Development guidelines
- **`.env.sample`** - Environment template
- **`orchestrator/db/migrations/`** - Database schema

---

## 🔗 Quick Links

**URLs:**
- Frontend: http://localhost:5175
- Backend API: http://localhost:9403
- WebSocket: ws://localhost:9403/ws

**Key Modules:**
- `orchestrator/backend/main.py` - FastAPI entry point
- `orchestrator/backend/modules/orchestrator_service.py` - Core orchestrator
- `orchestrator/backend/modules/agent_manager.py` - Agent lifecycle
- `orchestrator/frontend/src/App.vue` - Frontend root

**Plugin Example:**
- `.claude/rapids-plugins/greenfield/plugin.json` - Plugin configuration
- `.claude/rapids-plugins/greenfield/agents/` - Agent templates
- `.claude/rapids-plugins/greenfield/workflows/` - Workflow guides

---

**Last Updated:** March 22, 2026
**Project:** RAPIDS Meta-Orchestrator
**Version:** 1.0
