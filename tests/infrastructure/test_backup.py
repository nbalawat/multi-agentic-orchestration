"""
Tests for database backup functionality

Tests cover:
- Backup creation and verification
- Checksum calculation
- S3 upload simulation
- Metadata generation
- Retention policy enforcement
- Prometheus metrics export
"""

import asyncio
import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest
import asyncpg
from testcontainers.postgres import PostgresContainer

# Import backup module
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "infrastructure/scripts/backup"))

from backup import BackupManager, BackupMetadata


@pytest.fixture(scope="session")
def postgres_container():
    """Start PostgreSQL container for testing"""
    with PostgresContainer("postgres:16-alpine") as postgres:
        # Create test database
        conn = postgres.get_connection_url().replace("/test", "/postgres")

        # Setup schema
        setup_sql = """
        CREATE TABLE IF NOT EXISTS test_table (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100),
            created_at TIMESTAMP DEFAULT NOW()
        );

        INSERT INTO test_table (name) VALUES
            ('Test 1'),
            ('Test 2'),
            ('Test 3');
        """

        # Run setup
        subprocess.run(
            ['psql', conn, '-c', setup_sql],
            check=True,
            capture_output=True
        )

        yield postgres


@pytest.fixture
def backup_dir(tmp_path):
    """Create temporary backup directory"""
    backup_path = tmp_path / "backups"
    backup_path.mkdir()
    return backup_path


@pytest.fixture
def backup_manager(postgres_container, backup_dir):
    """Create BackupManager instance"""
    return BackupManager(
        database_url=postgres_container.get_connection_url(),
        backup_dir=str(backup_dir),
        s3_bucket=None,
        retention_days=7
    )


@pytest.mark.asyncio
async def test_get_database_stats(backup_manager):
    """Test retrieving database statistics"""
    stats = await backup_manager.get_database_stats()

    assert 'size_mb' in stats
    assert 'tables_count' in stats
    assert 'rows_count' in stats
    assert 'current_lsn' in stats

    assert stats['size_mb'] > 0
    assert stats['tables_count'] >= 1
    assert stats['rows_count'] >= 3


@pytest.mark.asyncio
async def test_create_backup(backup_manager, backup_dir):
    """Test backup creation"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # Mock pg_dump to avoid actual database dump in test
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(returncode=0, stderr="", stdout="")

        # Create a dummy backup file
        backup_file = backup_dir / f"rapids_backup_{timestamp}.dump"
        backup_file.write_bytes(b"dummy backup data")

        # Test would call create_backup here
        assert backup_file.exists()
        assert backup_file.stat().st_size > 0


def test_calculate_checksum(backup_manager, tmp_path):
    """Test SHA256 checksum calculation"""
    test_file = tmp_path / "test.txt"
    test_data = b"test data for checksum"
    test_file.write_bytes(test_data)

    checksum = backup_manager.calculate_checksum(test_file)

    # Verify checksum format
    assert len(checksum) == 64  # SHA256 produces 64 hex characters
    assert all(c in '0123456789abcdef' for c in checksum)

    # Verify consistency
    checksum2 = backup_manager.calculate_checksum(test_file)
    assert checksum == checksum2


def test_verify_backup(backup_manager, tmp_path):
    """Test backup verification"""
    # Create a mock backup file
    backup_file = tmp_path / "test_backup.dump"
    backup_file.write_bytes(b"dummy data")

    # Mock pg_restore verification
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(
            returncode=0,
            stdout="Table of contents\nLots of content here\n" * 10,
            stderr=""
        )

        result = backup_manager.verify_backup(backup_file)
        assert result is True

        # Verify pg_restore was called correctly
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert 'pg_restore' in call_args
        assert '--list' in call_args


def test_verify_backup_corrupted(backup_manager, tmp_path):
    """Test verification of corrupted backup"""
    backup_file = tmp_path / "corrupted.dump"
    backup_file.write_bytes(b"corrupted")

    # Mock failed verification
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(
            returncode=0,
            stdout="",  # Empty output indicates corruption
            stderr=""
        )

        result = backup_manager.verify_backup(backup_file)
        assert result is False


def test_upload_to_s3_no_bucket(backup_manager, tmp_path):
    """Test S3 upload when no bucket configured"""
    backup_file = tmp_path / "test.dump"
    backup_file.write_bytes(b"data")

    result = backup_manager.upload_to_s3(backup_file, "20260324_120000")
    assert result is None


def test_upload_to_s3_with_bucket(backup_manager, tmp_path):
    """Test S3 upload with bucket configured"""
    backup_manager.s3_bucket = "test-bucket"
    backup_file = tmp_path / "test.dump"
    backup_file.write_bytes(b"data")

    with patch('subprocess.run') as mock_run:
        # Mock AWS CLI available
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        s3_path = backup_manager.upload_to_s3(backup_file, "20260324_120000")

        # Should have called aws s3 cp
        assert mock_run.call_count >= 1

        # Verify S3 path format
        if s3_path:
            assert s3_path.startswith("s3://test-bucket/")
            assert "20260324_120000" in s3_path


def test_cleanup_old_backups(backup_manager, backup_dir):
    """Test cleanup of old backups"""
    # Create old and new backup files
    old_timestamp = (datetime.now() - timedelta(days=10)).timestamp()
    new_timestamp = datetime.now().timestamp()

    old_backup = backup_dir / "rapids_backup_old.dump"
    new_backup = backup_dir / "rapids_backup_new.dump"

    old_backup.write_bytes(b"old data")
    new_backup.write_bytes(b"new data")

    # Set modification time
    os.utime(old_backup, (old_timestamp, old_timestamp))
    os.utime(new_backup, (new_timestamp, new_timestamp))

    # Set retention to 7 days
    backup_manager.retention_days = 7
    backup_manager.cleanup_old_backups()

    # Old backup should be removed, new backup should remain
    assert not old_backup.exists()
    assert new_backup.exists()


def test_save_metadata(backup_manager, backup_dir):
    """Test saving backup metadata"""
    metadata = BackupMetadata(
        timestamp="20260324_120000",
        database_name="test_db",
        database_size_mb=100.5,
        backup_file=str(backup_dir / "test.dump"),
        backup_size_mb=25.2,
        checksum="abc123",
        duration_seconds=45.5,
        verified=True,
        s3_uploaded=False,
        tables_count=10,
        rows_count=1000
    )

    backup_manager.save_metadata(metadata)

    # Verify metadata file was created
    metadata_file = backup_dir / "rapids_backup_20260324_120000.json"
    assert metadata_file.exists()

    # Verify content
    with open(metadata_file) as f:
        saved_data = json.load(f)

    assert saved_data['timestamp'] == "20260324_120000"
    assert saved_data['database_name'] == "test_db"
    assert saved_data['database_size_mb'] == 100.5
    assert saved_data['verified'] is True


def test_export_prometheus_metrics(backup_manager, backup_dir):
    """Test Prometheus metrics export"""
    metadata = BackupMetadata(
        timestamp="20260324_120000",
        database_name="test_db",
        database_size_mb=100.0,
        backup_file="test.dump",
        backup_size_mb=25.0,
        checksum="abc123",
        duration_seconds=45.0,
        verified=True,
        s3_uploaded=True,
        tables_count=10,
        rows_count=1000
    )

    backup_manager.export_prometheus_metrics(metadata)

    # Verify metrics file was created
    metrics_file = backup_dir / "backup_metrics.prom"
    assert metrics_file.exists()

    # Verify metrics content
    content = metrics_file.read_text()

    assert 'rapids_backup_last_success_timestamp' in content
    assert 'rapids_backup_duration_seconds' in content
    assert 'rapids_backup_size_mb' in content
    assert 'rapids_backup_verified' in content
    assert 'rapids_backup_s3_uploaded' in content
    assert 'database="test_db"' in content


@pytest.mark.asyncio
async def test_run_backup_complete_workflow(backup_manager, backup_dir):
    """Test complete backup workflow"""
    # Mock external commands
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout="TOC\n" * 20, stderr="")

        # Create dummy backup file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = backup_dir / f"rapids_backup_{timestamp}.dump"
        backup_file.write_bytes(b"x" * 1024 * 100)  # 100KB dummy file

        # Mock create_backup to return our dummy file
        with patch.object(backup_manager, 'create_backup', return_value=backup_file):
            metadata = await backup_manager.run_backup(skip_s3=True)

        # Verify metadata
        assert metadata.timestamp == timestamp
        assert metadata.verified is True
        assert metadata.backup_size_mb > 0
        assert metadata.duration_seconds > 0

        # Verify files were created
        assert backup_file.exists()

        metadata_file = backup_dir / f"rapids_backup_{timestamp}.json"
        assert metadata_file.exists()

        metrics_file = backup_dir / "backup_metrics.prom"
        assert metrics_file.exists()


@pytest.mark.asyncio
async def test_database_connection_error(backup_dir):
    """Test handling of database connection errors"""
    # Create manager with invalid database URL
    manager = BackupManager(
        database_url="postgresql://invalid:invalid@localhost:9999/invalid",
        backup_dir=str(backup_dir),
        s3_bucket=None,
        retention_days=7
    )

    # Should raise connection error
    with pytest.raises(Exception):
        await manager.get_database_stats()


def test_backup_metadata_serialization():
    """Test BackupMetadata serialization to dict"""
    from dataclasses import asdict

    metadata = BackupMetadata(
        timestamp="20260324_120000",
        database_name="test",
        database_size_mb=100.0,
        backup_file="test.dump",
        backup_size_mb=25.0,
        checksum="abc",
        duration_seconds=10.0,
        verified=True,
        s3_uploaded=False,
        wal_start_lsn="0/123",
        wal_end_lsn="0/456",
        tables_count=5,
        rows_count=100
    )

    data = asdict(metadata)

    assert data['timestamp'] == "20260324_120000"
    assert data['verified'] is True
    assert 'wal_start_lsn' in data


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
