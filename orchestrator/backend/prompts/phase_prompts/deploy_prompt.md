# Deploy Phase Prompt

You are executing the **Deploy** phase of the RAPIDS workflow for project: {{PROJECT_NAME}}.

## Objective
Package, configure, and deploy the implemented project to the target environment(s). Establish CI/CD pipelines, containerize services, provision infrastructure, and verify the deployment is healthy.

## Inputs
Review the implementation artifacts and architecture before proceeding:
- `.rapids/analysis/architecture.md` — Deployment topology, infrastructure requirements
- `.rapids/plan/spec.md` — Environment setup, configuration requirements
- `.rapids/implement/progress.json` — Confirm all features are complete
- Source code and tests in the project's source directories

## Activities

### 1. Containerization
- Create Dockerfiles for each deployable service following best practices:
  - Multi-stage builds to minimize image size
  - Non-root user execution
  - Health check endpoints
  - Proper signal handling for graceful shutdown
- Create `docker-compose.yml` for local development and testing
- Document build arguments and environment variables

### 2. CI/CD Pipeline
- Configure the CI/CD pipeline (GitHub Actions, GitLab CI, or as specified in architecture):
  - **Build stage**: Compile, lint, type-check
  - **Test stage**: Unit tests, integration tests, coverage thresholds
  - **Security stage**: Dependency scanning, SAST, secret detection
  - **Package stage**: Build container images, tag with commit SHA and version
  - **Deploy stage**: Deploy to target environment with rollback capability
- Define environment-specific configurations (dev, staging, production)
- Set up branch protection rules and deployment gates

### 3. Infrastructure Setup
- Provision infrastructure as code (Terraform, CloudFormation, Pulumi, or as specified):
  - Compute resources (containers, serverless, VMs)
  - Networking (VPC, load balancers, DNS, TLS certificates)
  - Data stores (databases, caches, object storage)
  - Message queues and event buses (if applicable)
- Configure secrets management (environment variables, vault, parameter store)
- Set up database migrations and seed data

### 4. Deployment Verification
- Run smoke tests against the deployed environment
- Verify all service health check endpoints respond correctly
- Confirm database connectivity and migration status
- Validate external integration points (APIs, webhooks, third-party services)
- Test authentication and authorization flows end-to-end
- Verify logging and metrics are flowing to observability stack

### 5. Deployment Documentation
- Document the deployment process for manual and automated runs
- Record environment URLs, access credentials locations, and configuration
- Create rollback procedures for each component

## Artifacts to Produce
Save all outputs to the project's `.rapids/deploy/` directory:
- `deployment.md` — Deployment architecture, environment configurations, access details, rollback procedures
- `pipeline.md` — CI/CD pipeline documentation, stage descriptions, required secrets
- Infrastructure-as-code files in the project's `infrastructure/` or `deploy/` directory
- Dockerfiles and compose configurations in the project root or service directories

## Guidelines
- Never hard-code secrets, credentials, or environment-specific values in source code or configuration files
- All infrastructure should be reproducible from code — no manual console changes
- Deployments must be idempotent: running the deploy twice produces the same result
- Include rollback capability for every deployment step
- Test the deployment pipeline end-to-end in a non-production environment before targeting production
- Tag all infrastructure resources with project name, environment, and owner for cost tracking

{{PLUGIN_SUPPLEMENT}}
