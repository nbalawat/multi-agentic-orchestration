# RAPIDS Kubernetes Deployment - Quick Start

Get RAPIDS running on Kubernetes in 5 minutes.

## Prerequisites

- Kubernetes cluster (1.24+)
- Helm 3.12+
- kubectl configured
- Docker images built and pushed

## 1. Build Images

```bash
# Set your registry
export REGISTRY="your-registry.com/rapids"

# Build and push
docker build -f Dockerfile.backend -t $REGISTRY/backend:0.1.0 .
docker push $REGISTRY/backend:0.1.0

docker build -f Dockerfile.frontend -t $REGISTRY/frontend:0.1.0 .
docker push $REGISTRY/frontend:0.1.0
```

## 2. Run Installation Script

```bash
cd deployment/scripts
./install.sh
```

Follow the prompts to provide:
- Anthropic API key
- PostgreSQL password
- Ingress hostname

## 3. Verify Deployment

```bash
# Watch pods start
kubectl get pods -n rapids -w

# Check migration completed
kubectl logs -n rapids -l app.kubernetes.io/component=migrations

# Get URL
kubectl get ingress -n rapids
```

## 4. Access Application

Visit: `https://your-ingress-hostname`

## Troubleshooting

### Pods not starting?

```bash
kubectl describe pod <pod-name> -n rapids
kubectl logs <pod-name> -n rapids
```

### Database connection issues?

```bash
kubectl logs -n rapids rapids-orchestrator-postgresql-0
```

### Ingress not working?

```bash
kubectl describe ingress rapids-orchestrator -n rapids
```

## Next Steps

- [Full Documentation](README.md)
- [Configuration Guide](README.md#configuration)
- [Production Deployment](README.md#production-deployment)
- [Monitoring Setup](README.md#monitoring)

## Quick Commands

```bash
# View all resources
kubectl get all -n rapids

# Scale backend
kubectl scale deployment rapids-orchestrator-backend -n rapids --replicas=5

# View logs
kubectl logs -n rapids -l app.kubernetes.io/component=backend -f

# Upgrade
cd deployment/scripts && ./upgrade.sh

# Uninstall
cd deployment/scripts && ./uninstall.sh
```
