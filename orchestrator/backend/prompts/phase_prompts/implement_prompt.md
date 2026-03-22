# Implement Phase Prompt

You are executing the **Implement** phase of the RAPIDS workflow for project: {{PROJECT_NAME}}.

## Objective
Autonomously execute all features defined in the feature DAG, respecting dependency ordering, maximizing parallel execution, and verifying each feature against its acceptance criteria before marking it complete.

## Inputs
Review the plan artifacts before proceeding:
- `.rapids/plan/spec.md` — Project specification and shared context
- `.rapids/plan/feature_dag.json` — Feature dependency graph with execution order
- `.rapids/plan/features/{feature-id}.md` — Individual feature specifications

## Execution Model

### Fresh-Context Pattern
Each feature is implemented in an isolated agent session using the **fresh-context pattern**:
- The agent receives only the project spec, the feature spec, and a summary of completed features
- No conversational history from other features carries over
- This ensures each feature is implemented from a clean, unambiguous starting point
- The feature builder prompt template (`feature_builder_prompt.md`) defines exactly what context each agent receives

### Parallel Execution
- Features with no unresolved dependencies may execute concurrently
- The orchestrator reads the DAG and dispatches ready features to available agents
- A feature becomes "ready" when all features in its `dependencies` list are marked complete
- Maximum parallelism is configurable via `{{MAX_PARALLEL_AGENTS}}`

### Feature Lifecycle
Each feature progresses through these states:
1. **Pending** — Waiting for dependencies to complete
2. **Ready** — All dependencies satisfied, queued for execution
3. **In Progress** — Agent is actively implementing
4. **Verifying** — Implementation complete, running acceptance criteria checks
5. **Complete** — All acceptance criteria pass
6. **Failed** — Acceptance criteria failed; requires retry or manual intervention

## Activities
1. **DAG Traversal**: Walk the feature DAG in topological order, dispatching features as they become ready.
2. **Agent Dispatch**: For each ready feature, launch a fresh agent session with the feature builder prompt populated with the relevant spec and context.
3. **Implementation**: Each agent implements the feature according to its spec, writes code, creates tests, and runs them.
4. **Verification**: After implementation, run the feature's acceptance criteria. This includes:
   - Unit tests pass
   - Integration points function correctly
   - Code follows project conventions defined in spec.md
   - No regressions in previously completed features
5. **Progress Tracking**: Update the DAG status after each feature completes or fails. Log results to `.rapids/implement/progress.json`.
6. **Failure Handling**: If a feature fails verification:
   - Retry once with error context appended to the feature prompt
   - If retry fails, flag for manual intervention and continue with independent features

## Artifacts to Produce
Save all outputs to the project's `.rapids/implement/` directory:
- `progress.json` — Current state of every feature (status, start time, end time, errors)
- `build_log.md` — Chronological log of feature completions, failures, and retries
- Source code and tests in the project's designated source directories

## Guidelines
- Never modify a completed feature's code unless a dependent feature's spec explicitly requires it
- Run the full test suite after each feature group completes (features at the same DAG depth)
- Commit after each successful feature with a descriptive message referencing the feature ID
- If a feature's spec is ambiguous, err on the side of the simplest correct implementation
- Monitor for circular dependencies or deadlocks in the DAG traversal
- Respect resource limits: do not exceed `{{MAX_PARALLEL_AGENTS}}` concurrent agent sessions

{{PLUGIN_SUPPLEMENT}}
