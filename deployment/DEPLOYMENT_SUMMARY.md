# RAPIDS Kubernetes Deployment - Summary

## What Was Created

This deployment configuration provides production-ready Kubernetes manifests for RAPIDS Meta-Orchestrator.

### Directory Structure

```
deployment/
├── README.md                          # Comprehensive deployment guide
├── QUICK_START.md                     # 5-minute quick start
├── DEPLOYMENT_SUMMARY.md              # This file
├── helm/
│   └── rapids-orchestrator/           # Helm chart
│       ├── Chart.yaml                 # Chart metadata
│       ├── values.yaml                # Default configuration
│       ├── values-production.yaml     # Production overrides
│       ├── .helmignore                # Helm ignore patterns
│       └── templates/                 # Kubernetes manifests
│           ├── _helpers.tpl           # Template helpers
│           ├── NOTES.txt              # Post-install instructions
│           ├── configmap.yaml         # Configuration data
│           ├── secret.yaml            # Sensitive data
│           ├── deployment-backend.yaml     # Backend deployment
│           ├── deployment-frontend.yaml    # Frontend deployment
│           ├── statefulset-postgresql.yaml # Database StatefulSet
│           ├── service-backend.yaml        # Backend service
│           ├── service-frontend.yaml       # Frontend service
│           ├── service-postgresql.yaml     # Database services
│           ├── ingress.yaml                # Ingress controller config
│           ├── hpa-backend.yaml            # Backend auto-scaling
│           ├── hpa-frontend.yaml           # Frontend auto-scaling
│           ├── pvc.yaml                    # Persistent storage claims
│           ├── job-migrations.yaml         # Database migration job
│           ├── serviceaccount.yaml         # RBAC service account
│           ├── networkpolicy.yaml          # Network security policies
│           └── servicemonitor.yaml         # Prometheus monitoring
├── scripts/
│   ├── install.sh                     # Interactive installation
│   ├── upgrade.sh                     # Upgrade helper
│   └── uninstall.sh                   # Cleanup helper
└── examples/
    ├── github-actions-ci.yaml         # GitHub Actions pipeline
    ├── gitlab-ci.yaml                 # GitLab CI/CD pipeline
    └── prometheus-alerts.yaml         # Alerting rules
```

## Key Features

### 1. Production-Ready Configuration

- **Multi-replica deployments**: Backend (2-20 replicas), Frontend (2-10 replicas)
- **Horizontal Pod Autoscaling**: Automatic scaling based on CPU/memory
- **Resource limits**: Proper CPU and memory constraints
- **Health checks**: Liveness and readiness probes
- **Security**: Non-root containers, network policies, RBAC

### 2. High Availability

- **Pod anti-affinity**: Distributes replicas across nodes
- **Persistent storage**: Data survives pod restarts
- **StatefulSet for PostgreSQL**: Stable network identity
- **Graceful shutdowns**: Proper termination handling

### 3. Observability

- **Prometheus metrics**: Backend and database metrics exposed
- **ServiceMonitor**: Auto-discovery by Prometheus Operator
- **Alerting rules**: Pre-configured alerts for common issues
- **Logging**: Structured logs from all components

### 4. Automated Operations

- **Database migrations**: Run automatically before deployment
- **Helm hooks**: Pre-install and pre-upgrade tasks
- **CI/CD examples**: GitHub Actions and GitLab CI
- **Helper scripts**: Install, upgrade, and uninstall automation

### 5. Network Security

- **Network Policies**: Restricts pod-to-pod communication
- **Ingress with TLS**: HTTPS enforcement
- **cert-manager integration**: Automatic SSL certificate management
- **WebSocket support**: Properly configured for real-time updates

## Components Deployed

### Backend (FastAPI)

- **Image**: rapids-orchestrator/backend:0.1.0
- **Port**: 9403
- **Replicas**: 2-10 (auto-scaled)
- **Resources**: 500m-2 CPU, 1-4Gi memory
- **Volumes**: workspace (20Gi), logs (10Gi), plugins (read-only)

### Frontend (Vue 3 + Nginx)

- **Image**: rapids-orchestrator/frontend:0.1.0
- **Port**: 8080
- **Replicas**: 2-6 (auto-scaled)
- **Resources**: 100m-500m CPU, 128Mi-512Mi memory

### PostgreSQL 16

- **Image**: postgres:16-alpine
- **Port**: 5432
- **Type**: StatefulSet (single instance)
- **Resources**: 500m-2 CPU, 2-8Gi memory
- **Storage**: 50-200Gi persistent volume
- **Metrics**: postgres-exporter sidecar

### Supporting Components

- **ConfigMap**: Non-sensitive configuration
- **Secret**: API keys, JWT secret, database password
- **Ingress**: Routes traffic to frontend/backend
- **NetworkPolicy**: Pod communication rules
- **ServiceAccount**: RBAC permissions

## Configuration Options

### Environment Variables (ConfigMap)

- `LOG_LEVEL`: Logging verbosity (info, debug, warning, error)
- `ENVIRONMENT`: Deployment environment (development, production)
- `JWT_ALGORITHM`: JWT signing algorithm (HS256)
- `ACCESS_TOKEN_EXPIRE_MINUTES`: Token expiration (60)

### Secrets (Kubernetes Secret)

- `ANTHROPIC_API_KEY`: Claude API key **(required)**
- `JWT_SECRET_KEY`: JWT signing secret **(required)**
- `POSTGRES_PASSWORD`: Database password **(required)**
- `DATABASE_URL`: Full database connection string (auto-generated)

### Resource Limits

#### Development/Staging (default)
- Backend: 500m CPU, 1Gi memory
- Frontend: 100m CPU, 128Mi memory
- PostgreSQL: 500m CPU, 2Gi memory

#### Production (values-production.yaml)
- Backend: 1-4 CPU, 2-8Gi memory
- Frontend: 200m-1 CPU, 256Mi-1Gi memory
- PostgreSQL: 2-4 CPU, 8-16Gi memory

### Auto-Scaling Triggers

- **Backend**: 70% CPU or 80% memory
- **Frontend**: 80% CPU
- Scale up: Fast (30s stabilization)
- Scale down: Slow (300s stabilization)

## Deployment Modes

### 1. Quick Start (Development)

```bash
cd deployment/scripts
./install.sh
```

Uses default values, suitable for testing and development.

### 2. Production Deployment

```bash
helm install rapids-orchestrator ./deployment/helm/rapids-orchestrator \
  --namespace rapids \
  --values values-production.yaml \
  --set backend.secretEnv.ANTHROPIC_API_KEY=$API_KEY \
  --wait
```

Uses production configuration with proper resource limits and HA.

### 3. CI/CD Integration

Use provided examples:
- **GitHub Actions**: `.github/workflows/deploy.yaml`
- **GitLab CI**: `.gitlab-ci.yml`

Both examples include:
- Build and push Docker images
- Deploy to Kubernetes
- Run smoke tests
- Environment management

## Monitoring and Alerts

### Metrics Exposed

**Backend (`/metrics`)**:
- `http_requests_total`: Total HTTP requests
- `http_request_duration_seconds`: Request latency
- `agent_operations_total`: Agent operations
- `active_agents_gauge`: Active agents count
- `websocket_connections_gauge`: WebSocket connections

**PostgreSQL (port 9187)**:
- Standard PostgreSQL metrics via postgres-exporter
- Connection pool metrics
- Query performance metrics

### Pre-configured Alerts

- Backend/Frontend/Database availability
- High error rate (>5%)
- Slow responses (p95 >2s)
- High resource usage (>90%)
- Database connection pool saturation
- Disk space low (<15%)
- Frequent pod restarts
- HPA at max replicas

## Security Considerations

### Container Security

- ✅ Non-root user (UID 1000)
- ✅ Read-only root filesystem (where possible)
- ✅ Drop all capabilities
- ✅ No privilege escalation
- ✅ Minimal base images (alpine)

### Network Security

- ✅ Network policies restrict pod-to-pod traffic
- ✅ Ingress-only external access
- ✅ TLS/HTTPS enforcement
- ✅ Backend only accessible via ingress
- ✅ Database only accessible from backend

### Secrets Management

- ✅ Kubernetes Secrets for sensitive data
- ✅ Not stored in values.yaml
- ✅ Can integrate with External Secrets Operator
- ✅ Support for AWS Secrets Manager, GCP Secret Manager, etc.

### RBAC

- ✅ Dedicated ServiceAccount
- ✅ Minimal permissions
- ✅ No cluster-wide access

## Storage Architecture

### Workspace PVC (20-100Gi)

- **Purpose**: Multi-project workspace data
- **Access**: ReadWriteMany (shared across backend pods)
- **Lifecycle**: Persistent across deployments
- **Backup**: Recommended daily

### Logs PVC (10-50Gi)

- **Purpose**: Application logs
- **Access**: ReadWriteMany (shared across backend pods)
- **Lifecycle**: Persistent, can be rotated
- **Backup**: Optional

### PostgreSQL PVC (50-200Gi)

- **Purpose**: Database storage
- **Access**: ReadWriteOnce (StatefulSet)
- **Lifecycle**: Persistent, managed by StatefulSet
- **Backup**: **Critical** - daily backups required

## Upgrade Process

### Standard Upgrade

```bash
cd deployment/scripts
./upgrade.sh
```

Or manually:

```bash
helm upgrade rapids-orchestrator ./deployment/helm/rapids-orchestrator \
  --namespace rapids \
  --set backend.image.tag=0.2.0 \
  --wait
```

### What Happens During Upgrade

1. **Pre-upgrade hook**: Database migration job runs
2. **Rolling update**: Pods updated one by one (zero downtime)
3. **Health checks**: New pods must pass health checks
4. **Old pods terminate**: After new pods are ready

### Rollback

```bash
helm rollback rapids-orchestrator -n rapids
```

## Cost Optimization

### For Small Workloads

```yaml
backend:
  replicaCount: 1
  autoscaling:
    enabled: false
  resources:
    requests:
      cpu: 250m
      memory: 512Mi

postgresql:
  enabled: false  # Use external managed database
```

### For Large Scale

```yaml
backend:
  autoscaling:
    minReplicas: 5
    maxReplicas: 50
  resources:
    limits:
      cpu: 4000m
      memory: 8Gi

# Use external managed PostgreSQL (Cloud SQL, RDS)
postgresql:
  enabled: false
```

## Next Steps

1. **Review** [QUICK_START.md](QUICK_START.md) for rapid deployment
2. **Read** [README.md](README.md) for comprehensive documentation
3. **Customize** values.yaml for your environment
4. **Deploy** using install.sh script
5. **Monitor** with Prometheus and Grafana
6. **Secure** with proper secrets management
7. **Scale** based on your workload

## Support and Troubleshooting

Common issues and solutions are documented in [README.md#troubleshooting](README.md#troubleshooting).

For additional help:
- Check pod logs: `kubectl logs -n rapids <pod-name>`
- Describe resources: `kubectl describe <resource> -n rapids`
- Review events: `kubectl get events -n rapids --sort-by='.lastTimestamp'`

## License

Private - All rights reserved
