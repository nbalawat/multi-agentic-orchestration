"""
Tests for backup verification utility

Tests cover:
- Checksum validation
- Integrity checks
- S3 availability checks
- Verification reports
- JSON export
"""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch
import pytest

# Import verify module
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "infrastructure/scripts/backup"))

from verify import BackupVerifier, VerificationResult


@pytest.fixture
def backup_dir(tmp_path):
    """Create temporary backup directory"""
    backup_path = tmp_path / "backups"
    backup_path.mkdir()
    return backup_path


@pytest.fixture
def verifier(backup_dir):
    """Create BackupVerifier instance"""
    return BackupVerifier(backup_dir=str(backup_dir), s3_bucket=None)


def test_calculate_checksum(verifier, tmp_path):
    """Test checksum calculation"""
    test_file = tmp_path / "test.txt"
    test_data = b"test data for checksum calculation"
    test_file.write_bytes(test_data)

    checksum = verifier.calculate_checksum(test_file)

    # Verify checksum format (SHA256 = 64 hex characters)
    assert len(checksum) == 64
    assert all(c in '0123456789abcdef' for c in checksum)

    # Verify consistency
    checksum2 = verifier.calculate_checksum(test_file)
    assert checksum == checksum2

    # Verify different data produces different checksum
    test_file.write_bytes(b"different data")
    checksum3 = verifier.calculate_checksum(test_file)
    assert checksum != checksum3


def test_verify_integrity_success(verifier, backup_dir):
    """Test successful integrity verification"""
    backup_file = backup_dir / "test_backup.dump"
    backup_file.write_bytes(b"backup data")

    # Mock successful pg_restore --list
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(
            returncode=0,
            stdout=";\n; Archive created at 2026-03-24\n; Table of contents:\n" + ("Entry\n" * 20),
            stderr=""
        )

        result = verifier.verify_integrity(backup_file)

        assert result is True
        mock_run.assert_called_once()


def test_verify_integrity_failure(verifier, backup_dir):
    """Test failed integrity verification"""
    backup_file = backup_dir / "corrupted.dump"
    backup_file.write_bytes(b"corrupted data")

    # Mock failed pg_restore
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="pg_restore: error: could not read from input file"
        )

        result = verifier.verify_integrity(backup_file)

        assert result is False


def test_verify_integrity_empty_output(verifier, backup_dir):
    """Test integrity check with empty output"""
    backup_file = backup_dir / "empty.dump"
    backup_file.write_bytes(b"")

    with patch('subprocess.run') as mock_run:
        mock_run.return_value = Mock(
            returncode=0,
            stdout="",  # Empty output
            stderr=""
        )

        result = verifier.verify_integrity(backup_file)

        assert result is False


def test_check_s3_backup_no_bucket(verifier):
    """Test S3 check when no bucket configured"""
    result = verifier.check_s3_backup("20260324_120000")
    assert result is False


def test_check_s3_backup_exists(backup_dir):
    """Test S3 backup existence check"""
    verifier = BackupVerifier(backup_dir=str(backup_dir), s3_bucket="test-bucket")

    with patch('subprocess.run') as mock_run:
        # Mock AWS CLI available and backup exists
        mock_run.side_effect = [
            Mock(returncode=0, stdout="", stderr=""),  # aws --version
            Mock(returncode=0, stdout="rapids_backup_20260324_120000.dump\n", stderr="")  # aws s3 ls
        ]

        result = verifier.check_s3_backup("20260324_120000")

        assert result is True


def test_check_s3_backup_not_exists(backup_dir):
    """Test S3 backup not found"""
    verifier = BackupVerifier(backup_dir=str(backup_dir), s3_bucket="test-bucket")

    with patch('subprocess.run') as mock_run:
        # Mock AWS CLI available but backup doesn't exist
        mock_run.side_effect = [
            Mock(returncode=0, stdout="", stderr=""),  # aws --version
            Mock(returncode=1, stdout="", stderr="")   # aws s3 ls (not found)
        ]

        result = verifier.check_s3_backup("20260324_120000")

        assert result is False


def test_verify_backup_complete(verifier, backup_dir):
    """Test complete backup verification"""
    # Create backup file
    backup_file = backup_dir / "rapids_backup_20260324_120000.dump"
    backup_data = b"x" * 1024 * 100  # 100KB
    backup_file.write_bytes(backup_data)

    # Create metadata with correct checksum
    import hashlib
    checksum = hashlib.sha256(backup_data).hexdigest()

    metadata = {
        'timestamp': '20260324_120000',
        'database_name': 'test',
        'checksum': checksum,
        'verified': True
    }

    metadata_file = backup_dir / "rapids_backup_20260324_120000.json"
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f)

    # Mock integrity check
    with patch.object(verifier, 'verify_integrity', return_value=True):
        result = verifier.verify_backup(backup_file)

    # Verify result
    assert result.backup_file == "rapids_backup_20260324_120000.dump"
    assert result.timestamp == "20260324_120000"
    assert result.file_exists is True
    assert result.file_size_mb > 0
    assert result.checksum_match is True
    assert result.integrity_check is True
    assert result.metadata_exists is True
    assert result.passed is True
    assert len(result.errors) == 0


def test_verify_backup_missing_file(verifier, backup_dir):
    """Test verification of missing backup file"""
    backup_file = backup_dir / "nonexistent.dump"

    result = verifier.verify_backup(backup_file)

    assert result.file_exists is False
    assert result.passed is False
    assert "Backup file not found" in result.errors


def test_verify_backup_missing_metadata(verifier, backup_dir):
    """Test verification without metadata"""
    backup_file = backup_dir / "rapids_backup_20260324_120000.dump"
    backup_file.write_bytes(b"data")

    with patch.object(verifier, 'verify_integrity', return_value=True):
        result = verifier.verify_backup(backup_file)

    assert result.metadata_exists is False
    assert "Metadata file not found" in result.errors


def test_verify_backup_checksum_mismatch(verifier, backup_dir):
    """Test verification with checksum mismatch"""
    # Create backup file
    backup_file = backup_dir / "rapids_backup_20260324_120000.dump"
    backup_file.write_bytes(b"actual data")

    # Create metadata with wrong checksum
    metadata = {
        'timestamp': '20260324_120000',
        'checksum': 'wrong_checksum_value_1234567890abcdef' * 2  # Wrong checksum
    }

    metadata_file = backup_dir / "rapids_backup_20260324_120000.json"
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f)

    with patch.object(verifier, 'verify_integrity', return_value=True):
        result = verifier.verify_backup(backup_file)

    assert result.checksum_match is False
    assert any("Checksum mismatch" in error for error in result.errors)
    assert result.passed is False


def test_verify_backup_integrity_failure(verifier, backup_dir):
    """Test verification with integrity check failure"""
    backup_file = backup_dir / "rapids_backup_20260324_120000.dump"
    backup_file.write_bytes(b"corrupted")

    with patch.object(verifier, 'verify_integrity', return_value=False):
        result = verifier.verify_backup(backup_file)

    assert result.integrity_check is False
    assert any("Integrity check failed" in error for error in result.errors)
    assert result.passed is False


def test_verify_all_backups(verifier, backup_dir):
    """Test verifying multiple backups"""
    # Create multiple backup files
    timestamps = ["20260320_120000", "20260322_120000", "20260324_120000"]

    for ts in timestamps:
        backup_file = backup_dir / f"rapids_backup_{ts}.dump"
        backup_file.write_bytes(b"data")

        # Create metadata
        metadata_file = backup_dir / f"rapids_backup_{ts}.json"
        metadata_file.write_text(json.dumps({
            'timestamp': ts,
            'checksum': verifier.calculate_checksum(backup_file)
        }))

    # Mock integrity checks
    with patch.object(verifier, 'verify_integrity', return_value=True):
        results = verifier.verify_all_backups()

    assert len(results) == 3

    # Verify timestamps are in reverse chronological order
    assert results[0].timestamp == "20260324_120000"
    assert results[1].timestamp == "20260322_120000"
    assert results[2].timestamp == "20260320_120000"


def test_generate_report(verifier, capsys):
    """Test report generation"""
    results = [
        VerificationResult(
            backup_file="rapids_backup_20260324_120000.dump",
            timestamp="20260324_120000",
            file_exists=True,
            file_size_mb=100.5,
            checksum_match=True,
            integrity_check=True,
            metadata_exists=True,
            s3_exists=True,
            errors=[]
        ),
        VerificationResult(
            backup_file="rapids_backup_20260323_120000.dump",
            timestamp="20260323_120000",
            file_exists=True,
            file_size_mb=95.2,
            checksum_match=False,
            integrity_check=True,
            metadata_exists=True,
            s3_exists=False,
            errors=["Checksum mismatch"]
        )
    ]

    verifier.generate_report(results)

    # Capture output
    captured = capsys.readouterr()

    # Verify output contains expected information
    assert "Backup Verification Report" in captured.out
    assert "20260324_120000" in captured.out
    assert "20260323_120000" in captured.out
    assert "Verification Summary" in captured.out


def test_export_report_json(verifier, tmp_path):
    """Test JSON report export"""
    results = [
        VerificationResult(
            backup_file="rapids_backup_20260324_120000.dump",
            timestamp="20260324_120000",
            file_exists=True,
            file_size_mb=100.0,
            checksum_match=True,
            integrity_check=True,
            metadata_exists=True,
            s3_exists=True,
            errors=[]
        )
    ]

    output_file = tmp_path / "report.json"
    verifier.export_report_json(results, str(output_file))

    # Verify file was created
    assert output_file.exists()

    # Verify content
    with open(output_file) as f:
        report = json.load(f)

    assert 'generated_at' in report
    assert report['total_backups'] == 1
    assert report['passed'] == 1
    assert report['failed'] == 0
    assert len(report['backups']) == 1

    backup_info = report['backups'][0]
    assert backup_info['timestamp'] == "20260324_120000"
    assert backup_info['passed'] is True
    assert backup_info['checksum_match'] is True


def test_verification_result_passed_property():
    """Test VerificationResult.passed property logic"""
    # All checks pass
    result_pass = VerificationResult(
        backup_file="test.dump",
        timestamp="20260324_120000",
        file_exists=True,
        file_size_mb=100.0,
        checksum_match=True,
        integrity_check=True,
        metadata_exists=True,
        errors=[]
    )
    assert result_pass.passed is True

    # File doesn't exist
    result_fail1 = VerificationResult(
        backup_file="test.dump",
        timestamp="20260324_120000",
        file_exists=False,
        file_size_mb=0.0,
        checksum_match=True,
        integrity_check=True,
        metadata_exists=True,
        errors=[]
    )
    assert result_fail1.passed is False

    # Checksum mismatch
    result_fail2 = VerificationResult(
        backup_file="test.dump",
        timestamp="20260324_120000",
        file_exists=True,
        file_size_mb=100.0,
        checksum_match=False,
        integrity_check=True,
        metadata_exists=True,
        errors=["Checksum mismatch"]
    )
    assert result_fail2.passed is False

    # Integrity check failed
    result_fail3 = VerificationResult(
        backup_file="test.dump",
        timestamp="20260324_120000",
        file_exists=True,
        file_size_mb=100.0,
        checksum_match=True,
        integrity_check=False,
        metadata_exists=True,
        errors=["Integrity check failed"]
    )
    assert result_fail3.passed is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
