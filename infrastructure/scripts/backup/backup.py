#!/usr/bin/env python3
"""
RAPIDS Meta-Orchestrator Database Backup Script

Features:
- PostgreSQL pg_dump with custom format
- Automatic verification of backup integrity
- S3 upload with encryption
- Prometheus metrics export
- Point-in-time recovery support via WAL archiving
- Retention policy enforcement
- Monitoring integration

Usage:
    python backup.py [--verify-only] [--skip-s3] [--retention-days DAYS]
"""

import argparse
import asyncio
import gzip
import hashlib
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.parse import urlparse

import asyncpg
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
console = Console(width=120)


@dataclass
class BackupMetadata:
    """Metadata for backup files"""
    timestamp: str
    database_name: str
    database_size_mb: float
    backup_file: str
    backup_size_mb: float
    checksum: str
    duration_seconds: float
    verified: bool
    s3_uploaded: bool
    s3_path: Optional[str] = None
    wal_start_lsn: Optional[str] = None
    wal_end_lsn: Optional[str] = None
    tables_count: int = 0
    rows_count: int = 0


class BackupManager:
    """Manages PostgreSQL backup operations"""

    def __init__(
        self,
        database_url: str,
        backup_dir: str,
        s3_bucket: Optional[str] = None,
        retention_days: int = 30
    ):
        self.database_url = database_url
        self.backup_dir = Path(backup_dir)
        self.s3_bucket = s3_bucket
        self.retention_days = retention_days
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # Parse database URL
        parsed = urlparse(database_url)
        self.db_host = parsed.hostname
        self.db_port = parsed.port or 5432
        self.db_name = parsed.path.lstrip('/')
        self.db_user = parsed.username
        self.db_password = parsed.password

    async def get_database_stats(self) -> Dict[str, Any]:
        """Get database statistics before backup"""
        conn = await asyncpg.connect(self.database_url)
        try:
            # Get database size
            size_query = """
                SELECT pg_database_size($1) as size_bytes
            """
            size_row = await conn.fetchrow(size_query, self.db_name)
            size_mb = size_row['size_bytes'] / (1024 * 1024)

            # Get table count
            tables_query = """
                SELECT COUNT(*) as count
                FROM information_schema.tables
                WHERE table_schema = 'public'
            """
            tables_row = await conn.fetchrow(tables_query)
            tables_count = tables_row['count']

            # Get approximate row count
            rows_query = """
                SELECT SUM(n_live_tup) as total_rows
                FROM pg_stat_user_tables
            """
            rows_row = await conn.fetchrow(rows_query)
            rows_count = rows_row['total_rows'] or 0

            # Get current WAL LSN for point-in-time recovery
            lsn_query = "SELECT pg_current_wal_lsn() as lsn"
            lsn_row = await conn.fetchrow(lsn_query)
            current_lsn = str(lsn_row['lsn'])

            return {
                'size_mb': size_mb,
                'tables_count': tables_count,
                'rows_count': rows_count,
                'current_lsn': current_lsn
            }
        finally:
            await conn.close()

    def create_backup(self, timestamp: str) -> Path:
        """Create PostgreSQL backup using pg_dump"""
        backup_file = self.backup_dir / f"rapids_backup_{timestamp}.dump"

        # Set password for pg_dump
        env = os.environ.copy()
        env['PGPASSWORD'] = self.db_password

        # pg_dump command with custom format for best compression and features
        cmd = [
            'pg_dump',
            '-h', self.db_host,
            '-p', str(self.db_port),
            '-U', self.db_user,
            '-d', self.db_name,
            '--format=custom',
            '--compress=9',
            '--verbose',
            '--file', str(backup_file)
        ]

        logger.info(f"Running pg_dump: {' '.join(cmd[:-2])}...")
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"pg_dump failed: {result.stderr}")
            raise RuntimeError(f"Backup failed: {result.stderr}")

        logger.info(f"Backup created: {backup_file} ({backup_file.stat().st_size / 1024 / 1024:.2f} MB)")
        return backup_file

    def verify_backup(self, backup_file: Path) -> bool:
        """Verify backup integrity using pg_restore --list"""
        env = os.environ.copy()
        env['PGPASSWORD'] = self.db_password

        cmd = [
            'pg_restore',
            '--list',
            str(backup_file)
        ]

        logger.info(f"Verifying backup integrity...")
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"Backup verification failed: {result.stderr}")
            return False

        # Check that we have table of contents
        if not result.stdout or len(result.stdout) < 100:
            logger.error("Backup file appears to be empty or corrupted")
            return False

        logger.info("✓ Backup verification passed")
        return True

    def calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of backup file"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def upload_to_s3(self, backup_file: Path, timestamp: str) -> Optional[str]:
        """Upload backup to S3 with server-side encryption"""
        if not self.s3_bucket:
            logger.info("S3 bucket not configured, skipping upload")
            return None

        s3_key = f"backups/{timestamp}/{backup_file.name}"
        s3_path = f"s3://{self.s3_bucket}/{s3_key}"

        # Check if AWS CLI is available
        try:
            subprocess.run(['aws', '--version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("AWS CLI not found, skipping S3 upload")
            return None

        cmd = [
            'aws', 's3', 'cp',
            str(backup_file),
            s3_path,
            '--server-side-encryption', 'AES256',
            '--storage-class', 'STANDARD_IA'
        ]

        logger.info(f"Uploading to {s3_path}...")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"S3 upload failed: {result.stderr}")
            return None

        logger.info(f"✓ Uploaded to {s3_path}")
        return s3_path

    def cleanup_old_backups(self):
        """Remove local backups older than retention period"""
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        removed_count = 0

        for backup_file in self.backup_dir.glob("rapids_backup_*.dump"):
            if backup_file.stat().st_mtime < cutoff_date.timestamp():
                logger.info(f"Removing old backup: {backup_file.name}")
                backup_file.unlink()
                # Also remove metadata file
                metadata_file = backup_file.with_suffix('.json')
                if metadata_file.exists():
                    metadata_file.unlink()
                removed_count += 1

        if removed_count > 0:
            logger.info(f"✓ Removed {removed_count} old backup(s)")

    def cleanup_old_s3_backups(self):
        """Remove S3 backups older than retention period"""
        if not self.s3_bucket:
            return

        try:
            subprocess.run(['aws', '--version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("AWS CLI not found, skipping S3 cleanup")
            return

        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        cutoff_str = cutoff_date.strftime('%Y%m%d')

        # List all backups in S3
        cmd = ['aws', 's3', 'ls', f"s3://{self.s3_bucket}/backups/", '--recursive']
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"Failed to list S3 backups: {result.stderr}")
            return

        removed_count = 0
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 4:
                # Extract timestamp from path (format: backups/YYYYMMDD_HHMMSS/...)
                s3_key = parts[3]
                try:
                    timestamp_str = s3_key.split('/')[1].split('_')[0]
                    if timestamp_str < cutoff_str:
                        delete_cmd = ['aws', 's3', 'rm', f"s3://{self.s3_bucket}/{s3_key}"]
                        subprocess.run(delete_cmd, capture_output=True)
                        logger.info(f"Removed old S3 backup: {s3_key}")
                        removed_count += 1
                except (IndexError, ValueError):
                    continue

        if removed_count > 0:
            logger.info(f"✓ Removed {removed_count} old S3 backup(s)")

    def save_metadata(self, metadata: BackupMetadata):
        """Save backup metadata to JSON file"""
        metadata_file = self.backup_dir / f"rapids_backup_{metadata.timestamp}.json"
        with open(metadata_file, 'w') as f:
            json.dump(asdict(metadata), f, indent=2)
        logger.info(f"Metadata saved: {metadata_file}")

    def export_prometheus_metrics(self, metadata: BackupMetadata):
        """Export backup metrics for Prometheus"""
        metrics_file = self.backup_dir / "backup_metrics.prom"

        metrics = f"""# HELP rapids_backup_last_success_timestamp Unix timestamp of last successful backup
# TYPE rapids_backup_last_success_timestamp gauge
rapids_backup_last_success_timestamp {{database="{metadata.database_name}"}} {datetime.now().timestamp()}

# HELP rapids_backup_duration_seconds Duration of backup operation
# TYPE rapids_backup_duration_seconds gauge
rapids_backup_duration_seconds {{database="{metadata.database_name}"}} {metadata.duration_seconds}

# HELP rapids_backup_size_mb Size of backup file in megabytes
# TYPE rapids_backup_size_mb gauge
rapids_backup_size_mb {{database="{metadata.database_name}"}} {metadata.backup_size_mb}

# HELP rapids_backup_database_size_mb Size of database in megabytes
# TYPE rapids_backup_database_size_mb gauge
rapids_backup_database_size_mb {{database="{metadata.database_name}"}} {metadata.database_size_mb}

# HELP rapids_backup_verified Backup verification status (1=verified, 0=not verified)
# TYPE rapids_backup_verified gauge
rapids_backup_verified {{database="{metadata.database_name}"}} {int(metadata.verified)}

# HELP rapids_backup_s3_uploaded S3 upload status (1=uploaded, 0=not uploaded)
# TYPE rapids_backup_s3_uploaded gauge
rapids_backup_s3_uploaded {{database="{metadata.database_name}"}} {int(metadata.s3_uploaded)}
"""

        with open(metrics_file, 'w') as f:
            f.write(metrics)
        logger.info(f"Prometheus metrics exported: {metrics_file}")

    async def run_backup(self, skip_s3: bool = False) -> BackupMetadata:
        """Run complete backup workflow"""
        start_time = datetime.now()
        timestamp = start_time.strftime('%Y%m%d_%H%M%S')

        console.print(Panel.fit(
            f"[bold cyan]RAPIDS Database Backup[/bold cyan]\n"
            f"Database: {self.db_name}\n"
            f"Timestamp: {timestamp}",
            border_style="cyan"
        ))

        # Get database stats
        console.print("[yellow]→[/yellow] Gathering database statistics...")
        stats = await self.get_database_stats()

        # Create backup
        console.print("[yellow]→[/yellow] Creating database backup...")
        backup_file = self.create_backup(timestamp)
        backup_size_mb = backup_file.stat().st_size / (1024 * 1024)

        # Calculate checksum
        console.print("[yellow]→[/yellow] Calculating checksum...")
        checksum = self.calculate_checksum(backup_file)

        # Verify backup
        console.print("[yellow]→[/yellow] Verifying backup integrity...")
        verified = self.verify_backup(backup_file)

        # Upload to S3
        s3_path = None
        s3_uploaded = False
        if not skip_s3:
            console.print("[yellow]→[/yellow] Uploading to S3...")
            s3_path = self.upload_to_s3(backup_file, timestamp)
            s3_uploaded = s3_path is not None

        # Get ending LSN
        end_stats = await self.get_database_stats()

        # Calculate duration
        duration = (datetime.now() - start_time).total_seconds()

        # Create metadata
        metadata = BackupMetadata(
            timestamp=timestamp,
            database_name=self.db_name,
            database_size_mb=stats['size_mb'],
            backup_file=str(backup_file),
            backup_size_mb=backup_size_mb,
            checksum=checksum,
            duration_seconds=duration,
            verified=verified,
            s3_uploaded=s3_uploaded,
            s3_path=s3_path,
            wal_start_lsn=stats['current_lsn'],
            wal_end_lsn=end_stats['current_lsn'],
            tables_count=stats['tables_count'],
            rows_count=stats['rows_count']
        )

        # Save metadata
        self.save_metadata(metadata)

        # Export Prometheus metrics
        self.export_prometheus_metrics(metadata)

        # Cleanup old backups
        console.print("[yellow]→[/yellow] Cleaning up old backups...")
        self.cleanup_old_backups()
        if not skip_s3:
            self.cleanup_old_s3_backups()

        # Print summary
        console.print(Panel.fit(
            f"[bold green]✓ Backup Completed Successfully[/bold green]\n\n"
            f"Backup File: {backup_file.name}\n"
            f"Database Size: {stats['size_mb']:.2f} MB\n"
            f"Backup Size: {backup_size_mb:.2f} MB\n"
            f"Compression: {(1 - backup_size_mb / stats['size_mb']) * 100:.1f}%\n"
            f"Tables: {stats['tables_count']}\n"
            f"Rows: {stats['rows_count']:,}\n"
            f"Checksum: {checksum[:16]}...\n"
            f"Verified: {'✓ Yes' if verified else '✗ No'}\n"
            f"S3 Upload: {'✓ Yes' if s3_uploaded else '✗ No'}\n"
            f"Duration: {duration:.2f}s\n"
            f"WAL LSN Range: {stats['current_lsn']} → {end_stats['current_lsn']}",
            border_style="green"
        ))

        return metadata


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='RAPIDS Database Backup')
    parser.add_argument('--verify-only', action='store_true', help='Only verify existing backups')
    parser.add_argument('--skip-s3', action='store_true', help='Skip S3 upload')
    parser.add_argument('--retention-days', type=int, default=30, help='Backup retention in days')
    parser.add_argument('--backup-dir', default='./backups', help='Backup directory')
    args = parser.parse_args()

    # Load configuration from environment
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        console.print("[bold red]ERROR:[/bold red] DATABASE_URL environment variable not set")
        sys.exit(1)

    s3_bucket = os.getenv('S3_BACKUP_BUCKET')
    backup_dir = os.getenv('BACKUP_DIR', args.backup_dir)

    # Create backup manager
    manager = BackupManager(
        database_url=database_url,
        backup_dir=backup_dir,
        s3_bucket=s3_bucket,
        retention_days=args.retention_days
    )

    try:
        if args.verify_only:
            # Verify all backups
            for backup_file in manager.backup_dir.glob("rapids_backup_*.dump"):
                console.print(f"\n[cyan]Verifying {backup_file.name}...[/cyan]")
                verified = manager.verify_backup(backup_file)
                if verified:
                    console.print(f"[green]✓ {backup_file.name} verified[/green]")
                else:
                    console.print(f"[red]✗ {backup_file.name} verification failed[/red]")
        else:
            # Run backup
            await manager.run_backup(skip_s3=args.skip_s3)

    except Exception as e:
        logger.exception("Backup failed")
        console.print(f"[bold red]ERROR:[/bold red] {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
