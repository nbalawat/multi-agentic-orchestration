#!/bin/bash
# RAPIDS Meta-Orchestrator - Deployment Validation Script

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

NAMESPACE="${NAMESPACE:-rapids}"
RELEASE_NAME="${RELEASE_NAME:-rapids-orchestrator}"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     RAPIDS Deployment Validation                               ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check prerequisites
if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}✗ kubectl not found${NC}"
    exit 1
fi

# Check namespace exists
echo -e "${YELLOW}[1/10] Checking namespace...${NC}"
if kubectl get namespace "$NAMESPACE" &> /dev/null; then
    echo -e "${GREEN}✓ Namespace '$NAMESPACE' exists${NC}"
else
    echo -e "${RED}✗ Namespace '$NAMESPACE' not found${NC}"
    exit 1
fi
echo ""

# Check Helm release
echo -e "${YELLOW}[2/10] Checking Helm release...${NC}"
if helm list -n "$NAMESPACE" | grep -q "$RELEASE_NAME"; then
    RELEASE_STATUS=$(helm status "$RELEASE_NAME" -n "$NAMESPACE" -o json | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
    if [ "$RELEASE_STATUS" = "deployed" ]; then
        echo -e "${GREEN}✓ Helm release '$RELEASE_NAME' is deployed${NC}"
    else
        echo -e "${YELLOW}⚠ Helm release status: $RELEASE_STATUS${NC}"
    fi
else
    echo -e "${RED}✗ Helm release '$RELEASE_NAME' not found${NC}"
    exit 1
fi
echo ""

# Check pods
echo -e "${YELLOW}[3/10] Checking pods...${NC}"
PODS_READY=$(kubectl get pods -n "$NAMESPACE" -o json | jq -r '.items[] | select(.status.phase=="Running") | .metadata.name' | wc -l | tr -d ' ')
PODS_TOTAL=$(kubectl get pods -n "$NAMESPACE" --no-headers | wc -l | tr -d ' ')

if [ "$PODS_READY" -eq "$PODS_TOTAL" ] && [ "$PODS_TOTAL" -gt 0 ]; then
    echo -e "${GREEN}✓ All pods are running ($PODS_READY/$PODS_TOTAL)${NC}"
    kubectl get pods -n "$NAMESPACE"
else
    echo -e "${RED}✗ Not all pods are running ($PODS_READY/$PODS_TOTAL)${NC}"
    kubectl get pods -n "$NAMESPACE"
fi
echo ""

# Check backend deployment
echo -e "${YELLOW}[4/10] Checking backend deployment...${NC}"
BACKEND_READY=$(kubectl get deployment "$RELEASE_NAME-backend" -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
BACKEND_DESIRED=$(kubectl get deployment "$RELEASE_NAME-backend" -n "$NAMESPACE" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "0")

if [ "$BACKEND_READY" -eq "$BACKEND_DESIRED" ] && [ "$BACKEND_DESIRED" -gt 0 ]; then
    echo -e "${GREEN}✓ Backend deployment ready ($BACKEND_READY/$BACKEND_DESIRED replicas)${NC}"
else
    echo -e "${RED}✗ Backend deployment not ready ($BACKEND_READY/$BACKEND_DESIRED replicas)${NC}"
fi
echo ""

# Check frontend deployment
echo -e "${YELLOW}[5/10] Checking frontend deployment...${NC}"
FRONTEND_READY=$(kubectl get deployment "$RELEASE_NAME-frontend" -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
FRONTEND_DESIRED=$(kubectl get deployment "$RELEASE_NAME-frontend" -n "$NAMESPACE" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "0")

if [ "$FRONTEND_READY" -eq "$FRONTEND_DESIRED" ] && [ "$FRONTEND_DESIRED" -gt 0 ]; then
    echo -e "${GREEN}✓ Frontend deployment ready ($FRONTEND_READY/$FRONTEND_DESIRED replicas)${NC}"
else
    echo -e "${RED}✗ Frontend deployment not ready ($FRONTEND_READY/$FRONTEND_DESIRED replicas)${NC}"
fi
echo ""

# Check PostgreSQL
echo -e "${YELLOW}[6/10] Checking PostgreSQL...${NC}"
if kubectl get statefulset "$RELEASE_NAME-postgresql" -n "$NAMESPACE" &> /dev/null; then
    PG_READY=$(kubectl get statefulset "$RELEASE_NAME-postgresql" -n "$NAMESPACE" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    if [ "$PG_READY" -eq 1 ]; then
        echo -e "${GREEN}✓ PostgreSQL is ready${NC}"
    else
        echo -e "${RED}✗ PostgreSQL not ready${NC}"
    fi
else
    echo -e "${YELLOW}⚠ PostgreSQL StatefulSet not found (using external DB?)${NC}"
fi
echo ""

# Check services
echo -e "${YELLOW}[7/10] Checking services...${NC}"
SERVICES=$(kubectl get svc -n "$NAMESPACE" -l "app.kubernetes.io/instance=$RELEASE_NAME" --no-headers | wc -l | tr -d ' ')
if [ "$SERVICES" -ge 3 ]; then
    echo -e "${GREEN}✓ Services are configured ($SERVICES services)${NC}"
    kubectl get svc -n "$NAMESPACE" -l "app.kubernetes.io/instance=$RELEASE_NAME"
else
    echo -e "${RED}✗ Missing services (found $SERVICES, expected at least 3)${NC}"
fi
echo ""

# Check ingress
echo -e "${YELLOW}[8/10] Checking ingress...${NC}"
if kubectl get ingress "$RELEASE_NAME" -n "$NAMESPACE" &> /dev/null; then
    INGRESS_HOST=$(kubectl get ingress "$RELEASE_NAME" -n "$NAMESPACE" -o jsonpath='{.spec.rules[0].host}')
    echo -e "${GREEN}✓ Ingress configured${NC}"
    echo "   Host: $INGRESS_HOST"
    kubectl get ingress "$RELEASE_NAME" -n "$NAMESPACE"
else
    echo -e "${YELLOW}⚠ Ingress not found${NC}"
fi
echo ""

# Check PVCs
echo -e "${YELLOW}[9/10] Checking persistent volumes...${NC}"
PVCS=$(kubectl get pvc -n "$NAMESPACE" --no-headers | wc -l | tr -d ' ')
if [ "$PVCS" -gt 0 ]; then
    echo -e "${GREEN}✓ Persistent volumes configured ($PVCS PVCs)${NC}"
    kubectl get pvc -n "$NAMESPACE"
else
    echo -e "${YELLOW}⚠ No persistent volumes found${NC}"
fi
echo ""

# Health check
echo -e "${YELLOW}[10/10] Testing health endpoints...${NC}"

# Get backend pod
BACKEND_POD=$(kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/component=backend" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [ -n "$BACKEND_POD" ]; then
    if kubectl exec -n "$NAMESPACE" "$BACKEND_POD" -- curl -sf http://localhost:9403/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Backend health check passed${NC}"
    else
        echo -e "${RED}✗ Backend health check failed${NC}"
    fi
else
    echo -e "${RED}✗ No backend pod found${NC}"
fi
echo ""

# Summary
echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     Validation Summary                                         ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "Namespace:         $NAMESPACE"
echo "Release:           $RELEASE_NAME"
echo "Backend replicas:  $BACKEND_READY/$BACKEND_DESIRED"
echo "Frontend replicas: $FRONTEND_READY/$FRONTEND_DESIRED"
echo "Running pods:      $PODS_READY/$PODS_TOTAL"
echo "Services:          $SERVICES"
echo "PVCs:              $PVCS"
echo ""

# Check HPA
if kubectl get hpa -n "$NAMESPACE" &> /dev/null 2>&1; then
    echo -e "${YELLOW}HPA Status:${NC}"
    kubectl get hpa -n "$NAMESPACE"
    echo ""
fi

# Final verdict
if [ "$PODS_READY" -eq "$PODS_TOTAL" ] && [ "$BACKEND_READY" -eq "$BACKEND_DESIRED" ] && [ "$FRONTEND_READY" -eq "$FRONTEND_DESIRED" ]; then
    echo -e "${GREEN}✓ RAPIDS deployment is healthy!${NC}"
    echo ""
    echo "Access your application at: https://$INGRESS_HOST"
    exit 0
else
    echo -e "${RED}✗ RAPIDS deployment has issues${NC}"
    echo ""
    echo "Troubleshooting commands:"
    echo "  kubectl get pods -n $NAMESPACE"
    echo "  kubectl logs -n $NAMESPACE <pod-name>"
    echo "  kubectl describe pod -n $NAMESPACE <pod-name>"
    exit 1
fi
