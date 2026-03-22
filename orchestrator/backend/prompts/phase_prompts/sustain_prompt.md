# Sustain Phase Prompt

You are executing the **Sustain** phase of the RAPIDS workflow for project: {{PROJECT_NAME}}.

## Objective
Establish the operational foundation for long-term reliability: monitoring, alerting, incident response, performance optimization, and continuous improvement processes.

## Inputs
Review the deployment and architecture artifacts:
- `.rapids/analysis/architecture.md` — Non-functional requirements, performance targets
- `.rapids/deploy/deployment.md` — Deployment topology, environment details
- `.rapids/deploy/pipeline.md` — CI/CD pipeline configuration

## Activities

### 1. Monitoring Setup
- Configure application-level monitoring:
  - Request latency (p50, p95, p99) per endpoint
  - Error rates and error classification
  - Throughput and saturation metrics
  - Business-specific metrics (signups, transactions, etc.)
- Configure infrastructure monitoring:
  - CPU, memory, disk, and network utilization
  - Container health and restart counts
  - Database connection pool usage, query latency, replication lag
  - Queue depth and consumer lag
- Set up structured logging with correlation IDs for request tracing
- Configure distributed tracing if the architecture spans multiple services

### 2. Alerting Configuration
- Define alert rules based on SLOs (Service Level Objectives):
  - **Critical**: Service down, data loss risk, security breach indicators
  - **Warning**: Degraded performance, elevated error rates, resource approaching limits
  - **Info**: Deployment events, scaling events, configuration changes
- Configure notification channels (PagerDuty, Slack, email) with appropriate escalation paths
- Set up alert deduplication and grouping to prevent alert fatigue
- Define on-call rotation expectations (if applicable)

### 3. Runbook Creation
- Write operational runbooks for common scenarios:
  - `runbooks/incident-response.md` — General incident triage and escalation process
  - `runbooks/service-restart.md` — Safe restart procedures for each service
  - `runbooks/database-recovery.md` — Backup verification, point-in-time recovery steps
  - `runbooks/scaling.md` — Horizontal and vertical scaling procedures and limits
  - `runbooks/rollback.md` — Step-by-step rollback for deployment failures
- Each runbook should include: symptoms, diagnosis steps, resolution steps, verification, and escalation criteria

### 4. Performance Optimization
- Establish performance baselines from initial deployment metrics
- Identify optimization opportunities:
  - Query optimization (slow queries, missing indexes, N+1 patterns)
  - Caching strategy (what to cache, TTL policies, invalidation)
  - Connection pooling and resource reuse
  - Payload optimization (compression, pagination, field selection)
- Document performance budget: acceptable latency and resource consumption per operation
- Set up automated performance regression detection in CI/CD

### 5. Continuous Improvement
- Define the process for handling technical debt:
  - Maintain a tech-debt register with severity and estimated effort
  - Allocate recurring time for debt reduction
- Set up automated dependency updates (Dependabot, Renovate)
- Configure security vulnerability scanning on a regular schedule
- Establish review cadence for monitoring dashboards and alert thresholds
- Plan capacity reviews based on growth projections

### 6. Documentation and Knowledge Transfer
- Create an operations guide covering:
  - System overview and component interactions
  - Common operational tasks and their procedures
  - Troubleshooting decision trees
  - Contact information for external dependencies
- Ensure all monitoring dashboards are documented and accessible to the team

## Artifacts to Produce
Save all outputs to the project's `.rapids/sustain/` directory:
- `monitoring.md` — Monitoring architecture, dashboard descriptions, metric definitions, SLOs
- `alerting.md` — Alert rules, thresholds, notification channels, escalation policies
- `runbooks/` directory — Operational runbooks for common scenarios
- `optimization.md` — Performance baselines, optimization backlog, performance budgets
- `operations-guide.md` — Comprehensive operations reference document

## Guidelines
- Monitoring should answer "is the system healthy?" within 30 seconds of looking at a dashboard
- Alerts should be actionable — every alert should map to a runbook entry
- Prefer percentile-based metrics (p95, p99) over averages for latency monitoring
- Design runbooks for someone unfamiliar with the system to follow under pressure
- Automate everything that can be automated; document everything that cannot
- Review and update all sustain artifacts after each significant system change
- Start with simple monitoring and iterate — comprehensive observability is built over time

{{PLUGIN_SUPPLEMENT}}
