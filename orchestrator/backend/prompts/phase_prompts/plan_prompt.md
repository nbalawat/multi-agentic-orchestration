# Plan Phase Agent Prompt

You are executing the **Plan** phase of the RAPIDS workflow for project: **{{PROJECT_NAME}}**.

This is the critical convergence phase where architecture decisions crystallize into an executable plan. The quality of planning directly determines the success of autonomous implementation.

## Objective
Decompose the solution into discrete features, define their specifications, establish dependency ordering via a feature DAG, and produce specifications detailed enough for autonomous execution.

## Project Context
{{PROJECT_CONTEXT}}

## Inputs
Review the analysis artifacts before proceeding:
- `.rapids/analysis/solution-decision.md` — Selected approach and rationale
- `.rapids/analysis/architecture.md` — System architecture and component boundaries
- `.rapids/analysis/tech-stack.md` — Technology selections
- `.rapids/analysis/data-model.md` — Data storage design

## Activities
1. **Feature Identification**: Break the solution into independently implementable features. Each should be 200-500 lines of code change, testable, with clear boundaries.
2. **Dependency Mapping**: Map dependencies between features. Minimize dependencies to maximize parallelism.
3. **Acceptance Criteria**: Write 3-7 testable criteria per feature using Given/When/Then format.
4. **Priority & Sizing**: Assign priority (P0/P1/P2) and effort estimates (S/M/L/XL). Group into execution waves.
5. **Specification Writing**: For each feature, write a self-contained spec with acceptance criteria, file paths, API contracts, and test requirements.

## Artifacts to Produce

### 1. Feature DAG (Database — use MCP tools)

**CRITICAL: Use the `create_features` MCP tool to create features in the database. Do NOT write feature_dag.json manually.**

You have these MCP tools available:
- **`create_features(features)`** — Create features with dependencies. Pass a JSON array:
  ```json
  [
    {"name": "auth-models", "description": "User and session models", "priority": 1, "depends_on": [], "acceptance_criteria": ["User model exists", "Session model exists"], "estimated_complexity": "medium"},
    {"name": "auth-endpoints", "description": "Login/logout API", "priority": 1, "depends_on": ["auth-models"], "acceptance_criteria": ["POST /login works", "POST /logout works"], "estimated_complexity": "medium"}
  ]
  ```
  Use feature NAMES in `depends_on` — they resolve automatically.
- **`list_project_features()`** — List all features with status and dependencies
- **`validate_feature_dag()`** — Check for cycles, missing deps, structural issues
- **`delete_feature(feature_name)`** — Remove a feature if you need to restructure

### 2. File Artifacts (write to `.rapids/plan/`)

| File | Description | Required |
|------|-------------|----------|
| `specification.md` | Master project specification (goals, architecture, conventions) | Yes |
| `features/<name>/spec.md` | Self-contained spec per feature | Yes |
| `features/<name>/acceptance-criteria.md` | Testable acceptance criteria per feature | Yes |
| `feature-list.md` | Human-readable list of features with descriptions | Optional |
| `execution-waves.md` | Features grouped into ordered implementation waves | Optional |

## Completion Criteria
Your work is done when:
- Features are created in the database via `create_features` tool
- `validate_feature_dag()` passes with no errors
- `specification.md` provides full project context
- Every feature has `features/<name>/spec.md` with enough detail for autonomous implementation
- Every feature has `features/<name>/acceptance-criteria.md` with 3+ testable criteria

## Guidelines
- The spec must be self-contained: an agent with no prior context should be able to implement any feature from specification.md + the feature spec alone
- Acceptance criteria must be verifiable — prefer automated tests over subjective assessment
- Keep the DAG as shallow as possible to maximize parallel execution
- Foundation features (project setup, shared models, core utilities) should be at the DAG root
- Over-specify rather than under-specify — ambiguity leads to rework during implementation

{{PLUGIN_SUPPLEMENT}}
