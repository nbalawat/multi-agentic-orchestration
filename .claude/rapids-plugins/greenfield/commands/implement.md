---
description: "Orchestrate autonomous feature implementation — execute the feature DAG by spawning fresh-context agents for each feature."
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
---

# /implement Command — Greenfield Archetype

Execute the Implement phase of the RAPIDS workflow for a greenfield project. This is the autonomous execution engine that builds the project feature-by-feature according to the DAG.

## What This Command Does

1. **Verify Phase**: Confirm the project is in the Implement phase and that Plan exit criteria are met.
2. **Load DAG**: Parse `.rapids/plan/feature-dag.json` and determine the current execution state.
3. **Identify Ready Features**: Find features whose dependencies are all marked complete.
4. **For Each Ready Feature**:
   a. Load the feature spec from `.rapids/plan/features/<name>/spec.md`
   b. Load acceptance criteria from `.rapids/plan/features/<name>/acceptance-criteria.md`
   c. Spawn a `feature-builder` agent with fresh context containing only:
      - The feature specification
      - The acceptance criteria
      - The project's tech stack summary
      - Interface contracts from completed dependency features
   d. The agent implements the feature, writes tests, and verifies they pass
   e. Spawn a `tester` agent to validate acceptance criteria independently
   f. If all tests pass, mark the feature as complete in the DAG
   g. If tests fail, mark the feature as failed and report the issue
5. **Update DAG State**: Write updated feature statuses back to `feature-dag.json`.
6. **Iterate**: Repeat from step 3 until all features are complete or no progress can be made.
7. **Integration Check**: Run the full test suite to verify cross-feature integration.
8. **Report Status**: Display implementation progress, completed features, and any failures.

## Usage

```
/implement                        # Execute all ready features in the DAG
/implement --feature user-auth    # Implement a specific feature only
/implement --status               # Show DAG execution status and progress
/implement --retry-failed         # Retry all features in failed state
/implement --dry-run              # Show what would be executed without running
```

## Execution Model

The implementation engine operates on these principles:
- **Fresh Context**: Each feature-builder agent starts with a clean context. It receives only the spec, acceptance criteria, and interface contracts — not the full project history.
- **DAG Order**: Features are executed in topological order. A feature is only started when all its dependencies are complete.
- **Fail Fast**: If a feature fails, dependent features are not attempted. The user is notified and can choose to retry or skip.
- **Idempotent**: Running `/implement` again continues from where it left off. Completed features are not re-executed.
- **Parallel Potential**: Features at the same DAG level with no mutual dependencies can theoretically run in parallel (controlled by orchestrator settings).

## Progress Tracking

Implementation progress is tracked in:
- `.rapids/plan/feature-dag.json` — Feature statuses (pending, in_progress, complete, failed)
- `.rapids/implement/logs/<feature-name>.md` — Per-feature execution logs
- `.rapids/implement/status.md` — Overall implementation progress summary
