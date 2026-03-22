---
description: "Orchestrate the Plan phase — decompose the project into features, build the dependency DAG, and produce implementation specifications."
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
---

# /plan Command — Greenfield Archetype

Execute the Plan phase of the RAPIDS workflow for a greenfield project. This phase produces the feature DAG and specifications that drive autonomous implementation.

## What This Command Does

1. **Verify Phase**: Confirm the project is in the Plan phase and that Analysis exit criteria are met.
2. **Load Context**: Read all research and analysis artifacts to provide full project context to the planner.
3. **Load Workflow**: Load the plan workflow from `workflows/plan-workflow.md`.
4. **Launch Planner Agent**: Spawn the `planner` agent with full context and plan workflow.
5. **Execute Sections**: Walk through each workflow section:
   - Feature Identification — break architecture into discrete features
   - Dependency Mapping — build the feature DAG
   - Acceptance Criteria — define testable criteria per feature
   - Priority & Sizing — assign effort and execution waves
   - Specification Compilation — produce self-contained feature specs
6. **Validate DAG**: Parse and validate `feature-dag.json` for acyclicity and completeness.
7. **Validate Specs**: Verify every feature in the DAG has a corresponding `spec.md` and `acceptance-criteria.md`.
8. **Report Status**: Display the feature DAG, execution waves, and readiness for implementation.

## Usage

```
/plan                         # Run the full plan workflow
/plan --section features      # Run only Feature Identification
/plan --validate              # Validate existing DAG and specs without re-planning
/plan --status                # Show plan phase status, feature count, DAG health
```

## Interaction Model

The plan phase presents the decomposition for user review:
- Feature list is presented for confirmation before building the DAG
- The DAG is visualized and reviewed for correctness
- Execution waves are presented with estimated effort
- The user can request feature splits, merges, or re-prioritization

## Critical Output

The most important outputs of this phase are:
- `.rapids/plan/feature-dag.json` — Machine-readable DAG consumed by the orchestrator
- `.rapids/plan/features/<name>/spec.md` — Self-contained specs consumed by feature-builder agents

These artifacts must be complete and consistent for the `/implement` command to function.

## Artifacts Produced

All artifacts are written to `.rapids/plan/`:
- `feature-list.md`
- `feature-dag.json`
- `feature-dag.md`
- `execution-waves.md`
- `specification.md`
- `features/<feature-name>/spec.md` (one per feature)
- `features/<feature-name>/acceptance-criteria.md` (one per feature)
