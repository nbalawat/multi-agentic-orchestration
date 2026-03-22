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
- Plan phase must produce spec.md + feature_dag.json before Implement begins
- Implement phase executes features autonomously with fresh-context agents per feature
