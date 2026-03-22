---
description: "Orchestrate the Analysis phase — design architecture, select technologies, assess risks, and document decisions for a greenfield project."
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - WebSearch
  - WebFetch
---

# /analyze Command — Greenfield Archetype

Execute the Analysis phase of the RAPIDS workflow for a greenfield project.

## What This Command Does

1. **Verify Phase**: Confirm the project is in the Analysis phase and that Research exit criteria are met.
2. **Load Context**: Read all research artifacts from `.rapids/research/` to provide full context to the architect.
3. **Load Workflow**: Load the analysis workflow from `workflows/analysis-workflow.md`.
4. **Launch Architect Agent**: Spawn the `architect` agent with research context and analysis workflow.
5. **Execute Sections**: Walk through each workflow section:
   - Solution Options evaluation
   - Architecture Design
   - Technology Selection
   - Risk Assessment
   - Decision Records (ADRs)
6. **Validate Artifacts**: Verify all required analysis artifacts exist in `.rapids/analysis/`.
7. **Report Status**: Display summary of architecture decisions and whether exit criteria are met.

## Usage

```
/analyze                      # Run the full analysis workflow
/analyze --section arch       # Run only the Architecture Design section
/analyze --status             # Show analysis phase status and artifact checklist
```

## Interaction Model

The analysis phase presents decisions for user review:
- Solution options are presented with comparative analysis for user input
- Architecture diagrams are described and confirmed before proceeding
- Technology selections are summarized for approval
- ADRs are written and can be reviewed before the phase completes

## Artifacts Produced

All artifacts are written to `.rapids/analysis/`:
- `solution-options.md`
- `solution-decision.md`
- `architecture.md`
- `data-model.md`
- `api-contracts.md`
- `tech-stack.md`
- `dev-environment.md`
- `risk-register.md`
- `decisions/001-*.md`, `decisions/002-*.md`, ...
