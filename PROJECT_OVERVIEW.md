# RAPIDS Meta-Orchestrator - Project Overview

> **Comprehensive exploration summary** - Generated on March 22, 2026

---

## Table of Contents

1. [Project Purpose](#project-purpose)
2. [Core Functionality](#core-functionality)
3. [Architecture Overview](#architecture-overview)
4. [Key Components](#key-components)
5. [Data Models](#data-models)
6. [Plugin System](#plugin-system)
7. [Technology Stack](#technology-stack)
8. [Directory Structure](#directory-structure)
9. [Design Patterns](#design-patterns)
10. [Development Workflow](#development-workflow)
11. [Configuration](#configuration)

---

## Project Purpose

**RAPIDS Meta-Orchestrator** is a sophisticated multi-project workspace orchestration system built on the Claude Agent SDK. It provides an AI-powered platform for managing software projects through a structured, phase-based methodology.

### The RAPIDS Lifecycle

The system guides projects through six distinct phases:

- **R**esearch - Problem understanding and technology landscape
- **A**nalysis - Architecture design and decision making
- **P**lan - Feature decomposition and dependency mapping
- **I**mplement - Autonomous feature execution via DAG
- **D**eploy - Infrastructure setup and CI/CD configuration
- **S**ustain - Monitoring, maintenance, and operations

### Primary Goals

1. **Structured Project Management**: Enforce best practices through phase gates with entry/exit criteria
2. **Multi-Agent Coordination**: Meta-orchestrator manages specialized sub-agents for different tasks
3. **Autonomous Execution**: Fresh-context agents execute features independently using dependency graphs
4. **Archetype Flexibility**: Plugin system adapts workflows to project types (greenfield, brownfield, etc.)
5. **Real-Time Visibility**: WebSocket streaming provides live updates on all agent activities

---

## Core Functionality

### 1. Multi-Agent Orchestration

- **Meta-orchestrator agent** coordinates multiple sub-agents
- Each agent has its own session, working directory, and cost tracking
- Agents can be created, commanded, monitored, interrupted, and deleted
- Support for git worktree isolation to prevent conflicts

### 2. Phase-Based Workflow Management

- Projects progress through RAPIDS phases with validation at each transition
- Entry criteria must be met before entering a phase
- Exit criteria must be satisfied before advancing
- Phase history tracked with start/completion timestamps
- Support for blocking, review, and skipping phases

### 3. Workspace & Project Organization

- **Workspaces**: Top-level containers for related projects
- **Projects**: Individual software initiatives with archetype classification
- **Features**: Decomposed tasks with dependency tracking
- **Priority management** and **archiving** support

### 4. Feature DAG Execution

- Features organized as directed acyclic graph (DAG)
- Topological execution enables maximum parallelism
- Each feature assigned to fresh-context agent with isolated specification
- Automatic dependency resolution and blocking on incomplete dependencies

### 5. Plugin Architecture

- **Archetype-specific plugins** (greenfield, brownfield, enhancement, etc.)
- Customizable phase definitions, agents, workflows, and skills
- Dynamic plugin loading from `.claude/rapids-plugins/`
- Phase-specific prompt supplements inject context

### 6. Real-Time Streaming Interface

- WebSocket-based chat interface with live agent updates
- Streaming of agent thoughts, tool calls, and responses
- 3-way communication: user ↔ orchestrator ↔ agents
- Cost tracking and token usage monitoring

---

## Architecture Overview

### Three-Tier Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     FRONTEND LAYER                           │
│  ┌────────────────────────────────────────────────────┐     │
│  │  Vue 3 + TypeScript + Vite                         │     │
│  │  - Chat interface with markdown rendering          │     │
│  │  - Workspace/project/feature management UI         │     │
│  │  - Real-time agent status monitoring               │     │
│  │  - WebSocket client for streaming                  │     │
│  │  - Pinia stores for state management               │     │
│  └────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────┘
                           ↕
              (WebSocket + REST HTTP/JSON)
                           ↕
┌──────────────────────────────────────────────────────────────┐
│                     BACKEND LAYER                            │
│  ┌────────────────────────────────────────────────────┐     │
│  │  FastAPI + Claude Agent SDK (Python 3.12+)         │     │
│  │                                                     │     │
│  │  Core Services:                                    │     │
│  │  • OrchestratorService - Meta-orchestrator agent   │     │
│  │  • AgentManager - Sub-agent lifecycle mgmt         │     │
│  │  • PhaseEngine - RAPIDS phase transitions          │     │
│  │  • WorkspaceManager - Multi-workspace handling     │     │
│  │  • FeatureDAG - Dependency graph execution         │     │
│  │  • PluginLoader - Dynamic archetype loading        │     │
│  │  • WorkflowRunner - Guided template execution      │     │
│  │  • AutonomousExecutor - Fresh-context agents       │     │
│  │  • WebSocketManager - Real-time streaming          │     │
│  └────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────┘
                           ↕
                    (asyncpg - async)
                           ↕
┌──────────────────────────────────────────────────────────────┐
│                     DATABASE LAYER                           │
│  ┌────────────────────────────────────────────────────┐     │
│  │  PostgreSQL 16 (NeonDB or Docker)                  │     │
│  │                                                     │     │
│  │  Orchestration Schema:                             │     │
│  │  • orchestrator_agents - Meta-orchestrator state   │     │
│  │  • agents - Sub-agent registry                     │     │
│  │  • prompts - User/orchestrator messages            │     │
│  │  • agent_logs - Event log (hooks + responses)      │     │
│  │  • system_logs - Application-level logs            │     │
│  │  • orchestrator_chat - 3-way conversation log      │     │
│  │                                                     │     │
│  │  RAPIDS Schema:                                    │     │
│  │  • workspaces - Top-level project containers       │     │
│  │  • projects - Software projects with archetypes    │     │
│  │  • project_phases - Phase history tracking         │     │
│  │  • features - Task units with dependencies         │     │
│  └────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────┘
```

### Request Flow Example

1. **User sends chat message** via WebSocket
2. **Frontend** transmits to backend WebSocket endpoint
3. **OrchestratorService** logs message to database
4. **Claude SDK** executes orchestrator agent with chat history
5. **Agent** may invoke management tools (create_agent, command_agent, etc.)
6. **Management tools** interact with AgentManager to spawn/control sub-agents
7. **Sub-agents** execute in parallel, stream responses back
8. **WebSocketManager** broadcasts all events to frontend
9. **Database** captures all logs, costs, and state changes
10. **Frontend** renders markdown, updates UI in real-time

---

## Key Components

### Backend Modules (`orchestrator/backend/modules/`)

**Total:** ~12,700 lines of Python across 26 modules

#### Core Services

| Module | Size | Purpose |
|--------|------|---------|
| `orchestrator_service.py` | 45 KB | Meta-orchestrator agent execution with WebSocket streaming |
| `agent_manager.py` | 89 KB | Sub-agent creation, lifecycle management, tool implementations |
| `database.py` | 51 KB | PostgreSQL operations with connection pooling |
| `rapids_database.py` | 26 KB | RAPIDS-specific database operations (workspaces, projects, features) |

#### Workflow & Execution

| Module | Size | Purpose |
|--------|------|---------|
| `phase_engine.py` | 16 KB | RAPIDS phase validation and transition logic |
| `workflow_runner.py` | 19 KB | Interactive guided workflow execution |
| `autonomous_executor.py` | 26 KB | Fresh-context agent spawning for feature DAG |
| `feature_dag.py` | 18 KB | Dependency graph construction and topological sorting |

#### Infrastructure

| Module | Size | Purpose |
|--------|------|---------|
| `workspace_manager.py` | 13 KB | Workspace and project file management |
| `plugin_loader.py` | 8 KB | Dynamic archetype plugin discovery and loading |
| `websocket_manager.py` | 9 KB | WebSocket connection management and broadcasting |
| `git_worktree.py` | 10 KB | Git worktree isolation for agents |
| `git_utils.py` | 9 KB | Git operations (branch, commit, status) |
| `file_tracker.py` | 9 KB | File change tracking across git operations |

#### Supporting Modules

| Module | Size | Purpose |
|--------|------|---------|
| `hooks.py` | 17 KB | Agent event hooks (pre/post tool, stop) |
| `orchestrator_hooks.py` | 5 KB | Orchestrator-specific hooks |
| `command_agent_hooks.py` | 20 KB | Sub-agent command hooks |
| `logger.py` | 6 KB | Rich-based structured logging |
| `config.py` | 10 KB | Configuration management |
| `single_agent_prompt.py` | 11 KB | AI summarization utilities |
| `slash_command_parser.py` | 9 KB | Custom slash command parsing |
| `project_state.py` | 9 KB | Project state management |
| `subagent_loader.py` | 8 KB | Subagent template loading |

### Frontend Structure (`orchestrator/frontend/src/`)

```
src/
├── App.vue                    # Root component with chat interface
├── main.ts                    # Vue app initialization
├── types.d.ts                 # TypeScript type definitions
│
├── components/                # Vue 3 components (17 files)
│   ├── ChatInterface.vue      # Main chat UI
│   ├── WorkspacePanel.vue     # Workspace management
│   ├── ProjectCard.vue        # Project display
│   ├── FeatureDAG.vue         # Dependency visualization
│   └── ...
│
├── stores/                    # Pinia state management (5 stores)
│   ├── chat.ts               # Chat state and WebSocket handling
│   ├── workspace.ts          # Workspace/project state
│   ├── agent.ts              # Agent status tracking
│   └── ...
│
├── services/                  # API clients (9 services)
│   ├── websocket.ts          # WebSocket client
│   ├── api.ts                # REST API client
│   ├── workspace.ts          # Workspace API calls
│   └── ...
│
├── composables/               # Vue composables (7 files)
│   ├── useWebSocket.ts       # WebSocket hook
│   ├── useMarkdown.ts        # Markdown rendering
│   └── ...
│
├── utils/                     # Utility functions (4 files)
│   ├── formatters.ts         # Data formatting
│   └── validators.ts         # Input validation
│
└── styles/                    # Global styles (3 files)
    └── main.css              # CSS variables and themes
```

### Database Schema (`orchestrator/db/migrations/`)

**14 migration files** creating 10 tables with indexes, functions, and triggers

#### Orchestration Tables

1. **orchestrator_agents** - Singleton meta-orchestrator instance
   - session_id, system_prompt, status, working_dir
   - input_tokens, output_tokens, total_cost
   - metadata (JSONB), created_at, updated_at

2. **agents** - Sub-agent registry
   - orchestrator_agent_id (FK), name, model, system_prompt
   - working_dir, git_worktree, status, session_id
   - adw_id, adw_step (workflow tracking)
   - cost tracking, metadata, archival

3. **prompts** - User/orchestrator messages
   - agent_id (FK), task_slug, author (engineer | orchestrator_agent)
   - prompt_text, summary (AI-generated), timestamp

4. **agent_logs** - Unified event log
   - agent_id (FK), session_id, task_slug, adw_id, adw_step
   - event_category (hook | response), event_type
   - content, payload (JSONB), summary, timestamp

5. **system_logs** - Application logs
   - file_path, adw_id, adw_step
   - level (DEBUG | INFO | WARNING | ERROR)
   - message, summary, metadata (JSONB)

6. **orchestrator_chat** - 3-way conversation
   - orchestrator_agent_id (FK), agent_id (FK, optional)
   - sender_type (user | orchestrator | agent)
   - receiver_type (user | orchestrator | agent)
   - message, summary, metadata (JSONB)

#### RAPIDS Tables

7. **workspaces** - Project containers
   - name, description, root_path
   - status (active | archived | paused)
   - metadata (JSONB)

8. **projects** - Software projects
   - workspace_id (FK), name, repo_path, repo_url
   - archetype (greenfield | brownfield | enhancement | etc.)
   - current_phase (research | analysis | plan | implement | deploy | sustain)
   - phase_status (not_started | in_progress | blocked | review | complete)
   - plugin_id, priority, metadata (JSONB), archived

9. **project_phases** - Phase history
   - project_id (FK), phase, status
   - started_at, completed_at
   - entry_criteria_met, exit_criteria_met
   - artifacts (JSONB), notes, metadata (JSONB)

10. **features** - Task units
    - project_id (FK), name, description
    - depends_on (JSONB array of feature IDs)
    - acceptance_criteria (JSONB array)
    - status (planned | in_progress | complete | blocked | deferred)
    - priority, estimated_complexity
    - assigned_agent_id (FK to agents), spec_file
    - metadata (JSONB)

---

## Data Models

### Pydantic Models (`orchestrator/db/models.py`, `rapids_models.py`)

All database tables have corresponding Pydantic models with:
- Automatic UUID conversion (asyncpg UUID ↔ Python UUID)
- JSON serialization/deserialization for JSONB fields
- Type safety and validation
- Field defaults and constraints

**Key Features:**
- `@field_validator` decorators for type conversion
- `from_attributes = True` for ORM-style initialization
- Custom `json_encoders` for UUID and datetime serialization
- Literal types for enum fields (status, phase, level, etc.)

**Example Model Structure:**

```python
class Agent(BaseModel):
    id: UUID
    orchestrator_agent_id: UUID
    name: str
    model: str
    system_prompt: Optional[str] = None
    working_dir: Optional[str] = None
    git_worktree: Optional[str] = None
    status: Literal['idle', 'executing', 'waiting', 'blocked', 'complete']
    session_id: Optional[str] = None
    adw_id: Optional[str] = None
    adw_step: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost: float = 0.0
    archived: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @field_validator('id', 'orchestrator_agent_id', mode='before')
    @classmethod
    def convert_uuid(cls, v):
        if isinstance(v, UUID):
            return v
        return UUID(str(v))
```

---

## Plugin System

### Architecture

Plugins enable archetype-specific customization without modifying core code.

**Location:** `.claude/rapids-plugins/<archetype>/`

**Plugin Structure:**

```
<archetype>/
├── plugin.json           # Phase definitions, criteria, agents
├── agents/              # Agent templates (markdown)
│   ├── researcher.md
│   ├── architect.md
│   ├── planner.md
│   ├── feature-builder.md
│   └── ...
├── workflows/           # Guided workflow templates (markdown)
│   ├── research-workflow.md
│   ├── analysis-workflow.md
│   └── plan-workflow.md
├── commands/            # Custom slash commands
├── skills/              # Reusable skill definitions
└── hooks/               # Custom event handlers
```

### Plugin Configuration (`plugin.json`)

```json
{
  "name": "greenfield",
  "archetype": "greenfield",
  "description": "Plugin for greenfield projects...",
  "version": "1.0.0",
  "phases": {
    "<phase-name>": {
      "entry_criteria": ["criterion1", "criterion2"],
      "exit_criteria": ["criterion1", "criterion2"],
      "default_agents": ["agent-name"],
      "skills": ["skill1", "skill2"],
      "prompt_supplement": "Context injected into agents..."
    }
  }
}
```

### Greenfield Plugin Example

**7 Specialized Agents:**
1. **researcher** - Domain research, technology landscape
2. **architect** - Solution design, technology selection
3. **planner** - Feature decomposition, spec writing
4. **feature-builder** - Code implementation
5. **tester** - Test writing and execution
6. **deployer** - Infrastructure and CI/CD setup
7. **monitor** - Monitoring and operational setup

**3 Guided Workflows:**
1. **research-workflow.md** - Problem statement, technology landscape, constraints
2. **analysis-workflow.md** - Architecture design, technology stack, ADRs
3. **plan-workflow.md** - Feature decomposition, dependency DAG, acceptance criteria

**Phase Definitions:**
- **Research**: Define problem, survey technologies, identify constraints
- **Analysis**: Design architecture, select stack, document decisions
- **Plan**: Decompose features, build DAG, write specs
- **Implement**: Execute DAG autonomously with fresh-context agents
- **Deploy**: Setup infrastructure, CI/CD, deployment automation
- **Sustain**: Establish monitoring, alerting, runbooks

---

## Technology Stack

### Backend Technologies

| Category | Technology | Version | Purpose |
|----------|-----------|---------|---------|
| **Language** | Python | 3.12+ | Core backend language |
| **Package Manager** | Astral UV | Latest | Fast Python package/project manager |
| **Web Framework** | FastAPI | 0.115+ | REST API and WebSocket server |
| **ASGI Server** | uvicorn | 0.30+ | Production ASGI server |
| **Database Driver** | asyncpg | 0.29+ | Async PostgreSQL driver |
| **Validation** | pydantic | 2.0+ | Data validation and serialization |
| **AI Framework** | claude-agent-sdk | 0.1+ | Claude Agent orchestration |
| **WebSocket** | websockets | 12.0+ | WebSocket protocol |
| **HTTP Client** | httpx | 0.27+ | Async HTTP client |
| **Terminal UI** | rich | 13.0+ | Structured logging and displays |
| **Environment** | python-dotenv | 1.0+ | Environment variable management |

**Dev Dependencies:**
- pytest (8.0+) - Testing framework
- pytest-asyncio (0.23+) - Async test support
- ruff (0.4+) - Fast Python linter/formatter

### Frontend Technologies

| Category | Technology | Version | Purpose |
|----------|-----------|---------|---------|
| **Framework** | Vue | 3.4+ | Reactive UI framework |
| **Build Tool** | Vite | 5.0+ | Fast dev server and bundler |
| **Language** | TypeScript | 5.0+ | Type-safe JavaScript |
| **State Management** | Pinia | 2.1+ | Vue state management |
| **HTTP Client** | axios | 1.6+ | Promise-based HTTP client |
| **Markdown** | marked | 16.4+ | Markdown to HTML parser |
| **Sanitization** | dompurify | 3.3+ | HTML sanitization |
| **Syntax Highlighting** | highlight.js | 11.11+ | Code syntax highlighting |

**Dev Dependencies:**
- @vitejs/plugin-vue (5.0+) - Vue plugin for Vite
- vue-tsc (1.8+) - Vue TypeScript compiler
- TypeScript type definitions for dependencies

### Infrastructure

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Database** | PostgreSQL 16 | Persistent data storage |
| **Cloud DB** | NeonDB | Serverless PostgreSQL (production) |
| **Containerization** | Docker Compose | Local development database |
| **API Protocol** | REST + WebSocket | HTTP/JSON + real-time streaming |

### Development Tools

- **Version Control:** Git with worktree support
- **Testing:** pytest with real database connections
- **Linting:** ruff for Python
- **Type Checking:** TypeScript, Pydantic
- **Logging:** Rich panels and structured logs

---

## Directory Structure

```
agentic-meta-orchestrator/
├── .claude/                          # Claude Code configuration
│   ├── agents/                       # Custom agent definitions
│   ├── commands/                     # Slash commands
│   ├── data/                         # Session data
│   ├── hooks/                        # Lifecycle hooks
│   ├── output-styles/                # Display formatting
│   ├── rapids-plugins/               # Archetype plugins
│   │   └── greenfield/               # Greenfield plugin
│   │       ├── plugin.json
│   │       ├── agents/               # 7 agent templates
│   │       ├── workflows/            # 3 guided workflows
│   │       ├── commands/
│   │       ├── skills/
│   │       └── hooks/
│   ├── settings.json                 # Claude settings
│   └── settings.local.json           # Local overrides
│
├── orchestrator/                     # Main application
│   ├── backend/                      # FastAPI backend
│   │   ├── main.py                   # FastAPI app entry point (47KB)
│   │   ├── start_be.sh               # Backend startup script
│   │   ├── modules/                  # 26 Python modules (~12,700 lines)
│   │   │   ├── orchestrator_service.py
│   │   │   ├── agent_manager.py
│   │   │   ├── database.py
│   │   │   ├── rapids_database.py
│   │   │   ├── phase_engine.py
│   │   │   ├── feature_dag.py
│   │   │   ├── workspace_manager.py
│   │   │   ├── plugin_loader.py
│   │   │   ├── workflow_runner.py
│   │   │   ├── autonomous_executor.py
│   │   │   ├── websocket_manager.py
│   │   │   ├── git_worktree.py
│   │   │   ├── hooks.py
│   │   │   ├── logger.py
│   │   │   ├── config.py
│   │   │   └── ...
│   │   ├── prompts/                  # System prompts
│   │   ├── logs/                     # Runtime logs
│   │   └── tests/                    # 14 test files
│   │
│   ├── db/                           # Database layer
│   │   ├── models.py                 # Pydantic orchestration models
│   │   ├── rapids_models.py          # Pydantic RAPIDS models
│   │   ├── run_migrations.py         # Migration runner
│   │   ├── sync_models.py            # Schema sync utility
│   │   └── migrations/               # 14 SQL migration files
│   │       ├── 0_orchestrator_agents.sql
│   │       ├── 1_agents.sql
│   │       ├── 2_prompts.sql
│   │       ├── 3_agent_logs.sql
│   │       ├── 4_system_logs.sql
│   │       ├── 5_indexes.sql
│   │       ├── 6_functions.sql
│   │       ├── 7_triggers.sql
│   │       ├── 8_orchestrator_chat.sql
│   │       ├── 9_workspaces.sql
│   │       ├── 10_projects.sql
│   │       ├── 11_project_phases.sql
│   │       ├── 12_features.sql
│   │       └── 13_link_workspace_project.sql
│   │
│   ├── frontend/                     # Vue 3 frontend
│   │   ├── index.html                # HTML entry point
│   │   ├── package.json              # npm dependencies
│   │   ├── vite.config.ts            # Vite configuration
│   │   ├── tsconfig.node.json        # TypeScript config
│   │   ├── start_fe.sh               # Frontend startup script
│   │   ├── public/                   # Static assets
│   │   ├── node_modules/             # npm packages
│   │   └── src/                      # Source code
│   │       ├── App.vue               # Root component
│   │       ├── main.ts               # App initialization
│   │       ├── types.d.ts            # TypeScript types
│   │       ├── components/           # 17 Vue components
│   │       ├── stores/               # 5 Pinia stores
│   │       ├── services/             # 9 API services
│   │       ├── composables/          # 7 composables
│   │       ├── utils/                # 4 utility modules
│   │       ├── styles/               # 3 style files
│   │       └── config/               # Configuration
│   │
│   └── .env                          # Orchestrator env vars
│
├── workspace/                        # Multi-project workspace
│   ├── workspace.json                # Workspace metadata
│   └── projects/                     # Project repositories
│
├── specs/                            # Project specifications
├── logs/                             # Application logs
│
├── .git/                             # Git repository
├── .venv/                            # Python virtual environment
├── .pytest_cache/                    # Pytest cache
├── .rapids/                          # RAPIDS state (per project)
│
├── .env                              # Environment variables
├── .env.sample                       # Environment template
├── .gitignore                        # Git ignore rules
├── docker-compose.yml                # PostgreSQL container
├── pyproject.toml                    # Python project config
├── uv.lock                           # UV lock file
├── README.md                         # Project readme
└── CLAUDE.md                         # Development guidelines
```

---

## Design Patterns

### 1. Three-Phase Logging Pattern

Every orchestrator execution follows this pattern:

```python
# Phase 1: Pre-execution - Log user message
await insert_chat_message(
    sender_type='user',
    receiver_type='orchestrator',
    message=user_message
)

# Phase 2: Execution - Stream response via WebSocket
async for event in claude_client.execute(prompt):
    await ws_manager.broadcast(event)

# Phase 3: Post-execution - Log response, update costs
await insert_chat_message(
    sender_type='orchestrator',
    receiver_type='user',
    message=response
)
await update_orchestrator_costs(tokens, cost)
```

**Benefits:**
- Complete audit trail
- Resumable sessions
- Cost tracking
- Error recovery

### 2. Fresh-Context Agents

Each feature in the DAG gets a new agent instance:

```python
# Traditional approach (context pollution)
agent.execute(feature1)  # Context: feature1
agent.execute(feature2)  # Context: feature1 + feature2 (polluted!)

# Fresh-context approach (clean slate)
agent1 = create_agent(spec=feature1_spec)  # Only knows feature1
agent1.execute()

agent2 = create_agent(spec=feature2_spec)  # Only knows feature2
agent2.execute()
```

**Benefits:**
- No context pollution
- Parallel execution
- Isolated failures
- Reproducible builds

### 3. Hook-Based Event System

Agents emit events at key lifecycle points:

```python
# Pre-tool hook - Before tool execution
@pre_tool_hook
async def before_tool(tool_name, parameters):
    await log_event('pre_tool', tool_name, parameters)

# Post-tool hook - After tool execution
@post_tool_hook
async def after_tool(tool_name, result):
    await log_event('post_tool', tool_name, result)

# Stop hook - Agent completion
@stop_hook
async def on_stop(response, token_usage):
    await update_costs(token_usage)
    await log_event('stop', response)
```

**Benefits:**
- Centralized logging
- Cost tracking
- Event streaming
- Extensibility

### 4. Converge-Then-Execute Workflow

**RAP Phases** (Research, Analysis, Plan) use guided workflows to converge on specifications:

```
Research → Analysis → Plan
   ↓          ↓         ↓
[Guided]  [Guided]  [Guided]
   ↓          ↓         ↓
Problem    Arch      Feature
  Stmt     Design      DAG
```

**Implement Phase** executes autonomously using the converged spec:

```
Feature DAG → Topological Sort → Fresh-Context Agents → Parallel Execution
```

**Benefits:**
- Human validation before automation
- Clear specifications
- Autonomous execution
- Minimal manual intervention

### 5. Type-Safe Database Layer

Pydantic models mirror SQL schema exactly:

```sql
-- SQL Schema (migrations/1_agents.sql)
CREATE TABLE agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    status TEXT CHECK (status IN ('idle', 'executing', ...)),
    metadata JSONB DEFAULT '{}'::jsonb
);
```

```python
# Pydantic Model (db/models.py)
class Agent(BaseModel):
    id: UUID
    name: str
    status: Literal['idle', 'executing', 'waiting', 'blocked', 'complete']
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator('id', mode='before')
    @classmethod
    def convert_uuid(cls, v):
        return UUID(str(v)) if not isinstance(v, UUID) else v
```

**Benefits:**
- Type safety throughout stack
- Automatic validation
- IDE autocomplete
- Reduced bugs

### 6. WebSocket Event Broadcasting

All agent events stream to all connected clients:

```python
# Backend: Broadcast events
async def execute_agent(prompt):
    async for event in agent.execute(prompt):
        await ws_manager.broadcast({
            'type': event.type,
            'data': event.data,
            'timestamp': datetime.now()
        })

# Frontend: Receive events
ws.on('message', (event) => {
    if (event.type === 'thinking') {
        displayThinking(event.data)
    } else if (event.type === 'tool_use') {
        displayToolUse(event.data)
    }
})
```

**Benefits:**
- Real-time UI updates
- Multiple client support
- Event replay
- Debugging visibility

### 7. Plugin-Based Extensibility

Core system remains unchanged; behavior customized via plugins:

```
Core System (Fixed)
    ↓
Plugin Loader (Dynamic)
    ↓
Archetype Plugin (Configurable)
    ↓ (inject)
• Phase definitions
• Entry/exit criteria
• Agent templates
• Workflow templates
• Prompt supplements
```

**Benefits:**
- Extensible without code changes
- Archetype-specific optimization
- Easy experimentation
- Version-controlled plugins

### 8. Git Worktree Isolation

Agents work in isolated git worktrees to prevent conflicts:

```bash
# Main repo
/project/
  ├── .git/
  └── src/

# Agent worktrees
/project/.worktrees/
  ├── agent-feature-1/    # Isolated copy
  │   └── src/
  └── agent-feature-2/    # Isolated copy
      └── src/
```

**Benefits:**
- Parallel feature development
- No merge conflicts
- Independent testing
- Clean rollback

---

## Development Workflow

### Initial Setup

```bash
# 1. Clone repository
git clone <repo-url>
cd agentic-meta-orchestrator

# 2. Copy environment template
cp .env.sample .env

# 3. Configure environment
# Edit .env with database URL, ports, model selection
DATABASE_URL=postgresql://user:password@localhost:5432/rapids_orchestrator
BACKEND_PORT=9403
FRONTEND_PORT=5175
ORCHESTRATOR_MODEL=claude-sonnet-4-5-20250929

# 4. Start PostgreSQL (Docker)
docker-compose up -d

# 5. Install Python dependencies (using UV)
uv sync

# 6. Run database migrations
uv run python orchestrator/db/run_migrations.py

# 7. Install frontend dependencies
cd orchestrator/frontend
npm install
cd ../..
```

### Running the Application

**Option 1: Separate terminals**

```bash
# Terminal 1: Backend
cd orchestrator/backend
./start_be.sh

# Terminal 2: Frontend
cd orchestrator/frontend
./start_fe.sh
```

**Option 2: Background processes**

```bash
# Start both together
cd orchestrator/backend && ./start_be.sh &
cd orchestrator/frontend && ./start_fe.sh &
```

**Access:**
- Frontend: `http://localhost:5175`
- Backend API: `http://localhost:9403`
- WebSocket: `ws://localhost:9403/ws`

### Database Management

**Run migrations:**
```bash
uv run python orchestrator/db/run_migrations.py
```

**Sync models (verify schema matches Pydantic):**
```bash
uv run python orchestrator/db/sync_models.py
```

**Reset database (DANGER):**
```bash
docker-compose down -v  # Destroys all data
docker-compose up -d
uv run python orchestrator/db/run_migrations.py
```

### Testing

**Run all tests:**
```bash
uv run pytest
```

**Run specific test file:**
```bash
uv run pytest orchestrator/backend/tests/test_database.py
```

**Run with verbose output:**
```bash
uv run pytest -v -s
```

**Philosophy:**
- Use **real database connections** (no mocking)
- Create **ephemeral test data** (cleanup after tests)
- Test **integration**, not just units
- Verify **end-to-end workflows**

### Plugin Development

**Create new archetype plugin:**

```bash
# 1. Create plugin directory
mkdir -p .claude/rapids-plugins/my-archetype

# 2. Create plugin.json
cat > .claude/rapids-plugins/my-archetype/plugin.json <<EOF
{
  "name": "my-archetype",
  "archetype": "my-archetype",
  "description": "Custom archetype for...",
  "version": "1.0.0",
  "phases": {
    "research": { ... },
    "analysis": { ... },
    ...
  }
}
EOF

# 3. Create agent templates
mkdir -p .claude/rapids-plugins/my-archetype/agents
# Add agent markdown files

# 4. Create workflows
mkdir -p .claude/rapids-plugins/my-archetype/workflows
# Add workflow markdown files

# 5. Test plugin loading
uv run python -c "
from modules.plugin_loader import PluginLoader
loader = PluginLoader('.claude/rapids-plugins')
plugin = loader.load_plugin('my-archetype')
print(plugin)
"
```

### Code Style

**Python:**
- **Linter/Formatter:** ruff
- **Line length:** 120 characters
- **Target version:** Python 3.12
- **Type hints:** Required for public functions

**TypeScript:**
- **Line length:** 120 characters
- **Quotes:** Single quotes
- **Semicolons:** Required

**Commands:**
```bash
# Format Python
uv run ruff format .

# Lint Python
uv run ruff check .

# Format TypeScript
cd orchestrator/frontend
npm run lint
```

---

## Configuration

### Environment Variables (`.env`)

```bash
# Database
DATABASE_URL=postgresql://user:password@host:5432/rapids_orchestrator

# Backend
BACKEND_HOST=127.0.0.1
BACKEND_PORT=9403

# Frontend
FRONTEND_HOST=127.0.0.1
FRONTEND_PORT=5175

# Orchestrator
ORCHESTRATOR_MODEL=claude-sonnet-4-5-20250929

# Logging
LOG_LEVEL=INFO
LOG_DIR=orchestrator/backend/logs

# IDE
IDE_COMMAND=code
IDE_ENABLED=true
```

### Database Connection Strings

**Local Docker:**
```
postgresql://rapids:rapids_dev_2024@localhost:5434/rapids_orchestrator
```

**NeonDB (Production):**
```
postgresql://user:password@ep-xyz.region.aws.neon.tech/rapids_orchestrator?sslmode=require
```

### Model Selection

Available models (via Claude Agent SDK):
- `claude-sonnet-4-5-20250929` - Recommended for orchestrator
- `claude-opus-4-20250514` - Maximum capability
- `claude-haiku-4-20250611` - Fast responses

### Working Directory

Default: Project root directory

Override:
```bash
# CLI argument
./start_be.sh --cwd /path/to/workspace

# Environment variable
ORCHESTRATOR_WORKING_DIR=/path/to/workspace
```

### Session Management

**Start new session:**
```bash
./start_be.sh
```

**Resume existing session:**
```bash
./start_be.sh --session <session-id>
```

Session ID displayed in startup logs and stored in database.

### Claude Code Settings (`.claude/settings.json`)

```json
{
  "model": "claude-sonnet-4-5-20250929",
  "permissions": {
    "bash": "allow-all",
    "read": "allow-all",
    "write": "allow-all"
  },
  "hooks": {
    "beforeToolUse": [],
    "afterToolUse": [],
    "onStop": []
  }
}
```

---

## Key Takeaways

### What Makes This System Unique

1. **Multi-Layer Orchestration**: Meta-orchestrator manages sub-agents, enabling complex workflows
2. **Structured Methodology**: RAPIDS phases enforce best practices with validation gates
3. **Fresh-Context Execution**: Each feature gets isolated agent, preventing context pollution
4. **Plugin Extensibility**: Archetypes customize behavior without core code changes
5. **Real-Time Visibility**: WebSocket streaming provides live view into all agent activities
6. **Type-Safe Architecture**: Pydantic models ensure type safety from database to API
7. **Production-Grade**: PostgreSQL persistence, cost tracking, error handling, session resumption

### Ideal Use Cases

- **Greenfield Projects**: Build from scratch with optimal architecture
- **Feature Development**: Decompose large features into parallel tasks
- **Multi-Project Management**: Coordinate related projects in workspace
- **AI-Powered Development**: Leverage specialized agents for different phases
- **Structured Workflows**: Enforce methodology with phase gates

### Architecture Highlights

- **~1,500 Python files** (including dependencies)
- **~12,700 lines** of backend logic across 26 modules
- **10 database tables** with full migration history
- **7 specialized agents** in greenfield plugin
- **14 test suites** with real database integration
- **Full-stack TypeScript/Python** type safety

### Development Philosophy

- **No mocking** - Real database connections in tests
- **Schema-model sync** - SQL migrations mirror Pydantic models
- **UV-based workflow** - Astral UV for all Python operations
- **Fresh-context agents** - Isolated feature execution
- **WebSocket streaming** - Real-time UI updates
- **Plugin extensibility** - Archetype-based customization

---

## Quick Reference

### Common Commands

```bash
# Start backend
cd orchestrator/backend && ./start_be.sh

# Start frontend
cd orchestrator/frontend && ./start_fe.sh

# Run migrations
uv run python orchestrator/db/run_migrations.py

# Run tests
uv run pytest

# Format code
uv run ruff format .

# Start database
docker-compose up -d

# Stop database
docker-compose down
```

### API Endpoints

**REST:**
- `GET /api/workspaces` - List workspaces
- `POST /api/workspaces` - Create workspace
- `GET /api/projects` - List projects
- `POST /api/projects` - Create project
- `GET /api/features` - List features
- `POST /api/chat` - Send chat message

**WebSocket:**
- `ws://localhost:9403/ws` - Chat stream

### File Locations

- **Migrations:** `orchestrator/db/migrations/`
- **Models:** `orchestrator/db/models.py`, `rapids_models.py`
- **Backend:** `orchestrator/backend/modules/`
- **Frontend:** `orchestrator/frontend/src/`
- **Plugins:** `.claude/rapids-plugins/`
- **Logs:** `orchestrator/backend/logs/`
- **Project State:** `<project>/.rapids/`

---

**Document Version:** 1.0
**Generated:** March 22, 2026
**Project:** RAPIDS Meta-Orchestrator
**Repository:** `/Users/nbalawat/agentic-meta-orchestrator`
