# Plan Workflow — Greenfield Archetype

Guided workflow for the Plan phase of a greenfield project. The goal is to decompose the project into implementable features, map their dependencies into a DAG, and produce specifications detailed enough for autonomous agent execution.

---

## 1. Feature Identification

Break the project down into discrete, independently implementable features.

**Activities:**
- Review the architecture and identify natural feature boundaries along component lines
- Define each feature as a unit of work that produces a testable, observable increment
- Ensure features are small enough for a single agent session (target: 200-500 lines of code change)
- Name features with clear, descriptive kebab-case identifiers (e.g., `user-auth-api`, `database-schema-setup`)
- Categorize features: infrastructure, core-logic, api-layer, ui-component, integration, testing
- Identify foundational features that must exist before others can begin (e.g., project scaffolding, database setup)

**Artifacts:**
- `.rapids/plan/feature-list.md` — Complete list of features with names, categories, and brief descriptions

**Exit check:** Every piece of functionality in the architecture maps to at least one feature.

---

## 2. Dependency Mapping

Build the feature dependency DAG that determines execution order.

**Activities:**
- For each feature, identify which other features must be completed first (hard dependencies)
- Identify shared interfaces: if Feature A defines an interface that Feature B implements, A depends on B's contract
- Minimize dependencies to maximize parallelism; prefer interface contracts over implementation dependencies
- Identify features with zero dependencies (DAG leaves) that can be built first
- Verify the DAG is acyclic; resolve any circular dependencies by extracting shared contracts into separate features
- Identify the critical path through the DAG

**Artifacts:**
- `.rapids/plan/feature-dag.json` — Machine-readable DAG with nodes and edges
- `.rapids/plan/feature-dag.md` — Human-readable dependency visualization

**Exit check:** DAG is valid (acyclic), all features are reachable, leaf nodes are identified.

---

## 3. Acceptance Criteria

Define precise, testable acceptance criteria for every feature.

**Activities:**
- Write 3-7 acceptance criteria per feature using Given/When/Then format where applicable
- Include both happy-path and error-handling criteria
- Define the expected test types per feature (unit, integration, e2e)
- Specify any performance criteria (response time, resource limits)
- Ensure acceptance criteria reference the interface contracts from the architecture
- Mark any criteria that require external system availability for testing

**Artifacts:**
- `.rapids/plan/features/<feature-name>/acceptance-criteria.md` — Per-feature acceptance criteria

**Exit check:** Every feature has at least 3 testable acceptance criteria.

---

## 4. Priority & Sizing

Assign implementation priority and effort estimates to guide execution order.

**Activities:**
- Assign each feature a priority: P0 (critical path), P1 (important), P2 (nice to have)
- Estimate relative effort using t-shirt sizing (S/M/L/XL)
- Identify features that can be parallelized (no mutual dependencies)
- Group features into implementation waves based on DAG layers and priority
- Estimate total implementation time and identify potential bottlenecks
- Flag any features that may require specialized knowledge or spike work

**Artifacts:**
- `.rapids/plan/execution-waves.md` — Features grouped into ordered implementation waves

**Exit check:** All P0 features are in the first two waves; no wave has unresolved dependencies.

---

## 5. Specification Compilation

Produce the final feature specifications that agents will consume during implementation.

**Activities:**
- For each feature, compile a self-contained spec that includes:
  - Feature name and description
  - Dependencies (which features must be complete, and what interfaces they expose)
  - File paths and module locations where code should be written
  - Interface contracts (function signatures, API endpoints, data schemas)
  - Acceptance criteria
  - Implementation guidance and hints from the architecture
  - Test requirements
- Ensure each spec contains enough context for an agent with no prior project knowledge
- Validate specs against the architecture document for consistency
- Write the master project specification that ties all features together

**Artifacts:**
- `.rapids/plan/features/<feature-name>/spec.md` — Self-contained feature specification per feature
- `.rapids/plan/specification.md` — Master project specification summarizing scope, architecture, and feature overview

**Exit check:** Every feature has a complete spec.md; master specification is written.

---

## Phase Completion

The Plan phase is complete when:
1. All features are identified and named
2. Feature DAG is valid with no cycles and all dependencies mapped
3. Every feature has testable acceptance criteria
4. Features are prioritized and grouped into execution waves
5. Every feature has a self-contained spec.md sufficient for autonomous implementation

All artifacts should be written to `.rapids/plan/` and committed to version control. The feature DAG JSON must be parseable by the orchestrator's feature_dag module.
