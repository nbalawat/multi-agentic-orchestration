#!/bin/bash
# Quick start script for RAPIDS backup system

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
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

# Check prerequisites
info "Checking prerequisites..."

# Check Python
if ! command -v python3 &> /dev/null; then
    error "Python 3 is required but not installed"
fi

# Check PostgreSQL client tools
if ! command -v pg_dump &> /dev/null; then
    error "PostgreSQL client tools (pg_dump) not found. Install with: brew install postgresql@16 (macOS) or apt-get install postgresql-client-16 (Ubuntu)"
fi

if ! command -v pg_restore &> /dev/null; then
    error "PostgreSQL client tools (pg_restore) not found"
fi

info "✓ Prerequisites check passed"

# Check environment
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    warn "No .env file found. Creating from sample..."
    cp "$SCRIPT_DIR/.env.sample" "$SCRIPT_DIR/.env"
    warn "Please edit .env file with your configuration"
    exit 0
fi

# Load environment
set -a
source "$SCRIPT_DIR/.env"
set +a

# Verify DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    error "DATABASE_URL not set in .env file"
fi

info "Environment loaded successfully"

# Show menu
echo ""
echo "====================================="
echo "  RAPIDS Backup System Quick Start"
echo "====================================="
echo ""
echo "What would you like to do?"
echo ""
echo "  1) Create a backup"
echo "  2) Verify backups"
echo "  3) List backups"
echo "  4) Restore from latest backup"
echo "  5) Restore from specific backup"
echo "  6) Test backup system (dry run)"
echo "  7) Exit"
echo ""
read -p "Enter choice [1-7]: " choice

case $choice in
    1)
        info "Creating backup..."
        python3 "$SCRIPT_DIR/backup.py"
        ;;
    2)
        info "Verifying all backups..."
        python3 "$SCRIPT_DIR/verify.py" --all
        ;;
    3)
        info "Listing backups..."
        ls -lh "${BACKUP_DIR:-./backups}/rapids_backup_*.dump" 2>/dev/null || warn "No backups found"
        ;;
    4)
        warn "This will restore the database from the latest backup."
        read -p "Are you sure? (yes/no): " confirm
        if [ "$confirm" = "yes" ]; then
            info "Restoring from latest backup..."
            python3 "$SCRIPT_DIR/restore.py" --latest
        else
            info "Restore cancelled"
        fi
        ;;
    5)
        info "Available backups:"
        ls -1 "${BACKUP_DIR:-./backups}/rapids_backup_*.dump" 2>/dev/null | sed 's/.*rapids_backup_//' | sed 's/.dump//' || warn "No backups found"
        echo ""
        read -p "Enter timestamp (YYYYMMDD_HHMMSS): " timestamp
        if [ -n "$timestamp" ]; then
            python3 "$SCRIPT_DIR/restore.py" --backup-file "${BACKUP_DIR:-./backups}/rapids_backup_${timestamp}.dump"
        fi
        ;;
    6)
        info "Running dry-run restore test..."
        python3 "$SCRIPT_DIR/restore.py" --latest --dry-run
        ;;
    7)
        info "Exiting..."
        exit 0
        ;;
    *)
        error "Invalid choice"
        ;;
esac

info "Operation completed successfully!"
