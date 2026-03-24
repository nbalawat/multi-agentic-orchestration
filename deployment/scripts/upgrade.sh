#!/bin/bash
# RAPIDS Meta-Orchestrator - Upgrade Script

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

NAMESPACE="${NAMESPACE:-rapids}"
RELEASE_NAME="${RELEASE_NAME:-rapids-orchestrator}"
CHART_PATH="$(dirname "$0")/../helm/rapids-orchestrator"

echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     RAPIDS Meta-Orchestrator Upgrade Tool                      ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

read -p "Namespace [$NAMESPACE]: " input_namespace
NAMESPACE="${input_namespace:-$NAMESPACE}"

read -p "Release name [$RELEASE_NAME]: " input_release
RELEASE_NAME="${input_release:-$RELEASE_NAME}"

read -p "Backend image tag [current]: " backend_tag
read -p "Frontend image tag [current]: " frontend_tag

echo ""
echo -e "${YELLOW}Upgrading RAPIDS...${NC}"

# Build helm upgrade command
UPGRADE_CMD="helm upgrade $RELEASE_NAME $CHART_PATH --namespace $NAMESPACE --wait --timeout 10m"

if [ -n "$backend_tag" ]; then
    UPGRADE_CMD="$UPGRADE_CMD --set backend.image.tag=$backend_tag"
fi

if [ -n "$frontend_tag" ]; then
    UPGRADE_CMD="$UPGRADE_CMD --set frontend.image.tag=$frontend_tag"
fi

echo "Running: $UPGRADE_CMD"
echo ""

eval "$UPGRADE_CMD"

echo ""
echo -e "${GREEN}✓ Upgrade complete${NC}"
echo ""
echo "Check pod status:"
echo "  kubectl get pods -n $NAMESPACE"
echo ""
echo "View migration logs:"
echo "  kubectl logs -n $NAMESPACE -l app.kubernetes.io/component=migrations -f"
echo ""
echo "Rollback if needed:"
echo "  helm rollback $RELEASE_NAME -n $NAMESPACE"
