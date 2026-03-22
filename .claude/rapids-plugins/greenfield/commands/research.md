---
description: "Orchestrate the Research phase — explore the problem domain, survey technologies, and gather requirements for a greenfield project."
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

# /research Command — Greenfield Archetype

Execute the Research phase of the RAPIDS workflow for a greenfield project.

## What This Command Does

1. **Verify Phase**: Confirm the project is in the Research phase (or transition to it if the user requests).
2. **Load Workflow**: Load the research workflow from `workflows/research-workflow.md` for guided execution.
3. **Launch Researcher Agent**: Spawn the `researcher` agent with the research workflow context.
4. **Execute Sections**: Walk through each workflow section in order:
   - Problem Statement definition
   - Technology Landscape survey
   - Constraints & Requirements gathering
   - Domain Context building
   - Stakeholder identification
5. **Validate Artifacts**: After the agent completes, verify that all required artifacts exist in `.rapids/research/`.
6. **Report Status**: Display a summary of what was produced and whether exit criteria are met.

## Usage

```
/research                    # Run the full research workflow
/research --section problem  # Run only the Problem Statement section
/research --status           # Show research phase status and artifact checklist
```

## Interaction Model

The research phase is interactive. The researcher agent will:
- Ask the user clarifying questions about the project vision and requirements
- Present technology options for the user to review and provide preferences
- Confirm the problem statement before moving to subsequent sections
- Summarize findings at the end of each section

## Artifacts Produced

All artifacts are written to `.rapids/research/`:
- `problem-statement.md`
- `technology-landscape.md`
- `constraints.md`
- `requirements.md`
- `domain-glossary.md`
- `domain-model.md`
- `stakeholders.md`
- `success-metrics.md`
