---
description: "Orchestrate the Sustain phase — set up monitoring, alerting, operational runbooks, and ongoing maintenance practices."
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
---

# /sustain Command — Greenfield Archetype

Execute the Sustain phase of the RAPIDS workflow for a greenfield project. This is the ongoing operational phase that ensures the deployed system remains healthy and maintainable.

## What This Command Does

1. **Verify Phase**: Confirm the project is in the Sustain phase and that Deploy exit criteria are met.
2. **Load Context**: Read architecture, deployment configuration, and project code to understand the operational surface.
3. **Launch Monitor Agent**: Spawn the `monitor` agent with full project context.
4. **Execute Sustain Setup**:
   - Configure structured application logging
   - Set up health check and metrics endpoints
   - Define alerting rules and notification channels
   - Establish performance baselines
   - Create operational runbooks for common scenarios
   - Document maintenance procedures and schedules
   - Set up dependency update tracking
5. **Validate Setup**: Verify health endpoints respond, logging is functional, and runbooks are complete.
6. **Report Status**: Display operational readiness summary.

## Usage

```
/sustain                      # Run the full sustain setup
/sustain --monitoring         # Set up monitoring and alerting only
/sustain --runbooks           # Generate operational runbooks only
/sustain --status             # Show sustain phase status
/sustain --health-check       # Run health checks against the deployed system
```

## Interaction Model

The sustain phase is collaborative:
- The agent proposes monitoring and alerting configurations for user review
- Alert thresholds are presented with rationale and can be adjusted
- Runbooks are generated from the architecture and presented for review
- Maintenance schedules are proposed based on the technology stack

## Ongoing Operations

The Sustain phase has no exit criteria — it is an ongoing practice. The `/sustain` command can be re-run to:
- Update runbooks after feature additions
- Adjust alerting thresholds based on operational experience
- Add new monitoring for newly discovered failure modes
- Review and update maintenance schedules

## Artifacts Produced

`.rapids/sustain/`:
- `monitoring-config.md` — Monitoring and metrics configuration
- `alerting-rules.md` — Alert definitions and thresholds
- `performance-baseline.md` — Expected performance characteristics
- `maintenance-schedule.md` — Ongoing maintenance procedures and timing

`.rapids/sustain/runbooks/`:
- `incident-response.md` — Incident detection, triage, and resolution
- `troubleshooting.md` — Common issue diagnosis and fixes
- `scaling.md` — Manual and automated scaling procedures
- `backup-recovery.md` — Backup verification and disaster recovery
- `deployment-verification.md` — Post-deployment health check procedures
