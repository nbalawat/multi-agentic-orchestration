"""
Tests for database restore functionality

Tests cover:
- Finding backups (latest, by timestamp)
- S3 download simulation
- Pre-restore validation
- Restore execution
- Post-restore verification
- Dry-run mode
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
import pytest
from testcontainers.postgres import PostgresContainer

# Import restore module
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "infrastructure/scripts/backup"))

from restore import RestoreManager


@pytest.fixture(scope="session")
def postgres_container():
    """Start PostgreSQL container for testing"""
    with PostgresContainer("postgres:16-alpine") as postgres:
        yield postgres


@pytest.fixture
def backup_dir(tmp_path):
    """Create temporary backup directory"""
    backup_path = tmp_path / "backups"
    backup_path.mkdir()
    return backup_path


@pytest.fixture
def restore_manager(postgres_container, backup_dir):
    """Create RestoreManager instance"""
    return RestoreManager(
        database_url=postgres_container.get_connection_url(),
        backup_dir=str(backup_dir),
        s3_bucket=None
    )


def test_find_latest_backup(restore_manager, backup_dir):
    """Test finding the latest backup file"""
    # Create multiple backup files with different timestamps
    old_backup = backup_dir / "rapids_backup_20260320_120000.dump"
    mid_backup = backup_dir / "rapids_backup_20260322_120000.dump"
    new_backup = backup_dir / "rapids_backup_20260324_120000.dump"

    old_backup.write_bytes(b"old")
    mid_backup.write_bytes(b"mid")
    new_backup.write_bytes(b"new")

    # Find latest
    latest = restore_manager.find_latest_backup()

    assert latest is not None
    assert latest.name == "rapids_backup_20260324_120000.dump"


def test_find_latest_backup_empty(restore_manager, backup_dir):
    """Test finding latest backup when none exist"""
    latest = restore_manager.find_latest_backup()
    assert latest is None


def test_find_backup_by_timestamp(restore_manager, backup_dir):
    """Test finding backup by specific timestamp"""
    timestamp = "20260324_120000"
    backup_file = backup_dir / f"rapids_backup_{timestamp}.dump"
    backup_file.write_bytes(b"test data")

    found = restore_manager.find_backup_by_timestamp(timestamp)

    assert found is not None
    assert found.exists()
    assert found.name == f"rapids_backup_{timestamp}.dump"


def test_find_backup_by_timestamp_not_found(restore_manager, backup_dir):
    """Test finding non-existent backup"""
    found = restore_manager.find_backup_by_timestamp("20260101_000000")
    assert found is None


def test_download_from_s3_no_bucket(restore_manager):
    """Test S3 download when no bucket configured"""
    result = restore_manager.download_from_s3("20260324_120000")
    assert result is None


def test_download_from_s3_with_bucket(restore_manager, backup_dir):
    """Test S3 download with bucket configured"""
    restore_manager.s3_bucket = "test-bucket"

    with patch('subprocess.run') as mock_run:
        # Mock AWS CLI available check
        mock_run.side_effect = [
            Mock(returncode=0, stdout="", stderr=""),  # aws --version
            Mock(returncode=0, stdout="rapids_backup_20260324_120000.dump\n", stderr=""),  # aws s3 ls
            Mock(returncode=0, stdout="", stderr="")   # aws s3 cp
        ]

        # Mock file creation
        expected_file = backup_dir / "rapids_backup_20260324_120000.dump"
        expected_file.write_bytes(b"downloaded data")

        result = restore_manager.download_from_s3("20260324_120000")

        # Verify S3 commands were called
        assert mock_run.call_count >= 2


@pytest.mark.asyncio
async def test_verify_database_empty(restore_manager):
    """Test checking if database is empty"""
    # Create a test table first
    import asyncpg
    conn = await asyncpg.connect(restore_manager.database_url)
    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS test_table (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100)
            )
        """)

        # Should return False because table exists
        is_empty = await restore_manager.verify_database_empty()
        assert is_empty is False

        # Clean up
        await conn.execute("DROP TABLE test_table")

        # Now should be empty
        is_empty = await restore_manager.verify_database_empty()
        assert is_empty is True

    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_get_current_stats(restore_manager):
    """Test retrieving current database statistics"""
    stats = await restore_manager.get_current_stats()

    assert 'size_mb' in stats
    assert 'tables_count' in stats
    assert stats['size_mb'] >= 0
    assert stats['tables_count'] >= 0


def test_restore_backup(restore_manager, backup_dir):
    """Test restore execution"""
    backup_file = backup_dir / "test_backup.dump"
    backup_file.write_bytes(b"backup data")

    # Mock pg_restore
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        result = restore_manager.restore_backup(backup_file, clean=True)

        assert result is True

        # Verify pg_restore was called
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert 'pg_restore' in call_args
        assert '--clean' in call_args
        assert str(backup_file) in call_args


def test_restore_backup_with_errors(restore_manager, backup_dir):
    """Test restore with errors"""
    backup_file = backup_dir / "test_backup.dump"
    backup_file.write_bytes(b"backup data")

    # Mock pg_restore failure
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="ERROR: relation does not exist"
        )

        result = restore_manager.restore_backup(backup_file, clean=True)

        assert result is False


def test_restore_backup_with_warnings(restore_manager, backup_dir):
    """Test restore with warnings (should still succeed)"""
    backup_file = backup_dir / "test_backup.dump"
    backup_file.write_bytes(b"backup data")

    # Mock pg_restore with warnings but no errors
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="WARNING: some warning message\nINFO: additional info"
        )

        result = restore_manager.restore_backup(backup_file, clean=True)

        # Should succeed despite non-zero return code if no ERROR
        assert result is True


@pytest.mark.asyncio
async def test_verify_restore(restore_manager):
    """Test post-restore verification"""
    import asyncpg

    # Create some test tables
    conn = await asyncpg.connect(restore_manager.database_url)
    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS orchestrator_agents (
                id SERIAL PRIMARY KEY
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                id SERIAL PRIMARY KEY
            )
        """)

        # Verify restore
        result = await restore_manager.verify_restore(expected_tables=2)

        # Should pass with 2 tables
        assert result is True

        # Clean up
        await conn.execute("DROP TABLE orchestrator_agents")
        await conn.execute("DROP TABLE agents")

    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_verify_restore_table_mismatch(restore_manager):
    """Test verification with table count mismatch"""
    import asyncpg

    conn = await asyncpg.connect(restore_manager.database_url)
    try:
        await conn.execute("CREATE TABLE IF NOT EXISTS test_table (id SERIAL)")

        # Expect 5 tables but only have 1
        result = await restore_manager.verify_restore(expected_tables=5)

        assert result is False

        await conn.execute("DROP TABLE test_table")

    finally:
        await conn.close()


def test_load_backup_metadata(restore_manager, backup_dir):
    """Test loading backup metadata"""
    # Create backup file and metadata
    backup_file = backup_dir / "rapids_backup_20260324_120000.dump"
    metadata_file = backup_dir / "rapids_backup_20260324_120000.json"

    backup_file.write_bytes(b"data")

    metadata = {
        'timestamp': '20260324_120000',
        'database_name': 'test_db',
        'database_size_mb': 100.0,
        'tables_count': 10,
        'verified': True
    }

    with open(metadata_file, 'w') as f:
        json.dump(metadata, f)

    # Load metadata
    loaded = restore_manager.load_backup_metadata(backup_file)

    assert loaded is not None
    assert loaded['timestamp'] == '20260324_120000'
    assert loaded['database_size_mb'] == 100.0
    assert loaded['verified'] is True


def test_load_backup_metadata_missing(restore_manager, backup_dir):
    """Test loading metadata when file doesn't exist"""
    backup_file = backup_dir / "rapids_backup_20260324_120000.dump"
    backup_file.write_bytes(b"data")

    loaded = restore_manager.load_backup_metadata(backup_file)
    assert loaded is None


@pytest.mark.asyncio
async def test_run_restore_dry_run(restore_manager, backup_dir):
    """Test dry-run mode"""
    # Create backup file with metadata
    backup_file = backup_dir / "rapids_backup_20260324_120000.dump"
    metadata_file = backup_dir / "rapids_backup_20260324_120000.json"

    backup_file.write_bytes(b"data")
    metadata_file.write_text(json.dumps({
        'timestamp': '20260324_120000',
        'database_name': 'test',
        'database_size_mb': 10.0,
        'tables_count': 5,
        'verified': True
    }))

    # Run dry-run restore
    result = await restore_manager.run_restore(
        backup_file=backup_file,
        dry_run=True,
        skip_pre_backup=True,
        force=True
    )

    # Should succeed without making changes
    assert result is True


@pytest.mark.asyncio
async def test_run_restore_with_pre_backup(restore_manager, backup_dir):
    """Test restore with pre-restore backup creation"""
    backup_file = backup_dir / "rapids_backup_20260324_120000.dump"
    backup_file.write_bytes(b"x" * 1024)

    # Mock create_pre_restore_backup
    pre_backup_path = backup_dir / "pre-restore" / "backup.dump"
    pre_backup_path.parent.mkdir(parents=True, exist_ok=True)
    pre_backup_path.write_bytes(b"pre-backup")

    with patch.object(restore_manager, 'create_pre_restore_backup') as mock_pre_backup:
        mock_pre_backup.return_value = pre_backup_path

        # Mock restore operations
        with patch.object(restore_manager, 'restore_backup', return_value=True):
            with patch.object(restore_manager, 'verify_restore', return_value=True):
                result = await restore_manager.run_restore(
                    backup_file=backup_file,
                    skip_pre_backup=False,
                    force=True
                )

                # Verify pre-backup was called
                mock_pre_backup.assert_called_once()


@pytest.mark.asyncio
async def test_create_pre_restore_backup(restore_manager, backup_dir):
    """Test creating pre-restore backup"""
    # Mock BackupManager
    with patch('restore.BackupManager') as MockBackupManager:
        mock_manager = Mock()
        mock_metadata = Mock()
        mock_metadata.backup_file = str(backup_dir / "pre_backup.dump")
        mock_manager.run_backup = AsyncMock(return_value=mock_metadata)
        MockBackupManager.return_value = mock_manager

        result = await restore_manager.create_pre_restore_backup()

        # Should return backup path
        assert result == Path(mock_metadata.backup_file)


@pytest.mark.asyncio
async def test_run_restore_complete_workflow(restore_manager, backup_dir):
    """Test complete restore workflow"""
    # Create backup file
    backup_file = backup_dir / "rapids_backup_20260324_120000.dump"
    backup_file.write_bytes(b"backup data")

    # Mock all restore operations
    with patch.object(restore_manager, 'restore_backup', return_value=True):
        with patch.object(restore_manager, 'verify_restore', return_value=True):
            result = await restore_manager.run_restore(
                backup_file=backup_file,
                dry_run=False,
                skip_pre_backup=True,
                force=True
            )

            assert result is True


@pytest.mark.asyncio
async def test_run_restore_failure(restore_manager, backup_dir):
    """Test restore failure handling"""
    backup_file = backup_dir / "rapids_backup_20260324_120000.dump"
    backup_file.write_bytes(b"backup data")

    # Mock failed restore
    with patch.object(restore_manager, 'restore_backup', return_value=False):
        result = await restore_manager.run_restore(
            backup_file=backup_file,
            skip_pre_backup=True,
            force=True
        )

        assert result is False


def test_parse_database_url(postgres_container):
    """Test database URL parsing"""
    url = postgres_container.get_connection_url()
    manager = RestoreManager(database_url=url, backup_dir="/tmp/backups")

    assert manager.db_host is not None
    assert manager.db_port > 0
    assert manager.db_name is not None
    assert manager.db_user is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
