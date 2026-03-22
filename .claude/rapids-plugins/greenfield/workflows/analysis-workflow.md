# Analysis Workflow — Greenfield Archetype

Guided workflow for the Analysis phase of a greenfield project. The goal is to translate research findings into concrete architectural decisions, technology selections, and a documented rationale for every major choice.

---

## 1. Solution Options

Generate and evaluate candidate solution approaches.

**Activities:**
- Propose 2-3 high-level solution approaches based on research findings
- For each approach, describe the architecture pattern (monolith, microservices, serverless, etc.)
- Evaluate each approach against the documented constraints and requirements
- Conduct a comparative analysis using a decision matrix weighted by project priorities
- Select the recommended approach with documented justification

**Artifacts:**
- `.rapids/analysis/solution-options.md` — Candidate approaches with comparative evaluation
- `.rapids/analysis/solution-decision.md` — Selected approach with rationale

**Exit check:** At least two options evaluated; one selected with clear justification.

---

## 2. Architecture Design

Design the system architecture for the selected solution approach.

**Activities:**
- Define the high-level system components and their responsibilities
- Map data flow between components (inputs, outputs, transformations)
- Design the API surface and interface contracts between components
- Specify data storage strategy (schema approach, data models, storage engines)
- Define the integration architecture for external systems
- Document cross-cutting concerns (logging, error handling, configuration management)

**Artifacts:**
- `.rapids/analysis/architecture.md` — System architecture with component descriptions
- `.rapids/analysis/data-model.md` — Data storage design and schema strategy
- `.rapids/analysis/api-contracts.md` — Interface definitions between components

**Exit check:** All components identified; data flow is end-to-end traceable.

---

## 3. Technology Selection

Make final technology choices for each component of the architecture.

**Activities:**
- For each architectural component, select specific technologies from the research landscape
- Validate that selected technologies are compatible with each other
- Define version constraints and dependency management strategy
- Evaluate the build toolchain (package manager, bundler, test runner, linter)
- Document the development environment setup requirements
- Identify any proof-of-concept or spike work needed to de-risk selections

**Artifacts:**
- `.rapids/analysis/tech-stack.md` — Final technology selections per component with versions
- `.rapids/analysis/dev-environment.md` — Development environment setup specification

**Exit check:** Every architectural component has a concrete technology selection.

---

## 4. Risk Assessment

Identify and plan mitigations for technical and project risks.

**Activities:**
- Identify technical risks (scalability limits, integration complexity, skill gaps)
- Identify project risks (timeline pressure, dependency on external teams, scope creep)
- Rate each risk by probability and impact (High/Medium/Low)
- Define mitigation strategies for all High and Medium risks
- Identify any risks that require immediate spike work or prototyping
- Document assumptions that, if invalidated, would require revisiting decisions

**Artifacts:**
- `.rapids/analysis/risk-register.md` — Categorized risks with probability, impact, and mitigations

**Exit check:** All High risks have defined mitigation strategies.

---

## 5. Decision Records

Create Architecture Decision Records (ADRs) for every major choice.

**Activities:**
- Write an ADR for each major decision made during analysis
- Each ADR should include: context, decision, consequences, and alternatives considered
- Link ADRs to the relevant research artifacts that informed the decision
- Assign ADR numbers for future reference and traceability
- Review ADRs for completeness and consistency

**Artifacts:**
- `.rapids/analysis/decisions/` — Directory of numbered ADR files (e.g., `001-architecture-pattern.md`, `002-database-selection.md`)

**Exit check:** ADRs exist for architecture pattern, technology stack, data storage, and API design decisions at minimum.

---

## Phase Completion

The Analysis phase is complete when:
1. Solution approach is selected with documented alternatives and rationale
2. Architecture is designed with component responsibilities and data flow
3. Technology stack is fully specified with versions
4. Risk register is populated with mitigations for all High/Medium risks
5. ADRs are written for all major decisions

All artifacts should be written to `.rapids/analysis/` and committed to version control.
