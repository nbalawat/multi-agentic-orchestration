---
description: "Orchestrate the Deploy phase — configure CI/CD, containerize the application, set up infrastructure, and automate deployment."
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
---

# /deploy Command — Greenfield Archetype

Execute the Deploy phase of the RAPIDS workflow for a greenfield project.

## What This Command Does

1. **Verify Phase**: Confirm the project is in the Deploy phase and that Implementation exit criteria are met (all features complete, tests passing).
2. **Load Context**: Read the architecture, tech stack, and project structure to understand deployment requirements.
3. **Launch Deployer Agent**: Spawn the `deployer` agent with project context.
4. **Execute Deployment Setup**:
   - Configure CI/CD pipeline (GitHub Actions, GitLab CI, or platform-appropriate)
   - Write Dockerfiles and docker-compose configuration
   - Set up infrastructure-as-code definitions
   - Configure environment management and secrets handling
   - Define deployment stages (dev, staging, production)
   - Write deployment and rollback scripts
   - Set up database migration automation
5. **Validate Configuration**: Verify Dockerfiles build, CI config is syntactically valid, and scripts run without errors.
6. **Document Procedures**: Write deployment runbook to `.rapids/deploy/`.
7. **Report Status**: Display deployment readiness and any manual steps required.

## Usage

```
/deploy                       # Run the full deployment setup
/deploy --ci-only             # Configure CI/CD pipeline only
/deploy --docker-only         # Set up containerization only
/deploy --status              # Show deployment phase status
/deploy --validate            # Validate existing deployment configuration
```

## Interaction Model

The deploy phase requires user input for:
- Target platform selection (cloud provider, hosting service)
- Secrets and credentials (the agent will prompt but never store secrets in code)
- Domain and networking configuration
- Cost and scaling preferences

## Artifacts Produced

Project root:
- `Dockerfile` (and variants if multi-service)
- `docker-compose.yml`
- `.github/workflows/` or equivalent CI config

`.rapids/deploy/`:
- `deployment-guide.md` — Step-by-step deployment procedures
- `rollback-guide.md` — Rollback procedures
- `environment-config.md` — Environment variable documentation
- `infrastructure.md` — Infrastructure setup documentation
