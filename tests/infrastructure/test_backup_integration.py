"""
Integration tests for backup and restore workflow

These tests verify the complete backup/restore cycle including:
- Backup creation with real database
- Verification
- Restore
- Data integrity validation
"""

import asyncio
import os
import subprocess
from pathlib import Path
import pytest
import asyncpg
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="module")
def postgres_container():
    """Start PostgreSQL container for integration testing"""
    with PostgresContainer("postgres:16-alpine") as postgres:
        # Setup test schema
        setup_sql = """
        -- Create test tables
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            email VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS projects (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            user_id INTEGER REFERENCES users(id),
            status VARCHAR(50),
            created_at TIMESTAMP DEFAULT NOW()
        );

        CREATE INDEX idx_users_username ON users(username);
        CREATE INDEX idx_projects_user_id ON projects(user_id);

        -- Insert test data
        INSERT INTO users (username, email) VALUES
            ('alice', 'alice@example.com'),
            ('bob', 'bob@example.com'),
            ('charlie', 'charlie@example.com');

        INSERT INTO projects (name, user_id, status) VALUES
            ('Project A', 1, 'active'),
            ('Project B', 1, 'completed'),
            ('Project C', 2, 'active'),
            ('Project D', 3, 'planning');
        """

        conn_url = postgres.get_connection_url()

        # Execute setup
        subprocess.run(
            ['psql', conn_url, '-c', setup_sql],
            check=True,
            capture_output=True,
            text=True
        )

        yield postgres


@pytest.fixture
def backup_dir(tmp_path):
    """Create temporary backup directory"""
    backup_path = tmp_path / "backups"
    backup_path.mkdir()
    return backup_path


@pytest.fixture
def env_vars(postgres_container, backup_dir):
    """Setup environment variables for backup scripts"""
    env = os.environ.copy()
    env['DATABASE_URL'] = postgres_container.get_connection_url()
    env['BACKUP_DIR'] = str(backup_dir)
    env['PYTHONPATH'] = str(Path(__file__).parent.parent.parent)
    return env


@pytest.mark.integration
def test_backup_creation(env_vars, backup_dir):
    """Test creating a backup using backup.py"""
    script_path = Path(__file__).parent.parent.parent / "infrastructure/scripts/backup/backup.py"

    # Run backup script
    result = subprocess.run(
        ['python', str(script_path), '--skip-s3'],
        env=env_vars,
        capture_output=True,
        text=True,
        timeout=60
    )

    # Check if backup completed successfully
    assert result.returncode == 0, f"Backup failed: {result.stderr}"

    # Verify backup files were created
    backup_files = list(backup_dir.glob("rapids_backup_*.dump"))
    assert len(backup_files) > 0, "No backup file created"

    # Verify metadata file
    metadata_files = list(backup_dir.glob("rapids_backup_*.json"))
    assert len(metadata_files) > 0, "No metadata file created"

    # Verify metrics file
    metrics_file = backup_dir / "backup_metrics.prom"
    assert metrics_file.exists(), "Metrics file not created"


@pytest.mark.integration
def test_backup_verification(env_vars, backup_dir):
    """Test backup verification"""
    script_path = Path(__file__).parent.parent.parent / "infrastructure/scripts/backup/backup.py"

    # Create backup first
    subprocess.run(
        ['python', str(script_path), '--skip-s3'],
        env=env_vars,
        capture_output=True,
        timeout=60
    )

    # Run verification
    verify_script = Path(__file__).parent.parent.parent / "infrastructure/scripts/backup/verify.py"

    result = subprocess.run(
        ['python', str(verify_script), '--all'],
        env=env_vars,
        capture_output=True,
        text=True,
        timeout=60
    )

    assert result.returncode == 0, f"Verification failed: {result.stderr}"
    assert "PASS" in result.stdout or "✓" in result.stdout


@pytest.mark.integration
@pytest.mark.asyncio
async def test_backup_and_restore_workflow(postgres_container, env_vars, backup_dir):
    """Test complete backup and restore workflow"""
    # 1. Create initial backup
    backup_script = Path(__file__).parent.parent.parent / "infrastructure/scripts/backup/backup.py"

    result = subprocess.run(
        ['python', str(backup_script), '--skip-s3'],
        env=env_vars,
        capture_output=True,
        timeout=60
    )

    assert result.returncode == 0, "Initial backup failed"

    # Get the backup file
    backup_files = sorted(backup_dir.glob("rapids_backup_*.dump"))
    assert len(backup_files) > 0
    backup_file = backup_files[-1]

    # 2. Get current data count
    conn = await asyncpg.connect(env_vars['DATABASE_URL'])
    try:
        user_count_before = await conn.fetchval("SELECT COUNT(*) FROM users")
        project_count_before = await conn.fetchval("SELECT COUNT(*) FROM projects")

        # 3. Modify database (delete some data)
        await conn.execute("DELETE FROM projects WHERE id > 2")
        await conn.execute("DELETE FROM users WHERE id > 2")

        modified_user_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        modified_project_count = await conn.fetchval("SELECT COUNT(*) FROM projects")

        assert modified_user_count < user_count_before
        assert modified_project_count < project_count_before

    finally:
        await conn.close()

    # 4. Restore from backup
    restore_script = Path(__file__).parent.parent.parent / "infrastructure/scripts/backup/restore.py"

    result = subprocess.run(
        ['python', str(restore_script), '--backup-file', str(backup_file), '--force', '--skip-pre-backup'],
        env=env_vars,
        capture_output=True,
        text=True,
        timeout=120
    )

    assert result.returncode == 0, f"Restore failed: {result.stderr}"

    # 5. Verify data was restored
    conn = await asyncpg.connect(env_vars['DATABASE_URL'])
    try:
        user_count_after = await conn.fetchval("SELECT COUNT(*) FROM users")
        project_count_after = await conn.fetchval("SELECT COUNT(*) FROM projects")

        # Data should be restored to original counts
        assert user_count_after == user_count_before
        assert project_count_after == project_count_before

        # Verify specific data exists
        alice = await conn.fetchrow("SELECT * FROM users WHERE username = 'alice'")
        assert alice is not None
        assert alice['email'] == 'alice@example.com'

        projects = await conn.fetch("SELECT * FROM projects ORDER BY id")
        assert len(projects) == 4

    finally:
        await conn.close()


@pytest.mark.integration
def test_backup_with_retention_cleanup(env_vars, backup_dir):
    """Test backup retention policy"""
    script_path = Path(__file__).parent.parent.parent / "infrastructure/scripts/backup/backup.py"

    # Create multiple backups
    for i in range(3):
        result = subprocess.run(
            ['python', str(script_path), '--skip-s3', '--retention-days', '1'],
            env=env_vars,
            capture_output=True,
            timeout=60
        )
        assert result.returncode == 0

    # Should have 3 backups
    backup_files = list(backup_dir.glob("rapids_backup_*.dump"))
    assert len(backup_files) >= 3


@pytest.mark.integration
def test_dry_run_restore(env_vars, backup_dir):
    """Test restore dry-run mode"""
    # Create a backup first
    backup_script = Path(__file__).parent.parent.parent / "infrastructure/scripts/backup/backup.py"

    subprocess.run(
        ['python', str(backup_script), '--skip-s3'],
        env=env_vars,
        capture_output=True,
        timeout=60
    )

    # Get backup file
    backup_files = sorted(backup_dir.glob("rapids_backup_*.dump"))
    backup_file = backup_files[-1]

    # Run dry-run restore
    restore_script = Path(__file__).parent.parent.parent / "infrastructure/scripts/backup/restore.py"

    result = subprocess.run(
        ['python', str(restore_script), '--backup-file', str(backup_file), '--dry-run'],
        env=env_vars,
        capture_output=True,
        text=True,
        timeout=60
    )

    assert result.returncode == 0
    assert "DRY RUN" in result.stdout or "dry run" in result.stdout.lower()


@pytest.mark.integration
def test_verify_json_export(env_vars, backup_dir):
    """Test verification JSON export"""
    # Create backup
    backup_script = Path(__file__).parent.parent.parent / "infrastructure/scripts/backup/backup.py"

    subprocess.run(
        ['python', str(backup_script), '--skip-s3'],
        env=env_vars,
        capture_output=True,
        timeout=60
    )

    # Export verification report
    verify_script = Path(__file__).parent.parent.parent / "infrastructure/scripts/backup/verify.py"
    report_file = backup_dir / "verification_report.json"

    result = subprocess.run(
        ['python', str(verify_script), '--all', '--export-json', str(report_file)],
        env=env_vars,
        capture_output=True,
        timeout=60
    )

    assert result.returncode == 0
    assert report_file.exists()

    # Verify JSON structure
    import json
    with open(report_file) as f:
        report = json.load(f)

    assert 'generated_at' in report
    assert 'total_backups' in report
    assert 'passed' in report
    assert 'failed' in report
    assert 'backups' in report
    assert len(report['backups']) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-m', 'integration'])
