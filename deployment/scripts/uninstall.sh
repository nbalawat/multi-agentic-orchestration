#!/bin/bash
# RAPIDS Meta-Orchestrator - Uninstall Script

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

NAMESPACE="${NAMESPACE:-rapids}"
RELEASE_NAME="${RELEASE_NAME:-rapids-orchestrator}"

echo -e "${YELLOW}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${YELLOW}║     RAPIDS Meta-Orchestrator Uninstaller                       ║${NC}"
echo -e "${YELLOW}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${RED}WARNING: This will delete the RAPIDS installation and all data!${NC}"
echo ""
read -p "Namespace [$NAMESPACE]: " input_namespace
NAMESPACE="${input_namespace:-$NAMESPACE}"

read -p "Release name [$RELEASE_NAME]: " input_release
RELEASE_NAME="${input_release:-$RELEASE_NAME}"

echo ""
echo -e "${RED}This will delete:${NC}"
echo "  - Helm release: $RELEASE_NAME"
echo "  - Namespace: $NAMESPACE (and all resources)"
echo "  - Persistent volumes and data"
echo ""

read -p "Are you sure? Type 'yes' to confirm: " confirm
if [ "$confirm" != "yes" ]; then
    echo -e "${GREEN}Cancelled.${NC}"
    exit 0
fi

echo ""
echo -e "${YELLOW}Uninstalling RAPIDS...${NC}"

# Uninstall Helm release
echo "Deleting Helm release..."
helm uninstall "$RELEASE_NAME" --namespace "$NAMESPACE" || true

# Delete PVCs (optional - they won't be deleted by Helm)
echo ""
read -p "Delete persistent volumes (data will be lost)? [y/N]: " delete_pvcs
if [[ "$delete_pvcs" =~ ^[Yy]$ ]]; then
    echo "Deleting PVCs..."
    kubectl delete pvc --all -n "$NAMESPACE" || true
fi

# Delete namespace
echo ""
read -p "Delete namespace '$NAMESPACE'? [y/N]: " delete_ns
if [[ "$delete_ns" =~ ^[Yy]$ ]]; then
    echo "Deleting namespace..."
    kubectl delete namespace "$NAMESPACE" || true
fi

echo ""
echo -e "${GREEN}✓ Uninstall complete${NC}"
