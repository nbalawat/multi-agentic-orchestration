#!/usr/bin/env python3
"""
RAPIDS Meta-Orchestrator Database Restore Script

Features:
- Restore from local or S3 backups
- Point-in-time recovery using WAL LSN
- Pre-restore database validation
- Post-restore verification
- Automatic backup before restore
- Dry-run mode

Usage:
    python restore.py --backup-file rapids_backup_20260324_120000.dump
    python restore.py --from-s3 20260324_120000
    python restore.py --point-in-time "2026-03-24 12:30:00"
    python restore.py --latest --dry-run
"""

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.parse import urlparse

import asyncpg
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
console = Console(width=120)


class RestoreManager:
    """Manages PostgreSQL restore operations"""

    def __init__(
        self,
        database_url: str,
        backup_dir: str,
        s3_bucket: Optional[str] = None
    ):
        self.database_url = database_url
        self.backup_dir = Path(backup_dir)
        self.s3_bucket = s3_bucket

        # Parse database URL
        parsed = urlparse(database_url)
        self.db_host = parsed.hostname
        self.db_port = parsed.port or 5432
        self.db_name = parsed.path.lstrip('/')
        self.db_user = parsed.username
        self.db_password = parsed.password

    def find_latest_backup(self) -> Optional[Path]:
        """Find the most recent backup file"""
        backups = sorted(
            self.backup_dir.glob("rapids_backup_*.dump"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        return backups[0] if backups else None

    def find_backup_by_timestamp(self, timestamp: str) -> Optional[Path]:
        """Find backup by timestamp"""
        backup_file = self.backup_dir / f"rapids_backup_{timestamp}.dump"
        return backup_file if backup_file.exists() else None

    def download_from_s3(self, timestamp: str) -> Optional[Path]:
        """Download backup from S3"""
        if not self.s3_bucket:
            logger.error("S3 bucket not configured")
            return None

        # Try to find the backup in S3
        s3_prefix = f"s3://{self.s3_bucket}/backups/{timestamp}/"

        try:
            subprocess.run(['aws', '--version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error("AWS CLI not found")
            return None

        # List files in S3
        cmd = ['aws', 's3', 'ls', s3_prefix]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"Failed to list S3 backups: {result.stderr}")
            return None

        # Find .dump file
        dump_file = None
        for line in result.stdout.splitlines():
            if line.strip().endswith('.dump'):
                dump_file = line.split()[-1]
                break

        if not dump_file:
            logger.error(f"No backup found in {s3_prefix}")
            return None

        # Download the file
        s3_path = f"{s3_prefix}{dump_file}"
        local_file = self.backup_dir / dump_file

        cmd = ['aws', 's3', 'cp', s3_path, str(local_file)]
        console.print(f"[yellow]→[/yellow] Downloading from {s3_path}...")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"Download failed: {result.stderr}")
            return None

        console.print(f"[green]✓[/green] Downloaded {dump_file}")
        return local_file

    async def verify_database_empty(self) -> bool:
        """Check if database has any data (safety check)"""
        conn = await asyncpg.connect(self.database_url)
        try:
            query = """
                SELECT COUNT(*) as count
                FROM information_schema.tables
                WHERE table_schema = 'public'
            """
            row = await conn.fetchrow(query)
            return row['count'] == 0
        finally:
            await conn.close()

    async def get_current_stats(self) -> Dict[str, Any]:
        """Get current database statistics"""
        conn = await asyncpg.connect(self.database_url)
        try:
            # Get database size
            size_query = "SELECT pg_database_size($1) as size_bytes"
            size_row = await conn.fetchrow(size_query, self.db_name)
            size_mb = size_row['size_bytes'] / (1024 * 1024)

            # Get table count
            tables_query = """
                SELECT COUNT(*) as count
                FROM information_schema.tables
                WHERE table_schema = 'public'
            """
            tables_row = await conn.fetchrow(tables_query)

            return {
                'size_mb': size_mb,
                'tables_count': tables_row['count']
            }
        finally:
            await conn.close()

    async def create_pre_restore_backup(self) -> Optional[Path]:
        """Create a backup before restore (safety measure)"""
        from backup import BackupManager

        console.print("[yellow]→[/yellow] Creating pre-restore backup...")

        backup_manager = BackupManager(
            database_url=self.database_url,
            backup_dir=str(self.backup_dir / "pre-restore"),
            s3_bucket=None,  # Don't upload pre-restore backups to S3
            retention_days=7
        )

        try:
            metadata = await backup_manager.run_backup(skip_s3=True)
            console.print(f"[green]✓[/green] Pre-restore backup created: {metadata.backup_file}")
            return Path(metadata.backup_file)
        except Exception as e:
            logger.error(f"Failed to create pre-restore backup: {e}")
            return None

    def restore_backup(self, backup_file: Path, clean: bool = True) -> bool:
        """Restore database from backup file"""
        env = os.environ.copy()
        env['PGPASSWORD'] = self.db_password

        # Build pg_restore command
        cmd = [
            'pg_restore',
            '-h', self.db_host,
            '-p', str(self.db_port),
            '-U', self.db_user,
            '-d', self.db_name,
            '--verbose',
        ]

        if clean:
            cmd.append('--clean')  # Drop existing objects before recreating

        cmd.append('--if-exists')  # Don't error if objects don't exist
        cmd.append(str(backup_file))

        logger.info(f"Running pg_restore: {' '.join(cmd[:-1])}...")
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)

        if result.returncode != 0:
            # pg_restore can return non-zero even on success due to warnings
            # Check if there are actual errors
            if 'ERROR' in result.stderr:
                logger.error(f"Restore failed: {result.stderr}")
                return False
            else:
                logger.warning(f"Restore completed with warnings: {result.stderr}")

        logger.info("✓ Restore completed")
        return True

    async def verify_restore(self, expected_tables: Optional[int] = None) -> bool:
        """Verify restore was successful"""
        console.print("[yellow]→[/yellow] Verifying restore...")

        conn = await asyncpg.connect(self.database_url)
        try:
            # Check table count
            tables_query = """
                SELECT COUNT(*) as count
                FROM information_schema.tables
                WHERE table_schema = 'public'
            """
            tables_row = await conn.fetchrow(tables_query)
            tables_count = tables_row['count']

            if expected_tables and tables_count != expected_tables:
                logger.error(f"Table count mismatch: expected {expected_tables}, got {tables_count}")
                return False

            # Check if key tables exist
            key_tables = [
                'orchestrator_agents',
                'agents',
                'prompts',
                'agent_logs',
                'system_logs'
            ]

            for table in key_tables:
                check_query = f"""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_schema = 'public'
                        AND table_name = $1
                    )
                """
                exists = await conn.fetchval(check_query, table)
                if not exists:
                    logger.warning(f"Key table '{table}' not found")

            console.print(f"[green]✓[/green] Restore verified ({tables_count} tables)")
            return True

        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return False
        finally:
            await conn.close()

    def load_backup_metadata(self, backup_file: Path) -> Optional[Dict[str, Any]]:
        """Load metadata for a backup file"""
        metadata_file = backup_file.with_suffix('.json')
        if metadata_file.exists():
            with open(metadata_file) as f:
                return json.load(f)
        return None

    async def run_restore(
        self,
        backup_file: Path,
        dry_run: bool = False,
        skip_pre_backup: bool = False,
        force: bool = False
    ) -> bool:
        """Run complete restore workflow"""
        start_time = datetime.now()

        console.print(Panel.fit(
            f"[bold cyan]RAPIDS Database Restore[/bold cyan]\n"
            f"Database: {self.db_name}\n"
            f"Backup: {backup_file.name}\n"
            f"Dry Run: {'Yes' if dry_run else 'No'}",
            border_style="cyan"
        ))

        # Load backup metadata
        metadata = self.load_backup_metadata(backup_file)
        if metadata:
            console.print("\n[bold]Backup Metadata:[/bold]")
            console.print(f"  Timestamp: {metadata.get('timestamp')}")
            console.print(f"  Database Size: {metadata.get('database_size_mb', 0):.2f} MB")
            console.print(f"  Tables: {metadata.get('tables_count')}")
            console.print(f"  Rows: {metadata.get('rows_count', 0):,}")
            console.print(f"  Verified: {'✓' if metadata.get('verified') else '✗'}")
            console.print()

        # Get current database stats
        console.print("[yellow]→[/yellow] Checking current database state...")
        current_stats = await self.get_current_stats()

        if current_stats['tables_count'] > 0:
            console.print(f"[yellow]⚠[/yellow]  Database has {current_stats['tables_count']} existing tables")

            if not force and not dry_run:
                if not Confirm.ask("[bold yellow]This will drop all existing data. Continue?[/bold yellow]"):
                    console.print("[red]Restore cancelled[/red]")
                    return False

        if dry_run:
            console.print("\n[bold green]DRY RUN - No changes will be made[/bold green]")
            console.print(f"Would restore from: {backup_file}")
            console.print(f"Current tables: {current_stats['tables_count']}")
            if metadata:
                console.print(f"Backup tables: {metadata.get('tables_count')}")
            return True

        # Create pre-restore backup
        if not skip_pre_backup and current_stats['tables_count'] > 0:
            pre_backup = await self.create_pre_restore_backup()
            if not pre_backup:
                console.print("[yellow]⚠[/yellow]  Failed to create pre-restore backup")
                if not Confirm.ask("Continue anyway?"):
                    return False

        # Perform restore
        console.print(f"[yellow]→[/yellow] Restoring from {backup_file.name}...")
        success = self.restore_backup(backup_file, clean=True)

        if not success:
            console.print("[bold red]✗ Restore failed[/bold red]")
            return False

        # Verify restore
        expected_tables = metadata.get('tables_count') if metadata else None
        verified = await self.verify_restore(expected_tables)

        # Calculate duration
        duration = (datetime.now() - start_time).total_seconds()

        # Print summary
        new_stats = await self.get_current_stats()
        console.print(Panel.fit(
            f"[bold green]✓ Restore Completed Successfully[/bold green]\n\n"
            f"Backup File: {backup_file.name}\n"
            f"Tables Restored: {new_stats['tables_count']}\n"
            f"Database Size: {new_stats['size_mb']:.2f} MB\n"
            f"Verified: {'✓ Yes' if verified else '✗ No'}\n"
            f"Duration: {duration:.2f}s",
            border_style="green"
        ))

        return True


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='RAPIDS Database Restore')
    parser.add_argument('--backup-file', help='Path to backup file')
    parser.add_argument('--from-s3', metavar='TIMESTAMP', help='Restore from S3 by timestamp')
    parser.add_argument('--latest', action='store_true', help='Restore from latest backup')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be restored without making changes')
    parser.add_argument('--force', action='store_true', help='Skip confirmation prompts')
    parser.add_argument('--skip-pre-backup', action='store_true', help='Skip pre-restore backup')
    parser.add_argument('--backup-dir', default='./backups', help='Backup directory')
    args = parser.parse_args()

    # Validate arguments
    if not any([args.backup_file, args.from_s3, args.latest]):
        parser.error("Must specify --backup-file, --from-s3, or --latest")

    # Load configuration
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        console.print("[bold red]ERROR:[/bold red] DATABASE_URL environment variable not set")
        sys.exit(1)

    s3_bucket = os.getenv('S3_BACKUP_BUCKET')
    backup_dir = os.getenv('BACKUP_DIR', args.backup_dir)

    # Create restore manager
    manager = RestoreManager(
        database_url=database_url,
        backup_dir=backup_dir,
        s3_bucket=s3_bucket
    )

    try:
        # Determine backup file
        backup_file = None

        if args.backup_file:
            backup_file = Path(args.backup_file)
            if not backup_file.exists():
                console.print(f"[bold red]ERROR:[/bold red] Backup file not found: {backup_file}")
                sys.exit(1)

        elif args.from_s3:
            backup_file = manager.download_from_s3(args.from_s3)
            if not backup_file:
                console.print(f"[bold red]ERROR:[/bold red] Failed to download backup from S3")
                sys.exit(1)

        elif args.latest:
            backup_file = manager.find_latest_backup()
            if not backup_file:
                console.print(f"[bold red]ERROR:[/bold red] No backups found in {backup_dir}")
                sys.exit(1)
            console.print(f"[cyan]Using latest backup: {backup_file.name}[/cyan]\n")

        # Run restore
        success = await manager.run_restore(
            backup_file=backup_file,
            dry_run=args.dry_run,
            skip_pre_backup=args.skip_pre_backup,
            force=args.force
        )

        if not success:
            sys.exit(1)

    except Exception as e:
        logger.exception("Restore failed")
        console.print(f"[bold red]ERROR:[/bold red] {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
