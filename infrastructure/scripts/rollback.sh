#!/bin/bash
# RAPIDS Meta-Orchestrator Rollback Script
# Rolls back to a previous version or backup

set -e
set -u

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

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

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENVIRONMENT="${1:-production}"
COMPOSE_FILE="${PROJECT_ROOT}/docker-compose.${ENVIRONMENT}.yml"

echo -e "${YELLOW}================================${NC}"
echo -e "${YELLOW}RAPIDS Rollback Script${NC}"
echo -e "${YELLOW}================================${NC}"
echo ""

warn "This script will rollback the deployment."
read -p "Are you sure you want to continue? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    error "Rollback cancelled"
fi

# Load environment
ENV_FILE="${PROJECT_ROOT}/.env.${ENVIRONMENT}"
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
else
    error "Environment file not found: $ENV_FILE"
fi

# Rollback strategy selection
echo ""
echo "Select rollback strategy:"
echo "1. Rollback to previous Docker images (recommended)"
echo "2. Rollback to previous git commit"
echo "3. Restore from database backup"
read -p "Enter choice (1-3): " STRATEGY

case $STRATEGY in
    1)
        info "Rolling back Docker images..."

        # Stop current services
        docker compose -f "$COMPOSE_FILE" down

        # Pull previous version (assumes you tag with version or use 'previous')
        # You need to implement version tracking
        warn "Manual step: Specify the previous image tag"
        read -p "Enter backend image tag: " BACKEND_TAG
        read -p "Enter frontend image tag: " FRONTEND_TAG

        # Update compose file or use specific tags
        # docker compose -f "$COMPOSE_FILE" up -d
        info "Deploy previous images manually with: docker compose up -d"
        ;;

    2)
        info "Rolling back git repository..."

        cd "$PROJECT_ROOT"

        # Show recent commits
        git log --oneline -10
        echo ""
        read -p "Enter commit hash to rollback to: " COMMIT_HASH

        # Create backup branch
        BACKUP_BRANCH="backup-before-rollback-$(date +%Y%m%d-%H%M%S)"
        git branch "$BACKUP_BRANCH"
        info "Created backup branch: $BACKUP_BRANCH"

        # Rollback
        git reset --hard "$COMMIT_HASH"

        # Rebuild and deploy
        info "Rebuilding and deploying..."
        ./infrastructure/scripts/deploy.sh "$ENVIRONMENT"
        ;;

    3)
        info "Restoring from database backup..."

        BACKUP_DIR="${PROJECT_ROOT}/backups"

        # List available backups
        echo "Available backups:"
        ls -lh "$BACKUP_DIR"/rapids_backup_*.sql.gz 2>/dev/null || error "No backups found"
        echo ""
        read -p "Enter backup filename: " BACKUP_FILE

        BACKUP_PATH="${BACKUP_DIR}/${BACKUP_FILE}"
        if [ ! -f "$BACKUP_PATH" ]; then
            error "Backup file not found: $BACKUP_PATH"
        fi

        warn "This will OVERWRITE the current database!"
        read -p "Type 'RESTORE' to confirm: " RESTORE_CONFIRM
        if [ "$RESTORE_CONFIRM" != "RESTORE" ]; then
            error "Restore cancelled"
        fi

        # Stop services
        docker compose -f "$COMPOSE_FILE" stop fastapi-backend

        # Restore database
        info "Restoring database..."
        gunzip -c "$BACKUP_PATH" | docker exec -i rapids-postgres pg_restore \
            -U "${POSTGRES_USER}" \
            -d "${POSTGRES_DB}" \
            --clean \
            --if-exists

        # Restart services
        docker compose -f "$COMPOSE_FILE" start fastapi-backend

        info "Database restored successfully"
        ;;

    *)
        error "Invalid choice"
        ;;
esac

# Verify rollback
info "Verifying rollback..."
sleep 10

if curl -f http://localhost/health &>/dev/null; then
    info "Rollback completed successfully!"
else
    error "Health check failed after rollback"
fi

echo ""
info "Rollback process complete"
