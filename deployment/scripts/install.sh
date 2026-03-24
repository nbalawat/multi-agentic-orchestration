#!/bin/bash
# RAPIDS Meta-Orchestrator - Kubernetes Installation Script
# This script helps you deploy RAPIDS to Kubernetes using Helm

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
NAMESPACE="${NAMESPACE:-rapids}"
RELEASE_NAME="${RELEASE_NAME:-rapids-orchestrator}"
CHART_PATH="$(dirname "$0")/../helm/rapids-orchestrator"

echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     RAPIDS Meta-Orchestrator Kubernetes Installer              ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check prerequisites
echo -e "${YELLOW}[1/7] Checking prerequisites...${NC}"

if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}✗ kubectl not found. Please install kubectl.${NC}"
    exit 1
fi

if ! command -v helm &> /dev/null; then
    echo -e "${RED}✗ Helm not found. Please install Helm 3.${NC}"
    exit 1
fi

# Check Kubernetes cluster access
if ! kubectl cluster-info &> /dev/null; then
    echo -e "${RED}✗ Cannot access Kubernetes cluster. Please configure kubectl.${NC}"
    exit 1
fi

echo -e "${GREEN}✓ kubectl found: $(kubectl version --client --short 2>/dev/null || kubectl version --client)${NC}"
echo -e "${GREEN}✓ Helm found: $(helm version --short)${NC}"
echo -e "${GREEN}✓ Kubernetes cluster accessible${NC}"
echo ""

# Collect configuration
echo -e "${YELLOW}[2/7] Gathering configuration...${NC}"

read -p "Enter namespace [rapids]: " input_namespace
NAMESPACE="${input_namespace:-$NAMESPACE}"

read -p "Enter release name [rapids-orchestrator]: " input_release
RELEASE_NAME="${input_release:-$RELEASE_NAME}"

read -p "Enter backend image repository [rapids-orchestrator/backend]: " backend_repo
BACKEND_REPO="${backend_repo:-rapids-orchestrator/backend}"

read -p "Enter backend image tag [0.1.0]: " backend_tag
BACKEND_TAG="${backend_tag:-0.1.0}"

read -p "Enter frontend image repository [rapids-orchestrator/frontend]: " frontend_repo
FRONTEND_REPO="${frontend_repo:-rapids-orchestrator/frontend}"

read -p "Enter frontend image tag [0.1.0]: " frontend_tag
FRONTEND_TAG="${frontend_tag:-0.1.0}"

read -p "Enter ingress hostname [rapids.example.com]: " ingress_host
INGRESS_HOST="${ingress_host:-rapids.example.com}"

echo ""

# Create namespace
echo -e "${YELLOW}[3/7] Creating namespace...${NC}"
if kubectl get namespace "$NAMESPACE" &> /dev/null; then
    echo -e "${GREEN}✓ Namespace '$NAMESPACE' already exists${NC}"
else
    kubectl create namespace "$NAMESPACE"
    echo -e "${GREEN}✓ Created namespace '$NAMESPACE'${NC}"
fi
echo ""

# Collect secrets
echo -e "${YELLOW}[4/7] Configuring secrets...${NC}"
echo "Please provide the following secrets:"

read -sp "Anthropic API Key: " anthropic_key
echo ""
if [ -z "$anthropic_key" ]; then
    echo -e "${RED}✗ Anthropic API Key is required${NC}"
    exit 1
fi

# Generate JWT secret if not provided
echo "JWT Secret (leave empty to auto-generate): "
read -s jwt_secret
echo ""
if [ -z "$jwt_secret" ]; then
    jwt_secret=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null || openssl rand -base64 32)
    echo -e "${GREEN}✓ Generated JWT secret${NC}"
fi

read -sp "PostgreSQL Password: " postgres_password
echo ""
if [ -z "$postgres_password" ]; then
    echo -e "${RED}✗ PostgreSQL Password is required${NC}"
    exit 1
fi

echo ""

# Validate Helm chart
echo -e "${YELLOW}[5/7] Validating Helm chart...${NC}"
if [ ! -f "$CHART_PATH/Chart.yaml" ]; then
    echo -e "${RED}✗ Helm chart not found at $CHART_PATH${NC}"
    exit 1
fi

helm lint "$CHART_PATH" > /dev/null
echo -e "${GREEN}✓ Helm chart validation passed${NC}"
echo ""

# Create values file
echo -e "${YELLOW}[6/7] Creating custom values file...${NC}"
VALUES_FILE="/tmp/rapids-values-$$.yaml"

cat > "$VALUES_FILE" <<EOF
backend:
  image:
    repository: $BACKEND_REPO
    tag: "$BACKEND_TAG"
  secretEnv:
    ANTHROPIC_API_KEY: "$anthropic_key"
    JWT_SECRET_KEY: "$jwt_secret"

frontend:
  image:
    repository: $FRONTEND_REPO
    tag: "$FRONTEND_TAG"

postgresql:
  auth:
    password: "$postgres_password"

ingress:
  hosts:
    - host: $INGRESS_HOST
      paths:
        - path: /api
          pathType: Prefix
          backend: backend
        - path: /ws
          pathType: Prefix
          backend: backend
        - path: /health
          pathType: Prefix
          backend: backend
        - path: /
          pathType: Prefix
          backend: frontend
  tls:
    - secretName: rapids-tls
      hosts:
        - $INGRESS_HOST
EOF

echo -e "${GREEN}✓ Created custom values file${NC}"
echo ""

# Install with Helm
echo -e "${YELLOW}[7/7] Installing RAPIDS with Helm...${NC}"
echo "Running: helm install $RELEASE_NAME $CHART_PATH --namespace $NAMESPACE --values $VALUES_FILE --wait --timeout 10m"
echo ""

helm install "$RELEASE_NAME" "$CHART_PATH" \
  --namespace "$NAMESPACE" \
  --create-namespace \
  --values "$VALUES_FILE" \
  --wait \
  --timeout 10m

# Cleanup values file (contains secrets)
rm -f "$VALUES_FILE"

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              Installation Completed Successfully!              ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${YELLOW}Next steps:${NC}"
echo ""
echo "1. Check deployment status:"
echo "   kubectl get pods -n $NAMESPACE"
echo ""
echo "2. Watch migration job:"
echo "   kubectl logs -n $NAMESPACE -l app.kubernetes.io/component=migrations -f"
echo ""
echo "3. Access the application:"
echo "   https://$INGRESS_HOST"
echo ""
echo "4. View backend logs:"
echo "   kubectl logs -n $NAMESPACE -l app.kubernetes.io/component=backend -f"
echo ""
echo "5. Check HPA status:"
echo "   kubectl get hpa -n $NAMESPACE"
echo ""
echo -e "${YELLOW}For more information, see deployment/README.md${NC}"
