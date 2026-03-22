"""
Tests for GitWorktreeManager.

NO MOCKS — uses real git operations in temporary directories.
"""

import subprocess
import pytest
from pathlib import Path

from orchestrator.backend.modules.git_worktree import GitWorktreeManager


@pytest.fixture
def empty_dir(tmp_path):
    """Create an empty temporary directory (not a git repo)."""
    d = tmp_path / "project"
    d.mkdir()
    return d


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repository with an initial commit."""
    d = tmp_path / "repo"
    d.mkdir()
    subprocess.run(["git", "init"], cwd=str(d), capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(d), capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(d), capture_output=True, check=True,
    )
    # Create a file and commit
    (d / "README.md").write_text("# Test Project\n")
    subprocess.run(["git", "add", "-A"], cwd=str(d), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=str(d), capture_output=True, check=True,
    )
    return d


class TestIsGitRepo:
    def test_is_git_repo_true(self, git_repo):
        mgr = GitWorktreeManager(str(git_repo))
        assert mgr.is_git_repo() is True

    def test_is_git_repo_false(self, empty_dir):
        mgr = GitWorktreeManager(str(empty_dir))
        assert mgr.is_git_repo() is False


class TestInitGitRepo:
    def test_init_creates_git_dir(self, empty_dir):
        mgr = GitWorktreeManager(str(empty_dir))
        result = mgr.init_git_repo()
        assert result is True
        assert (empty_dir / ".git").exists()

    def test_init_creates_gitignore(self, empty_dir):
        mgr = GitWorktreeManager(str(empty_dir))
        mgr.init_git_repo()
        gitignore = empty_dir / ".gitignore"
        assert gitignore.exists()
        content = gitignore.read_text()
        assert ".rapids/worktrees/" in content

    def test_init_creates_initial_commit(self, empty_dir):
        mgr = GitWorktreeManager(str(empty_dir))
        mgr.init_git_repo()
        # Check there's at least one commit
        result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=str(empty_dir), capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "RAPIDS" in result.stdout or "Initial" in result.stdout

    def test_init_returns_false_if_already_git(self, git_repo):
        mgr = GitWorktreeManager(str(git_repo))
        result = mgr.init_git_repo()
        assert result is False

    def test_ensure_git_repo_idempotent(self, empty_dir):
        mgr = GitWorktreeManager(str(empty_dir))
        mgr.ensure_git_repo()
        assert mgr.is_git_repo()
        mgr.ensure_git_repo()  # Should not error
        assert mgr.is_git_repo()


class TestBranchInfo:
    def test_get_current_branch(self, git_repo):
        mgr = GitWorktreeManager(str(git_repo))
        branch = mgr.get_current_branch()
        assert branch in ("main", "master")

    def test_get_main_branch(self, git_repo):
        mgr = GitWorktreeManager(str(git_repo))
        branch = mgr.get_main_branch()
        assert branch in ("main", "master")


class TestCreateWorktree:
    def test_create_worktree(self, git_repo):
        mgr = GitWorktreeManager(str(git_repo))
        wt_path = mgr.create_worktree("feat-001")

        assert wt_path.exists()
        assert wt_path.is_dir()
        assert (wt_path / "README.md").exists()  # Inherits from main

    def test_worktree_path_under_rapids(self, git_repo):
        mgr = GitWorktreeManager(str(git_repo))
        wt_path = mgr.create_worktree("feat-001")

        expected = git_repo / ".rapids" / "worktrees" / "feat-001"
        assert wt_path == expected

    def test_worktree_has_feature_branch(self, git_repo):
        mgr = GitWorktreeManager(str(git_repo))
        mgr.create_worktree("feat-001")

        # Check the branch exists
        result = subprocess.run(
            ["git", "branch", "--list", "rapids/feat-001"],
            cwd=str(git_repo), capture_output=True, text=True,
        )
        assert "rapids/feat-001" in result.stdout

    def test_create_worktree_idempotent(self, git_repo):
        mgr = GitWorktreeManager(str(git_repo))
        path1 = mgr.create_worktree("feat-001")
        path2 = mgr.create_worktree("feat-001")
        assert path1 == path2

    def test_create_multiple_worktrees(self, git_repo):
        mgr = GitWorktreeManager(str(git_repo))
        wt1 = mgr.create_worktree("feat-001")
        wt2 = mgr.create_worktree("feat-002")
        wt3 = mgr.create_worktree("feat-003")

        assert wt1.exists()
        assert wt2.exists()
        assert wt3.exists()
        assert wt1 != wt2 != wt3

    def test_worktrees_are_independent(self, git_repo):
        """Changes in one worktree don't affect others."""
        mgr = GitWorktreeManager(str(git_repo))
        wt1 = mgr.create_worktree("feat-001")
        wt2 = mgr.create_worktree("feat-002")

        # Write a file in wt1
        (wt1 / "feature1.txt").write_text("Feature 1")

        # wt2 should NOT have it
        assert not (wt2 / "feature1.txt").exists()


class TestRemoveWorktree:
    def test_remove_worktree(self, git_repo):
        mgr = GitWorktreeManager(str(git_repo))
        wt_path = mgr.create_worktree("feat-001")
        assert wt_path.exists()

        result = mgr.remove_worktree("feat-001")
        assert result is True
        assert not wt_path.exists()

    def test_remove_nonexistent_returns_false(self, git_repo):
        mgr = GitWorktreeManager(str(git_repo))
        result = mgr.remove_worktree("nonexistent")
        assert result is False

    def test_remove_worktree_with_changes(self, git_repo):
        mgr = GitWorktreeManager(str(git_repo))
        wt_path = mgr.create_worktree("feat-001")

        # Make changes in worktree
        (wt_path / "new_file.txt").write_text("new content")

        # Force removal should work
        result = mgr.remove_worktree("feat-001", force=True)
        assert result is True


class TestListWorktrees:
    def test_list_empty(self, git_repo):
        mgr = GitWorktreeManager(str(git_repo))
        worktrees = mgr.list_worktrees()
        assert len(worktrees) == 0

    def test_list_with_worktrees(self, git_repo):
        mgr = GitWorktreeManager(str(git_repo))
        mgr.create_worktree("feat-001")
        mgr.create_worktree("feat-002")

        worktrees = mgr.list_worktrees()
        assert len(worktrees) == 2
        feature_ids = [wt["feature_id"] for wt in worktrees]
        assert "feat-001" in feature_ids
        assert "feat-002" in feature_ids

    def test_list_has_branch_info(self, git_repo):
        mgr = GitWorktreeManager(str(git_repo))
        mgr.create_worktree("feat-001")

        worktrees = mgr.list_worktrees()
        assert len(worktrees) == 1
        assert "branch" in worktrees[0]
        assert "rapids/feat-001" in worktrees[0]["branch"]


class TestGetWorktreePath:
    def test_get_existing(self, git_repo):
        mgr = GitWorktreeManager(str(git_repo))
        mgr.create_worktree("feat-001")

        path = mgr.get_worktree_path("feat-001")
        assert path is not None
        assert path.exists()

    def test_get_nonexistent(self, git_repo):
        mgr = GitWorktreeManager(str(git_repo))
        path = mgr.get_worktree_path("feat-001")
        assert path is None


class TestMergeWorktree:
    def test_merge_worktree(self, git_repo):
        mgr = GitWorktreeManager(str(git_repo))
        wt_path = mgr.create_worktree("feat-001")

        # Make a change and commit in the worktree
        (wt_path / "feature.py").write_text("def hello(): return 'world'\n")
        subprocess.run(["git", "add", "-A"], cwd=str(wt_path), capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add feature"],
            cwd=str(wt_path), capture_output=True, check=True,
        )

        # Merge back
        success, msg = mgr.merge_worktree("feat-001", delete_after=True)
        assert success is True
        assert "merged" in msg.lower() or "Merge" in msg

        # File should exist in main repo now
        assert (git_repo / "feature.py").exists()

    def test_merge_no_changes(self, git_repo):
        mgr = GitWorktreeManager(str(git_repo))
        mgr.create_worktree("feat-001")

        # Merge without any changes - should succeed (fast-forward or empty merge)
        success, msg = mgr.merge_worktree("feat-001", delete_after=True)
        # Even with no changes, merge should succeed
        assert success is True


class TestCleanupAllWorktrees:
    def test_cleanup_all(self, git_repo):
        mgr = GitWorktreeManager(str(git_repo))
        mgr.create_worktree("feat-001")
        mgr.create_worktree("feat-002")
        mgr.create_worktree("feat-003")

        count = mgr.cleanup_all_worktrees(force=True)
        assert count == 3

        # Verify all removed
        assert len(mgr.list_worktrees()) == 0

    def test_cleanup_empty(self, git_repo):
        mgr = GitWorktreeManager(str(git_repo))
        count = mgr.cleanup_all_worktrees()
        assert count == 0


class TestWorktreeProperties:
    def test_repo_path(self, git_repo):
        mgr = GitWorktreeManager(str(git_repo))
        assert mgr.repo_path == git_repo

    def test_worktrees_dir(self, git_repo):
        mgr = GitWorktreeManager(str(git_repo))
        expected = git_repo / ".rapids" / "worktrees"
        assert mgr.worktrees_dir == expected
