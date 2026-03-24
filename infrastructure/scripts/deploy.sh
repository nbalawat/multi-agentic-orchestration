#!/bin/bash
# RAPIDS Meta-Orchestrator Deployment Script
# Usage: ./deploy.sh [environment]
# Environments: dev, staging, production

set -e  # Exit on error
set -u  # Exit on undefined variable

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENVIRONMENT="${1:-production}"
COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.${ENVIRONMENT}.yml"

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}RAPIDS Deployment Script${NC}"
echo -e "${GREEN}================================${NC}"
echo ""

# Function to print colored messages
info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(dev|staging|production)$ ]]; then
    error "Invalid environment: $ENVIRONMENT. Use dev, staging, or production."
fi

info "Deploying to: $ENVIRONMENT"

# Check if compose file exists
if [ ! -f "$COMPOSE_FILE" ]; then
    error "Compose file not found: $COMPOSE_FILE"
fi

# Check if .env file exists
ENV_FILE="${PROJECT_ROOT}/.env.${ENVIRONMENT}"
if [ ! -f "$ENV_FILE" ]; then
    error "Environment file not found: $ENV_FILE"
    echo "Please copy .env.${ENVIRONMENT}.template to .env.${ENVIRONMENT} and configure it."
fi

# Load environment variables
set -a
source "$ENV_FILE"
set +a

# Verify required environment variables
REQUIRED_VARS=(
    "POSTGRES_PASSWORD"
    "ANTHROPIC_API_KEY"
    "JWT_SECRET_KEY"
    "GRAFANA_ADMIN_PASSWORD"
)

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var:-}" ]; then
        error "Required environment variable not set: $var"
    fi
done

info "Environment variables validated"

# Pre-deployment checks
info "Running pre-deployment checks..."

# Check Docker
if ! command -v docker &> /dev/null; then
    error "Docker is not installed"
fi

# Check Docker Compose
if ! command -v docker &> /dev/null || ! docker compose version &> /dev/null; then
    error "Docker Compose is not installed"
fi

# Check available disk space (need at least 10GB)
AVAILABLE_SPACE=$(df -BG "$PROJECT_ROOT" | tail -1 | awk '{print $4}' | sed 's/G//')
if [ "$AVAILABLE_SPACE" -lt 10 ]; then
    warn "Low disk space: ${AVAILABLE_SPACE}GB available. Recommend at least 10GB."
fi

info "Pre-deployment checks passed"

# Build frontend if needed
info "Building frontend..."
cd "${PROJECT_ROOT}/orchestrator/frontend"
if [ ! -d "node_modules" ]; then
    info "Installing frontend dependencies..."
    npm ci
fi
npm run build
info "Frontend build complete"

# Create required directories
info "Creating required directories..."
mkdir -p "${PROJECT_ROOT}/logs"
mkdir -p "${PROJECT_ROOT}/workspace"
mkdir -p "${PROJECT_ROOT}/infrastructure/nginx/ssl"

# Pull latest images
info "Pulling latest Docker images..."
cd "$PROJECT_ROOT"
docker compose -f "$COMPOSE_FILE" pull

# Run database migrations
info "Running database migrations..."
# First, start only PostgreSQL
docker compose -f "$COMPOSE_FILE" up -d postgres
sleep 10  # Wait for PostgreSQL to be ready

# Run migrations (adjust path as needed)
if [ -d "${PROJECT_ROOT}/db/migrations" ]; then
    info "Applying database migrations..."
    # You can add migration logic here
    # Example: docker compose -f "$COMPOSE_FILE" exec -T postgres psql -U rapids -d rapids_orchestrator -f /migrations/001_init.sql
fi

# Deploy all services
info "Deploying all services..."
docker compose -f "$COMPOSE_FILE" up -d --remove-orphans

# Wait for services to be healthy
info "Waiting for services to be healthy..."
sleep 30

# Health check
info "Running health checks..."
BACKEND_HEALTH=$(docker compose -f "$COMPOSE_FILE" exec -T fastapi-backend curl -f http://localhost:9403/health 2>/dev/null || echo "FAILED")
if [[ "$BACKEND_HEALTH" == "FAILED" ]]; then
    error "Backend health check failed"
fi

PROMETHEUS_HEALTH=$(docker compose -f "$COMPOSE_FILE" exec -T prometheus wget -qO- http://localhost:9090/-/healthy 2>/dev/null || echo "FAILED")
if [[ "$PROMETHEUS_HEALTH" == "FAILED" ]]; then
    warn "Prometheus health check failed (non-critical)"
fi

info "Health checks passed"

# Clean up old images and containers
info "Cleaning up old Docker resources..."
docker system prune -f

# Display deployment info
echo ""
echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${GREEN}================================${NC}"
echo ""
echo "Environment: $ENVIRONMENT"
echo "Services running:"
docker compose -f "$COMPOSE_FILE" ps
echo ""
echo "Access URLs:"
echo "  - Frontend: http://localhost (or your domain)"
echo "  - Backend API: http://localhost/api"
echo "  - Grafana: http://localhost/grafana (user: admin)"
echo "  - Prometheus: http://localhost/prometheus"
echo ""
echo "Logs:"
echo "  docker compose -f $COMPOSE_FILE logs -f"
echo ""
echo "To stop:"
echo "  docker compose -f $COMPOSE_FILE down"
echo ""

info "Deployment completed successfully!"
