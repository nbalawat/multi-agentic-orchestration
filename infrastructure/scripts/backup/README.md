# RAPIDS Database Backup & Restore System

Comprehensive PostgreSQL backup and restore solution with verification, S3 upload, point-in-time recovery, and monitoring integration.

## Features

✅ **Automated Backups**
- PostgreSQL `pg_dump` with custom format and compression
- Scheduled via Kubernetes CronJob
- Configurable retention policies
- Automatic cleanup of old backups

✅ **Verification & Integrity**
- Automatic backup verification using `pg_restore --list`
- SHA256 checksum validation
- Backup metadata tracking
- Comprehensive verification reports

✅ **S3 Integration**
- Encrypted uploads to S3 (AES256)
- Configurable storage class (STANDARD_IA by default)
- Automatic S3 cleanup based on retention policy
- Support for downloading backups from S3

✅ **Point-in-Time Recovery**
- WAL LSN tracking for PITR
- Recovery target time support
- Pre-restore safety backups
- Dry-run mode for testing

✅ **Monitoring**
- Prometheus metrics export
- Backup success/failure tracking
- Duration and size metrics
- Integration with Grafana dashboards

## Directory Structure

```
infrastructure/scripts/backup/
├── backup.py          # Main backup script
├── restore.py         # Restore script with PITR support
├── verify.py          # Verification utility
└── README.md          # This file

deployment/helm/rapids-orchestrator/templates/
└── cronjob-backup.yaml  # Kubernetes CronJob configuration
```

## Quick Start

### Prerequisites

```bash
# Install required Python packages
uv pip install asyncpg rich python-dotenv

# Install PostgreSQL client tools
# macOS
brew install postgresql@16

# Ubuntu/Debian
apt-get install postgresql-client-16

# Alpine (Docker)
apk add postgresql16-client
```

### Configuration

Set environment variables:

```bash
# Required
export DATABASE_URL="postgresql://user:password@host:5432/dbname"

# Optional
export BACKUP_DIR="./backups"
export S3_BACKUP_BUCKET="rapids-orchestrator-backups"
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="us-east-1"
```

Or use a `.env` file:

```bash
cp .env.sample .env
# Edit .env with your configuration
```

## Usage

### Backup Operations

#### Create a Backup

```bash
# Basic backup (local only)
python backup.py

# Skip S3 upload
python backup.py --skip-s3

# Custom retention period
python backup.py --retention-days 60

# Specify backup directory
python backup.py --backup-dir /path/to/backups
```

#### Verify Backups

```bash
# Verify all backups
python verify.py --all

# Verify specific backup
python verify.py --backup-file rapids_backup_20260324_120000.dump

# Include S3 availability check
python verify.py --all --s3-check

# Export verification report as JSON
python verify.py --all --export-json report.json
```

### Restore Operations

#### Restore from Backup

```bash
# Restore from latest backup
python restore.py --latest

# Restore from specific backup file
python restore.py --backup-file rapids_backup_20260324_120000.dump

# Restore from S3 (downloads automatically)
python restore.py --from-s3 20260324_120000

# Dry run (show what would be restored)
python restore.py --latest --dry-run

# Force restore without confirmation
python restore.py --latest --force

# Skip pre-restore safety backup
python restore.py --latest --skip-pre-backup
```

## Kubernetes Deployment

### Install with Helm

```bash
# Enable backups in values.yaml
helm upgrade --install rapids-orchestrator ./deployment/helm/rapids-orchestrator \
  --set backup.enabled=true \
  --set backup.schedule="0 2 * * *" \
  --set backup.s3.bucket="my-backup-bucket" \
  --set backup.s3.region="us-east-1"
```

### Create S3 Credentials Secret

```bash
kubectl create secret generic s3-backup-credentials \
  --from-literal=access-key-id=YOUR_ACCESS_KEY \
  --from-literal=secret-access-key=YOUR_SECRET_KEY
```

### Manual Backup Job

```bash
# Trigger a manual backup
kubectl create job --from=cronjob/rapids-orchestrator-backup rapids-backup-manual-$(date +%s)

# View backup job logs
kubectl logs -f job/rapids-backup-manual-1234567890
```

### List Backup Jobs

```bash
# List all backup CronJobs
kubectl get cronjobs

# List backup job executions
kubectl get jobs -l app.kubernetes.io/component=backup

# View backup PVC
kubectl get pvc rapids-orchestrator-backups
```

## Backup Schedule Configuration

The CronJob schedule is configured in `values.yaml`:

```yaml
backup:
  enabled: true
  schedule: "0 2 * * *"  # Daily at 2 AM UTC
```

Common schedules:
- Daily at 2 AM: `"0 2 * * *"`
- Every 6 hours: `"0 */6 * * *"`
- Twice daily (2 AM, 2 PM): `"0 2,14 * * *"`
- Weekly (Sunday 2 AM): `"0 2 * * 0"`
- Hourly: `"0 * * * *"`

## Monitoring

### Prometheus Metrics

Backup scripts export metrics to `/backups/backup_metrics.prom`:

```prometheus
# Last successful backup timestamp
rapids_backup_last_success_timestamp{database="rapids_orchestrator"}

# Backup duration in seconds
rapids_backup_duration_seconds{database="rapids_orchestrator"}

# Backup file size in MB
rapids_backup_size_mb{database="rapids_orchestrator"}

# Database size in MB
rapids_backup_database_size_mb{database="rapids_orchestrator"}

# Backup verification status (1=verified, 0=failed)
rapids_backup_verified{database="rapids_orchestrator"}

# S3 upload status (1=uploaded, 0=failed)
rapids_backup_s3_uploaded{database="rapids_orchestrator"}
```

### Grafana Dashboard

Create alerts for backup monitoring:

```yaml
# Alert if no backup in last 25 hours
- alert: BackupMissing
  expr: time() - rapids_backup_last_success_timestamp > 90000
  annotations:
    summary: "No recent database backup"

# Alert if backup not verified
- alert: BackupNotVerified
  expr: rapids_backup_verified == 0
  annotations:
    summary: "Backup verification failed"
```

## Backup Metadata

Each backup creates a JSON metadata file:

```json
{
  "timestamp": "20260324_120000",
  "database_name": "rapids_orchestrator",
  "database_size_mb": 1024.5,
  "backup_file": "/backups/rapids_backup_20260324_120000.dump",
  "backup_size_mb": 256.2,
  "checksum": "abc123...",
  "duration_seconds": 45.2,
  "verified": true,
  "s3_uploaded": true,
  "s3_path": "s3://bucket/backups/20260324_120000/rapids_backup_20260324_120000.dump",
  "wal_start_lsn": "0/1234ABCD",
  "wal_end_lsn": "0/1234ABEF",
  "tables_count": 14,
  "rows_count": 125430
}
```

## Point-in-Time Recovery (PITR)

### Setup WAL Archiving

Configure PostgreSQL for WAL archiving in `postgresql.conf`:

```conf
# Enable WAL archiving
wal_level = replica
archive_mode = on
archive_command = 'test ! -f /wal_archive/%f && cp %p /wal_archive/%f'
max_wal_senders = 3
```

### Restore to Point in Time

```bash
# Restore to specific timestamp
python restore.py --point-in-time "2026-03-24 12:30:00"

# Restore to specific LSN
python restore.py --recovery-target-lsn "0/1234ABCD"
```

## Retention Policy

Backups are automatically cleaned up based on retention policy:

- **Local backups**: Configurable via `--retention-days` (default: 30 days)
- **S3 backups**: Same retention policy applied
- **Pre-restore backups**: Kept for 7 days in separate directory

## Troubleshooting

### Backup Fails with "pg_dump: command not found"

Ensure PostgreSQL client tools are installed:

```bash
# Check pg_dump availability
which pg_dump

# Install on macOS
brew install postgresql@16

# Install on Ubuntu
apt-get install postgresql-client-16
```

### S3 Upload Fails

Check AWS credentials:

```bash
# Test AWS CLI
aws s3 ls s3://your-bucket/

# Verify credentials
echo $AWS_ACCESS_KEY_ID
echo $AWS_SECRET_ACCESS_KEY
```

### Restore Fails with Permission Error

Ensure database user has sufficient privileges:

```sql
-- Grant restore permissions
GRANT CREATE ON DATABASE rapids_orchestrator TO rapids_user;
ALTER USER rapids_user CREATEDB;
```

### Verification Fails

Check backup file integrity:

```bash
# Manual verification
pg_restore --list /path/to/backup.dump

# Check file size
ls -lh /path/to/backup.dump

# Verify checksum
sha256sum /path/to/backup.dump
```

## Best Practices

1. **Test Restores Regularly**
   ```bash
   # Monthly restore test to staging environment
   python restore.py --latest --dry-run
   ```

2. **Monitor Backup Success**
   - Set up Prometheus alerts for failed backups
   - Review backup logs weekly

3. **Verify S3 Uploads**
   ```bash
   python verify.py --all --s3-check
   ```

4. **Keep Multiple Backup Locations**
   - Local backups for fast recovery
   - S3 backups for disaster recovery

5. **Document Recovery Procedures**
   - Maintain runbook for emergency restores
   - Test procedures quarterly

## Security Considerations

- Backups contain sensitive data - encrypt at rest and in transit
- S3 buckets should have encryption enabled
- Restrict access to backup files using IAM policies
- Use separate AWS credentials for backups
- Rotate credentials regularly
- Enable S3 versioning for backup files

## Performance Tuning

### Backup Performance

```bash
# Use parallel workers (PostgreSQL 13+)
pg_dump --jobs=4 ...

# Adjust compression level
pg_dump --compress=6 ...  # Faster, larger files
pg_dump --compress=9 ...  # Slower, smaller files
```

### Restore Performance

```bash
# Use parallel restore
pg_restore --jobs=4 ...

# Disable triggers during restore
pg_restore --disable-triggers ...
```

## License

Copyright © 2026 RAPIDS Meta-Orchestrator Team
