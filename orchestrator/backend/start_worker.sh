#!/bin/bash
# Start the execution worker process
# This runs separately from the backend — spawns Claude SDK sessions
# for queued feature execution runs.

cd "$(dirname "$0")"
exec uv run python -m modules.execution_worker
