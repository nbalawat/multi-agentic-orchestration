# RAPIDS Meta-Orchestrator - Kubernetes Deployment

This directory contains production-ready Kubernetes manifests and Helm charts for deploying the RAPIDS Meta-Orchestrator to Kubernetes.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start with Helm](#quick-start-with-helm)
- [Configuration](#configuration)
- [Production Deployment](#production-deployment)
- [Monitoring](#monitoring)
- [Backup and Restore](#backup-and-restore)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### Required

- Kubernetes 1.24+ cluster
- Helm 3.12+
- kubectl configured to access your cluster
- Container registry access (Docker Hub, GCR, ECR, etc.)
- SSL certificate for HTTPS (or cert-manager installed)

### Recommended

- Nginx Ingress Controller installed
- cert-manager for automatic SSL certificate management
- Prometheus Operator for monitoring (optional)
- Persistent volume provisioner (for production)

## Quick Start with Helm

### 1. Build and Push Docker Images

```bash
# Build backend image
docker build -f Dockerfile.backend -t your-registry.com/rapids-orchestrator/backend:0.1.0 .
docker push your-registry.com/rapids-orchestrator/backend:0.1.0

# Build frontend image
docker build -f Dockerfile.frontend -t your-registry.com/rapids-orchestrator/frontend:0.1.0 .
docker push your-registry.com/rapids-orchestrator/frontend:0.1.0
```

### 2. Create Namespace

```bash
kubectl create namespace rapids
```

### 3. Create Secrets

```bash
# Generate JWT secret
JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

# Create Kubernetes secret
kubectl create secret generic rapids-secrets \
  --namespace rapids \
  --from-literal=ANTHROPIC_API_KEY='your-anthropic-api-key' \
  --from-literal=JWT_SECRET_KEY="$JWT_SECRET" \
  --from-literal=POSTGRES_PASSWORD='your-strong-database-password'
```

### 4. Install with Helm

```bash
# Add your custom values
cd deployment/helm/rapids-orchestrator

# Install the chart
helm install rapids-orchestrator . \
  --namespace rapids \
  --create-namespace \
  --set backend.image.repository=your-registry.com/rapids-orchestrator/backend \
  --set backend.image.tag=0.1.0 \
  --set frontend.image.repository=your-registry.com/rapids-orchestrator/frontend \
  --set frontend.image.tag=0.1.0 \
  --set backend.secretEnv.ANTHROPIC_API_KEY='your-api-key' \
  --set backend.secretEnv.JWT_SECRET_KEY='your-jwt-secret' \
  --set postgresql.auth.password='your-db-password' \
  --set ingress.hosts[0].host=rapids.yourcompany.com
```

### 5. Verify Deployment

```bash
# Watch pods starting
kubectl get pods -n rapids -w

# Check migration job
kubectl logs -n rapids -l app.kubernetes.io/component=migrations -f

# Get ingress URL
kubectl get ingress -n rapids
```

## Configuration

### values.yaml Structure

The default `values.yaml` contains sensible defaults for development/staging. For production, use `values-production.yaml` or override specific values.

#### Key Configuration Sections

1. **Backend Configuration**
   ```yaml
   backend:
     replicaCount: 2  # Number of backend pods
     resources:
       limits:
         cpu: 2000m
         memory: 4Gi
     autoscaling:
       enabled: true
       minReplicas: 2
       maxReplicas: 10
   ```

2. **Frontend Configuration**
   ```yaml
   frontend:
     replicaCount: 2  # Number of frontend pods
     resources:
       limits:
         cpu: 500m
         memory: 512Mi
   ```

3. **Database Configuration**
   ```yaml
   postgresql:
     enabled: true
     primary:
       persistence:
         enabled: true
         size: 50Gi
         storageClass: "fast-ssd"
   ```

4. **Ingress Configuration**
   ```yaml
   ingress:
     enabled: true
     className: "nginx"
     hosts:
       - host: rapids.example.com
     tls:
       - secretName: rapids-tls
         hosts:
           - rapids.example.com
   ```

### Environment Variables

Key environment variables are configured through ConfigMap and Secrets:

- `ANTHROPIC_API_KEY` (Secret) - Claude API key
- `JWT_SECRET_KEY` (Secret) - JWT signing secret
- `POSTGRES_PASSWORD` (Secret) - Database password
- `LOG_LEVEL` (ConfigMap) - Logging level (info, debug, warning, error)
- `ENVIRONMENT` (ConfigMap) - Environment name (development, production)

## Production Deployment

### 1. Prepare Production Values

Create a `values-production.yaml` file or use the provided template:

```bash
cp deployment/helm/rapids-orchestrator/values-production.yaml values-custom.yaml
```

Edit `values-custom.yaml` and set:
- Image repositories (your private registry)
- Resource limits based on your workload
- Ingress hostname
- Storage classes
- Autoscaling parameters

### 2. Use External Secrets (Recommended)

Instead of passing secrets via `--set`, use Kubernetes secrets management:

```bash
# Using External Secrets Operator (recommended)
cat <<EOF | kubectl apply -f -
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: rapids-secrets
  namespace: rapids
spec:
  refreshInterval: 1h
  secretStoreRef:
    name: aws-secretsmanager
    kind: SecretStore
  target:
    name: rapids-orchestrator
  data:
    - secretKey: ANTHROPIC_API_KEY
      remoteRef:
        key: rapids/anthropic-api-key
    - secretKey: JWT_SECRET_KEY
      remoteRef:
        key: rapids/jwt-secret-key
    - secretKey: POSTGRES_PASSWORD
      remoteRef:
        key: rapids/postgres-password
EOF
```

### 3. Install with Production Values

```bash
helm install rapids-orchestrator ./deployment/helm/rapids-orchestrator \
  --namespace rapids \
  --create-namespace \
  --values values-custom.yaml \
  --wait \
  --timeout 10m
```

### 4. Configure SSL/TLS

#### Option A: Using cert-manager (Recommended)

cert-manager is already configured in the ingress annotations. Just ensure cert-manager is installed:

```bash
# Install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml

# Create ClusterIssuer for Let's Encrypt
cat <<EOF | kubectl apply -f -
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: your-email@example.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
      - http01:
          ingress:
            class: nginx
EOF
```

#### Option B: Using Existing Certificate

```bash
# Create TLS secret from existing certificate
kubectl create secret tls rapids-tls \
  --namespace rapids \
  --cert=path/to/tls.crt \
  --key=path/to/tls.key
```

### 5. Verify Production Deployment

```bash
# Check all resources
kubectl get all -n rapids

# Check HPA status
kubectl get hpa -n rapids

# Check persistent volumes
kubectl get pvc -n rapids

# Test health endpoints
curl https://rapids.yourcompany.com/health
```

## Monitoring

### Prometheus ServiceMonitor

Enable monitoring with Prometheus Operator:

```yaml
# In values.yaml
monitoring:
  enabled: true
  serviceMonitor:
    enabled: true
    interval: 30s
```

This creates ServiceMonitor resources for:
- Backend API metrics
- PostgreSQL metrics (via postgres-exporter sidecar)

### Available Metrics

Backend exposes metrics at `/metrics`:
- `http_requests_total` - Total HTTP requests
- `http_request_duration_seconds` - Request duration histogram
- `agent_operations_total` - Agent operations counter
- `active_agents_gauge` - Currently active agents
- `websocket_connections_gauge` - Active WebSocket connections

### Grafana Dashboards

Import pre-built dashboards:

```bash
# Import dashboards from infrastructure/grafana/dashboards/
kubectl create configmap rapids-dashboards \
  --namespace monitoring \
  --from-file=infrastructure/grafana/dashboards/
```

## Scaling

### Manual Scaling

```bash
# Scale backend
kubectl scale deployment rapids-orchestrator-backend -n rapids --replicas=5

# Scale frontend
kubectl scale deployment rapids-orchestrator-frontend -n rapids --replicas=3
```

### Auto-Scaling

HPA is configured by default based on CPU and memory:

```yaml
backend:
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 10
    targetCPUUtilizationPercentage: 70
    targetMemoryUtilizationPercentage: 80
```

Monitor HPA behavior:

```bash
kubectl get hpa -n rapids -w
```

## Backup and Restore

### Database Backup

```bash
# Manual backup
kubectl exec -n rapids rapids-orchestrator-postgresql-0 -- \
  pg_dump -U rapids rapids_orchestrator > backup-$(date +%Y%m%d-%H%M%S).sql

# Automated backup with CronJob
cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: CronJob
metadata:
  name: postgresql-backup
  namespace: rapids
spec:
  schedule: "0 2 * * *"  # Daily at 2 AM
  jobTemplate:
    spec:
      template:
        spec:
          containers:
            - name: backup
              image: postgres:16-alpine
              command:
                - /bin/sh
                - -c
                - |
                  pg_dump -h rapids-orchestrator-postgresql -U rapids rapids_orchestrator | \
                  gzip > /backup/backup-\$(date +%Y%m%d-%H%M%S).sql.gz
              env:
                - name: PGPASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: rapids-orchestrator
                      key: POSTGRES_PASSWORD
              volumeMounts:
                - name: backup
                  mountPath: /backup
          volumes:
            - name: backup
              persistentVolumeClaim:
                claimName: postgresql-backup
          restartPolicy: OnFailure
EOF
```

### Workspace Backup

```bash
# Create a backup of workspace PVC
kubectl exec -n rapids deployment/rapids-orchestrator-backend -- \
  tar czf - /app/workspace | cat > workspace-backup-$(date +%Y%m%d).tar.gz
```

### Restore from Backup

```bash
# Restore database
cat backup.sql | kubectl exec -i -n rapids rapids-orchestrator-postgresql-0 -- \
  psql -U rapids rapids_orchestrator

# Restore workspace
cat workspace-backup.tar.gz | kubectl exec -i -n rapids deployment/rapids-orchestrator-backend -- \
  tar xzf - -C /
```

## Upgrading

### Helm Upgrade

```bash
# Update chart
helm upgrade rapids-orchestrator ./deployment/helm/rapids-orchestrator \
  --namespace rapids \
  --values values-custom.yaml \
  --wait

# Rollback if needed
helm rollback rapids-orchestrator -n rapids
```

### Database Migrations

Migrations run automatically via Helm hooks before installation/upgrade. Check migration logs:

```bash
kubectl logs -n rapids -l app.kubernetes.io/component=migrations
```

## Troubleshooting

### Common Issues

#### 1. Pods Not Starting

```bash
# Check pod status
kubectl get pods -n rapids

# Describe pod for events
kubectl describe pod <pod-name> -n rapids

# Check logs
kubectl logs <pod-name> -n rapids
```

#### 2. Database Connection Issues

```bash
# Check PostgreSQL pod
kubectl logs -n rapids rapids-orchestrator-postgresql-0

# Test connection from backend
kubectl exec -n rapids deployment/rapids-orchestrator-backend -- \
  pg_isready -h rapids-orchestrator-postgresql -p 5432
```

#### 3. Ingress Not Working

```bash
# Check ingress status
kubectl get ingress -n rapids
kubectl describe ingress rapids-orchestrator -n rapids

# Check ingress controller logs
kubectl logs -n ingress-nginx deployment/ingress-nginx-controller
```

#### 4. WebSocket Connection Failures

Ensure ingress has proper WebSocket annotations:

```yaml
nginx.ingress.kubernetes.io/websocket-services: "rapids-backend"
nginx.ingress.kubernetes.io/proxy-read-timeout: "3600"
nginx.ingress.kubernetes.io/proxy-send-timeout: "3600"
```

### Debug Mode

Enable debug logging:

```bash
helm upgrade rapids-orchestrator ./deployment/helm/rapids-orchestrator \
  --namespace rapids \
  --set backend.env.LOG_LEVEL=debug \
  --reuse-values
```

### Get Shell Access

```bash
# Backend pod
kubectl exec -it -n rapids deployment/rapids-orchestrator-backend -- /bin/bash

# PostgreSQL pod
kubectl exec -it -n rapids rapids-orchestrator-postgresql-0 -- /bin/bash

# Frontend pod
kubectl exec -it -n rapids deployment/rapids-orchestrator-frontend -- /bin/sh
```

## Resource Requirements

### Minimum (Development/Staging)

- **Backend**: 500m CPU, 1Gi memory (2 replicas)
- **Frontend**: 100m CPU, 128Mi memory (2 replicas)
- **PostgreSQL**: 500m CPU, 2Gi memory
- **Total**: ~2 CPUs, 5Gi memory

### Recommended (Production)

- **Backend**: 1-4 CPUs, 2-8Gi memory (3-20 replicas with HPA)
- **Frontend**: 200m-1 CPU, 256Mi-1Gi memory (3-10 replicas with HPA)
- **PostgreSQL**: 2-4 CPUs, 8-16Gi memory with 200Gi SSD storage
- **Total**: ~5-12 CPUs, 12-30Gi memory (base + auto-scaling headroom)

## Security Considerations

1. **Network Policies**: Enabled by default to restrict pod-to-pod communication
2. **Pod Security**: Runs as non-root user (UID 1000)
3. **Secrets Management**: Use external secrets operator for production
4. **RBAC**: ServiceAccount with minimal permissions
5. **TLS**: HTTPS enforced via ingress
6. **Image Security**: Use official base images, scan for vulnerabilities

## High Availability

For HA deployment:

```yaml
backend:
  replicaCount: 3
  affinity:
    podAntiAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        - labelSelector:
            matchExpressions:
              - key: app.kubernetes.io/component
                operator: In
                values:
                  - backend
          topologyKey: kubernetes.io/hostname

postgresql:
  # For HA, use external PostgreSQL cluster (Cloud SQL, RDS, etc.)
  enabled: false

# Configure external database
backend:
  env:
    DATABASE_URL: "postgresql://user:pass@external-db:5432/rapids"
```

## Support

For issues and questions:
- GitHub Issues: https://github.com/nbalawat/multi-agentic-orchestration/issues
- Documentation: README.md in project root

## License

Private - All rights reserved
