# Engineering Rules for RAPIDS Meta-Orchestrator

## Do not mock tests

- Use real database connections
- Use real Claude Agent SDK agents
- IMPORTANT: Tests must be ephemeral — create test data, then clean it up after.

## Keep models.py in sync with migrations

Be sure to keep `orchestrator/db/models.py` and `orchestrator/db/rapids_models.py` in sync with the migrations in `orchestrator/db/migrations/*.sql`.

## Use .env file when needed and expose with python-dotenv

- Use python-dotenv to load environment variables from .env file

## IMPORTANT: Actually read the file

- When asked to read a file, read all of it — don't just read the first N lines.
- Read in chunks if too large. Use `wc -l <filename>` to get line counts.

## Use Astral UV, never raw python

- We're using Astral UV to manage our Python projects.
- Always use uv to run commands, never raw python.

## Python rich panels

- Always full width panels with rich.

## Git Commits

- IMPORTANT: Do NOT commit any changes unless explicitly asked.

## Avoid dict and prefer pydantic models

- Prefer pydantic models over dicts.
- For every database model, use the appropriate models file.

## Project Structure

- `orchestrator/` — The meta layer (orchestration engine)
  - `orchestrator/db/` — Database schema, models, migrations
  - `orchestrator/backend/` — FastAPI server + Claude Agent SDK modules
  - `orchestrator/frontend/` — Vue 3 + TypeScript UI
- `.claude/rapids-plugins/` — Archetype plugins (commands, skills, agents, workflows)
- `workspace/` — Workspace metadata and project registry
- Per-project state lives in `<project-repo>/.rapids/`

## RAPIDS Phases

Research → Analysis → Plan (convergence) → Implement → Deploy → Sustain (execution)
- RAP phases use guided workflow templates (interactive, section-by-section)
- Plan phase creates features in the database using MCP tools (NOT feature_dag.json)
- Implement phase executes features autonomously via the execution worker process

## Starting the Application

### Prerequisites
- Docker Desktop running
- Node.js 22+
- Python 3.12+ with Astral UV

### 1. Database
```bash
docker-compose up -d
```

### 2. Environment
```bash
cd orchestrator
cp .env.sample .env
# Edit .env — set CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY
```

### 3. Run Migrations
```bash
for f in orchestrator/db/migrations/*.sql; do
  docker exec -i rapids-postgres psql -U rapids -d rapids_orchestrator < "$f"
done
```

### 4. Backend (terminal 1)
```bash
cd orchestrator/backend
bash start_be.sh
```

### 5. Frontend (terminal 2)
```bash
cd orchestrator/frontend
npm install   # first time only
npm run dev
```

### 6. Execution Worker (terminal 3)
```bash
cd orchestrator/backend
bash start_worker.sh
```

### 7. Open Browser
```
http://127.0.0.1:5175
```

### Three Processes
| Process | Port | Purpose |
|---------|------|---------|
| Backend | 9403 | FastAPI server + WebSocket + MCP tools |
| Frontend | 5175 | Vue 3 UI (Kanban board, event stream, chat) |
| Worker | — | Picks up queued features, spawns builder agents |

### Authentication
- **OAuth Token** (recommended): Set `CLAUDE_CODE_OAUTH_TOKEN` in `.env`. Uses your Claude Code subscription. Get it via `claude auth login`.
- **API Key**: Set `ANTHROPIC_API_KEY` in `.env`. Billed directly to your Anthropic account.

## Architecture: Execution Pipeline

The orchestrator queues features in the `execution_runs` PostgreSQL table. The worker process (separate from the backend) polls for queued runs and spawns isolated Claude SDK sessions — no nesting conflicts.

```
Orchestrator (MCP tool: execute_ready_features)
  └── INSERT into execution_runs (status=queued)

Worker Process (start_worker.sh)
  └── Polls execution_runs every 5s
  └── For each queued run:
      ├── Create agent record in agents table (visible in sidebar)
      ├── Spawn Claude SDK session
      ├── Stream events to backend via HTTP webhook
      ├── On completion: run tests, update execution_run, archive agent
      └── Auto-queue next wave when dependencies satisfied

Frontend
  └── Polls GET /api/projects/{id}/execution-status every 3s
  └── Renders Kanban board from response
```

## Feature Management

Features are stored in the PostgreSQL `features` table (database-primary, NOT feature_dag.json). Phase agents have MCP tools to manage features directly:

- `create_features` — batch create with name-based dependency resolution
- `list_project_features` — list all with status
- `validate_feature_dag` — check for cycles/issues
- `delete_feature` — remove by name
