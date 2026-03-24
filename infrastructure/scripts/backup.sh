#!/bin/bash
# RAPIDS Meta-Orchestrator Backup Script
# Creates backups of PostgreSQL database and uploads to S3 (if configured)

set -e
set -u

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BACKUP_DIR="${PROJECT_ROOT}/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="rapids_backup_${TIMESTAMP}.sql.gz"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

# Load environment
ENV_FILE="${PROJECT_ROOT}/.env.production"
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
else
    error "Environment file not found: $ENV_FILE"
fi

# Create backup directory
mkdir -p "$BACKUP_DIR"

info "Starting backup..."

# Determine if using Docker or remote PostgreSQL
if docker ps --format '{{.Names}}' | grep -q rapids-postgres; then
    info "Backing up Docker PostgreSQL..."
    docker exec rapids-postgres pg_dump \
        -U "${POSTGRES_USER}" \
        -d "${POSTGRES_DB}" \
        --format=custom \
        --compress=9 \
        --file=/tmp/backup.dump

    docker cp rapids-postgres:/tmp/backup.dump "${BACKUP_DIR}/${BACKUP_FILE%.gz}"
    gzip "${BACKUP_DIR}/${BACKUP_FILE%.gz}"
else
    info "Backing up remote PostgreSQL..."
    pg_dump "${DATABASE_URL}" \
        --format=custom \
        --compress=9 \
        --file="${BACKUP_DIR}/${BACKUP_FILE%.gz}"
    gzip "${BACKUP_DIR}/${BACKUP_FILE%.gz}"
fi

info "Backup created: ${BACKUP_DIR}/${BACKUP_FILE}"

# Upload to S3 if configured
if [ -n "${S3_BACKUP_BUCKET:-}" ] && [ -n "${AWS_ACCESS_KEY_ID:-}" ]; then
    info "Uploading to S3: s3://${S3_BACKUP_BUCKET}/backups/${BACKUP_FILE}"
    aws s3 cp "${BACKUP_DIR}/${BACKUP_FILE}" "s3://${S3_BACKUP_BUCKET}/backups/${BACKUP_FILE}"
    info "Upload complete"
else
    info "S3 backup not configured, skipping upload"
fi

# Clean up old backups (keep last 7 days locally)
info "Cleaning up old local backups..."
find "$BACKUP_DIR" -name "rapids_backup_*.sql.gz" -mtime +7 -delete

# Clean up old S3 backups (keep based on retention policy)
if [ -n "${S3_BACKUP_BUCKET:-}" ] && [ -n "${BACKUP_RETENTION_DAYS:-30}" ]; then
    info "Cleaning up old S3 backups (older than ${BACKUP_RETENTION_DAYS} days)..."
    CUTOFF_DATE=$(date -d "${BACKUP_RETENTION_DAYS} days ago" +%Y-%m-%d)
    aws s3 ls "s3://${S3_BACKUP_BUCKET}/backups/" \
        | awk '{print $4}' \
        | while read -r file; do
            FILE_DATE=$(echo "$file" | grep -oP '\d{8}' | head -1)
            if [[ "$FILE_DATE" < "${CUTOFF_DATE//-/}" ]]; then
                info "Deleting old backup: $file"
                aws s3 rm "s3://${S3_BACKUP_BUCKET}/backups/$file"
            fi
        done
fi

info "Backup completed successfully!"
echo "Local backup: ${BACKUP_DIR}/${BACKUP_FILE}"
