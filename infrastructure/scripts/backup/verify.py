#!/usr/bin/env python3
"""
RAPIDS Backup Verification Utility

Features:
- Verify backup file integrity
- Validate backup metadata
- Check S3 backup availability
- Generate verification reports
- Compare backup checksums

Usage:
    python verify.py --all
    python verify.py --backup-file rapids_backup_20260324_120000.dump
    python verify.py --s3-check
"""

import argparse
import asyncio
import json
import hashlib
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
console = Console(width=120)


@dataclass
class VerificationResult:
    """Result of backup verification"""
    backup_file: str
    timestamp: str
    file_exists: bool
    file_size_mb: float
    checksum_match: bool
    integrity_check: bool
    metadata_exists: bool
    s3_exists: bool = False
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    @property
    def passed(self) -> bool:
        """Overall verification status"""
        return (
            self.file_exists and
            self.integrity_check and
            self.checksum_match and
            len(self.errors) == 0
        )


class BackupVerifier:
    """Verify backup files and metadata"""

    def __init__(self, backup_dir: str, s3_bucket: Optional[str] = None):
        self.backup_dir = Path(backup_dir)
        self.s3_bucket = s3_bucket

    def calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def verify_integrity(self, backup_file: Path) -> bool:
        """Verify backup integrity using pg_restore --list"""
        cmd = ['pg_restore', '--list', str(backup_file)]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"Integrity check failed: {result.stderr}")
            return False

        if not result.stdout or len(result.stdout) < 100:
            logger.error("Backup file appears to be empty or corrupted")
            return False

        return True

    def check_s3_backup(self, timestamp: str) -> bool:
        """Check if backup exists in S3"""
        if not self.s3_bucket:
            return False

        try:
            subprocess.run(['aws', '--version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

        s3_prefix = f"s3://{self.s3_bucket}/backups/{timestamp}/"
        cmd = ['aws', 's3', 'ls', s3_prefix]
        result = subprocess.run(cmd, capture_output=True, text=True)

        return result.returncode == 0 and len(result.stdout) > 0

    def verify_backup(self, backup_file: Path) -> VerificationResult:
        """Verify a single backup file"""
        errors = []

        # Extract timestamp from filename
        timestamp = backup_file.stem.replace('rapids_backup_', '')

        # Check file exists
        file_exists = backup_file.exists()
        if not file_exists:
            errors.append("Backup file not found")

        # Get file size
        file_size_mb = backup_file.stat().st_size / (1024 * 1024) if file_exists else 0

        # Load metadata
        metadata_file = backup_file.with_suffix('.json')
        metadata_exists = metadata_file.exists()
        metadata = None

        if metadata_exists:
            with open(metadata_file) as f:
                metadata = json.load(f)
        else:
            errors.append("Metadata file not found")

        # Verify checksum
        checksum_match = False
        if file_exists and metadata:
            actual_checksum = self.calculate_checksum(backup_file)
            expected_checksum = metadata.get('checksum')
            checksum_match = actual_checksum == expected_checksum
            if not checksum_match:
                errors.append(f"Checksum mismatch: expected {expected_checksum[:16]}..., got {actual_checksum[:16]}...")

        # Verify integrity
        integrity_check = False
        if file_exists:
            try:
                integrity_check = self.verify_integrity(backup_file)
                if not integrity_check:
                    errors.append("Integrity check failed (pg_restore --list)")
            except Exception as e:
                errors.append(f"Integrity check error: {str(e)}")

        # Check S3
        s3_exists = self.check_s3_backup(timestamp)

        return VerificationResult(
            backup_file=backup_file.name,
            timestamp=timestamp,
            file_exists=file_exists,
            file_size_mb=file_size_mb,
            checksum_match=checksum_match,
            integrity_check=integrity_check,
            metadata_exists=metadata_exists,
            s3_exists=s3_exists,
            errors=errors
        )

    def verify_all_backups(self) -> List[VerificationResult]:
        """Verify all backups in directory"""
        results = []

        backup_files = sorted(
            self.backup_dir.glob("rapids_backup_*.dump"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        for backup_file in backup_files:
            console.print(f"[cyan]Verifying {backup_file.name}...[/cyan]")
            result = self.verify_backup(backup_file)
            results.append(result)

        return results

    def generate_report(self, results: List[VerificationResult]):
        """Generate verification report"""
        # Summary table
        table = Table(title="Backup Verification Report", show_header=True, header_style="bold cyan")
        table.add_column("Timestamp", style="cyan")
        table.add_column("Size (MB)", justify="right")
        table.add_column("File", justify="center")
        table.add_column("Integrity", justify="center")
        table.add_column("Checksum", justify="center")
        table.add_column("Metadata", justify="center")
        table.add_column("S3", justify="center")
        table.add_column("Status", justify="center")

        for result in results:
            def check_icon(value: bool) -> str:
                return "[green]✓[/green]" if value else "[red]✗[/red]"

            status = "[green]PASS[/green]" if result.passed else "[red]FAIL[/red]"

            table.add_row(
                result.timestamp,
                f"{result.file_size_mb:.2f}",
                check_icon(result.file_exists),
                check_icon(result.integrity_check),
                check_icon(result.checksum_match),
                check_icon(result.metadata_exists),
                check_icon(result.s3_exists),
                status
            )

        console.print(table)

        # Statistics
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed

        console.print(Panel.fit(
            f"[bold]Verification Summary[/bold]\n\n"
            f"Total Backups: {total}\n"
            f"[green]Passed: {passed}[/green]\n"
            f"[red]Failed: {failed}[/red]\n"
            f"Success Rate: {(passed / total * 100) if total > 0 else 0:.1f}%",
            border_style="cyan"
        ))

        # Show errors
        if failed > 0:
            console.print("\n[bold red]Errors Found:[/bold red]")
            for result in results:
                if not result.passed:
                    console.print(f"\n[yellow]{result.backup_file}:[/yellow]")
                    for error in result.errors:
                        console.print(f"  • {error}")

    def export_report_json(self, results: List[VerificationResult], output_file: str):
        """Export verification report as JSON"""
        report = {
            'generated_at': datetime.now().isoformat(),
            'total_backups': len(results),
            'passed': sum(1 for r in results if r.passed),
            'failed': sum(1 for r in results if not r.passed),
            'backups': [
                {
                    'backup_file': r.backup_file,
                    'timestamp': r.timestamp,
                    'file_exists': r.file_exists,
                    'file_size_mb': r.file_size_mb,
                    'checksum_match': r.checksum_match,
                    'integrity_check': r.integrity_check,
                    'metadata_exists': r.metadata_exists,
                    's3_exists': r.s3_exists,
                    'passed': r.passed,
                    'errors': r.errors
                }
                for r in results
            ]
        }

        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)

        console.print(f"[green]✓[/green] Report exported to {output_file}")


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='RAPIDS Backup Verification')
    parser.add_argument('--backup-file', help='Verify specific backup file')
    parser.add_argument('--all', action='store_true', help='Verify all backups')
    parser.add_argument('--s3-check', action='store_true', help='Include S3 availability check')
    parser.add_argument('--export-json', help='Export report as JSON')
    parser.add_argument('--backup-dir', default='./backups', help='Backup directory')
    args = parser.parse_args()

    # Load configuration
    backup_dir = os.getenv('BACKUP_DIR', args.backup_dir)
    s3_bucket = os.getenv('S3_BACKUP_BUCKET') if args.s3_check else None

    # Create verifier
    verifier = BackupVerifier(backup_dir=backup_dir, s3_bucket=s3_bucket)

    try:
        if args.backup_file:
            # Verify single backup
            backup_path = Path(args.backup_file)
            result = verifier.verify_backup(backup_path)
            verifier.generate_report([result])

            if not result.passed:
                sys.exit(1)

        elif args.all:
            # Verify all backups
            results = verifier.verify_all_backups()
            verifier.generate_report(results)

            if args.export_json:
                verifier.export_report_json(results, args.export_json)

            # Exit with error if any verification failed
            if any(not r.passed for r in results):
                sys.exit(1)

        else:
            parser.error("Must specify --backup-file or --all")

    except Exception as e:
        logger.exception("Verification failed")
        console.print(f"[bold red]ERROR:[/bold red] {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
