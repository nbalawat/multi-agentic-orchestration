"""
Git Worktree Manager

Manages git repositories and worktrees for parallel feature implementation.
During the Implement phase, each feature gets its own worktree so agents
can work in parallel without conflicts.

Worktrees are created as: <repo>/.rapids/worktrees/<feature-id>/
Each worktree gets a branch: rapids/<feature-id>
"""

import logging
import subprocess
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone

from . import config

logger = logging.getLogger(__name__)


class GitWorktreeManager:
    """Manages git repositories and worktrees for parallel feature implementation."""

    def __init__(self, repo_path: str):
        self._repo_path = Path(repo_path)
        self._worktrees_dir = self._repo_path / '.rapids' / 'worktrees'
        self._remote_sync = config.GIT_REMOTE_SYNC
        self._remote_name = config.GIT_REMOTE_NAME

    @property
    def repo_path(self) -> Path:
        return self._repo_path

    @property
    def worktrees_dir(self) -> Path:
        return self._worktrees_dir

    # ─── Git Repository Management ───────────────────────────────

    def is_git_repo(self) -> bool:
        """Check if the repo path is a git repository."""
        git_dir = self._repo_path / '.git'
        return git_dir.exists()

    def init_git_repo(self) -> bool:
        """
        Initialize a git repository if one doesn't exist.
        Creates initial commit so worktrees can be created.
        Returns True if newly initialized, False if already existed.
        """
        if self.is_git_repo():
            return False

        # Initialize repo
        self._run_git(['init'])

        # Configure basic git settings for the repo
        self._run_git(['config', 'user.email', 'rapids@orchestrator.local'])
        self._run_git(['config', 'user.name', 'RAPIDS Orchestrator'])

        # Create .gitignore if it doesn't exist
        gitignore_path = self._repo_path / '.gitignore'
        if not gitignore_path.exists():
            gitignore_path.write_text(
                "# RAPIDS orchestrator state\n"
                ".rapids/worktrees/\n"
                ".rapids/state.json\n"
                "\n"
                "# Python\n"
                "__pycache__/\n"
                "*.pyc\n"
                ".venv/\n"
                "\n"
                "# Node\n"
                "node_modules/\n"
                "\n"
                "# OS\n"
                ".DS_Store\n"
            )

        # Stage all existing files and create initial commit
        self._run_git(['add', '-A'])
        self._run_git(['commit', '--allow-empty', '-m', 'Initial commit (RAPIDS orchestrator)'])

        return True

    def ensure_git_repo(self) -> None:
        """Ensure the repo is a git repo, initializing if needed."""
        self.init_git_repo()

    def get_current_branch(self) -> str:
        """Get the current branch name."""
        result = self._run_git(['rev-parse', '--abbrev-ref', 'HEAD'])
        return result.strip()

    def get_main_branch(self) -> str:
        """Get the main/default branch name."""
        # Try common names
        for branch in ['main', 'master']:
            result = self._run_git(['branch', '--list', branch], check=False)
            if result.strip():
                return branch
        # Fall back to current branch
        return self.get_current_branch()

    # ─── Worktree Management ─────────────────────────────────────

    def create_worktree(self, feature_id: str, base_branch: Optional[str] = None) -> Path:
        """
        Create a git worktree for a feature.

        Args:
            feature_id: Feature identifier (used for branch and directory name)
            base_branch: Branch to base the worktree on (defaults to main branch)

        Returns:
            Path to the worktree directory
        """
        self.ensure_git_repo()

        worktree_path = self._worktrees_dir / feature_id
        branch_name = f'rapids/{feature_id}'

        if worktree_path.exists():
            # Worktree already exists, return its path
            return worktree_path

        # Ensure worktrees directory exists
        self._worktrees_dir.mkdir(parents=True, exist_ok=True)

        # Determine base branch
        if base_branch is None:
            base_branch = self.get_main_branch()

        # Sync from remote before branching so worktree starts from latest
        sync_ok, sync_msg = self.sync_main_from_remote()
        if not sync_ok:
            logger.warning(f"Pre-worktree remote sync warning: {sync_msg}")

        # Create a new branch and worktree
        self._run_git([
            'worktree', 'add',
            '-b', branch_name,
            str(worktree_path),
            base_branch,
        ])

        return worktree_path

    def remove_worktree(self, feature_id: str, force: bool = False) -> bool:
        """
        Remove a git worktree for a feature.

        Args:
            feature_id: Feature identifier
            force: Force removal even if worktree has changes

        Returns:
            True if removed, False if not found
        """
        worktree_path = self._worktrees_dir / feature_id

        if not worktree_path.exists():
            return False

        # Remove the worktree
        cmd = ['worktree', 'remove']
        if force:
            cmd.append('--force')
        cmd.append(str(worktree_path))

        try:
            self._run_git(cmd)
        except subprocess.CalledProcessError:
            if force:
                # If force removal via git fails, clean up manually
                shutil.rmtree(worktree_path, ignore_errors=True)
                self._run_git(['worktree', 'prune'])
            else:
                raise

        return True

    def get_worktree_path(self, feature_id: str) -> Optional[Path]:
        """Get the worktree path for a feature, or None if it doesn't exist."""
        worktree_path = self._worktrees_dir / feature_id
        if worktree_path.exists():
            return worktree_path
        return None

    def list_worktrees(self) -> List[Dict]:
        """List all active worktrees for this repo."""
        result = self._run_git(['worktree', 'list', '--porcelain'])
        worktrees = []
        current = {}

        for line in result.strip().split('\n'):
            line = line.strip()
            if not line:
                if current and 'worktree' in current:
                    # Only include worktrees under our worktrees dir
                    wt_path = Path(current['worktree'])
                    if str(wt_path).startswith(str(self._worktrees_dir)):
                        feature_id = wt_path.name
                        current['feature_id'] = feature_id
                        worktrees.append(current)
                current = {}
            elif line.startswith('worktree '):
                current['worktree'] = line[9:]
            elif line.startswith('HEAD '):
                current['head'] = line[5:]
            elif line.startswith('branch '):
                current['branch'] = line[7:]
            elif line == 'bare':
                current['bare'] = True

        # Don't forget last entry
        if current and 'worktree' in current:
            wt_path = Path(current['worktree'])
            if str(wt_path).startswith(str(self._worktrees_dir)):
                feature_id = wt_path.name
                current['feature_id'] = feature_id
                worktrees.append(current)

        return worktrees

    def merge_worktree(self, feature_id: str, target_branch: Optional[str] = None,
                       delete_after: bool = True) -> Tuple[bool, str]:
        """
        Merge a feature worktree's branch back into the target branch.

        Args:
            feature_id: Feature identifier
            target_branch: Branch to merge into (defaults to main branch)
            delete_after: Remove the worktree after successful merge

        Returns:
            (success, message) tuple
        """
        branch_name = f'rapids/{feature_id}'
        if target_branch is None:
            target_branch = self.get_main_branch()

        try:
            # Switch to target branch in the main repo
            self._run_git(['checkout', target_branch])

            # Merge the feature branch
            result = self._run_git(
                ['merge', branch_name, '--no-ff',
                 '-m', f'Merge feature {feature_id} from RAPIDS implementation'],
                check=False
            )

            if 'CONFLICT' in result:
                # Abort merge on conflict
                self._run_git(['merge', '--abort'])
                return False, f'Merge conflict in feature {feature_id}. Manual resolution needed.'

            # Clean up
            if delete_after:
                self.remove_worktree(feature_id, force=True)
                # Delete the feature branch
                self._run_git(['branch', '-d', branch_name], check=False)

            # Push merged main to remote
            push_ok, push_msg = self.push_to_remote(target_branch)
            if not push_ok:
                logger.warning(f"Post-merge push warning: {push_msg}")
                return True, f'Feature {feature_id} merged into {target_branch} (local only — push failed: {push_msg})'

            return True, f'Feature {feature_id} merged into {target_branch} and pushed to remote'

        except subprocess.CalledProcessError as e:
            return False, f'Merge failed: {e}'

    def cleanup_all_worktrees(self, force: bool = False) -> int:
        """
        Remove all RAPIDS worktrees. Returns count of removed worktrees.
        """
        worktrees = self.list_worktrees()
        count = 0
        for wt in worktrees:
            if 'feature_id' in wt:
                if self.remove_worktree(wt['feature_id'], force=force):
                    count += 1
        # Prune any stale worktree entries
        self._run_git(['worktree', 'prune'])
        return count

    # ─── Remote Sync ────────────────────────────────────────────

    def has_remote(self, remote: Optional[str] = None) -> bool:
        """Check if the specified remote exists."""
        remote = remote or self._remote_name
        try:
            self._run_git(['remote', 'get-url', remote])
            return True
        except subprocess.CalledProcessError:
            return False

    def fetch_remote(self, remote: Optional[str] = None) -> str:
        """Fetch from the remote. Returns output."""
        remote = remote or self._remote_name
        return self._run_git(['fetch', remote], check=False)

    def sync_main_from_remote(self, remote: Optional[str] = None) -> Tuple[bool, str]:
        """
        Fetch and fast-forward merge main branch from remote.
        Non-fatal: returns (True, reason) when skipped, (False, reason) on divergence.
        """
        if not self._remote_sync:
            return True, "Remote sync disabled via GIT_REMOTE_SYNC"

        remote = remote or self._remote_name

        if not self.has_remote(remote):
            return True, f"No remote '{remote}' configured, skipping sync"

        try:
            self.fetch_remote(remote)
            main_branch = self.get_main_branch()

            # Fast-forward only — never create surprise merge commits
            result = self._run_git(
                ['merge', f'{remote}/{main_branch}', '--ff-only'],
                check=False
            )

            if 'fatal' in result.lower() or 'error' in result.lower():
                logger.warning(f"Remote sync failed (non-fatal): {result.strip()}")
                return False, f"Main branch has diverged from {remote}/{main_branch}; manual intervention needed"

            logger.info(f"Synced main branch from {remote}/{main_branch}")
            return True, f"Synced from {remote}/{main_branch}"

        except subprocess.CalledProcessError as e:
            logger.warning(f"Remote sync error (non-fatal): {e}")
            return False, f"Remote sync failed: {e}"

    def push_to_remote(self, branch: Optional[str] = None,
                       remote: Optional[str] = None) -> Tuple[bool, str]:
        """
        Push a branch to the remote.
        Non-fatal: returns (True, reason) when skipped.
        """
        if not self._remote_sync:
            return True, "Remote sync disabled via GIT_REMOTE_SYNC"

        remote = remote or self._remote_name

        if not self.has_remote(remote):
            return True, f"No remote '{remote}' configured, skipping push"

        if branch is None:
            branch = self.get_main_branch()

        try:
            result = self._run_git(['push', remote, branch], check=False)

            if 'error' in result.lower() or 'rejected' in result.lower():
                logger.warning(f"Push failed (non-fatal): {result.strip()}")
                return False, f"Push to {remote}/{branch} rejected — pull and resolve first"

            logger.info(f"Pushed {branch} to {remote}")
            return True, f"Pushed {branch} to {remote}"

        except subprocess.CalledProcessError as e:
            logger.warning(f"Push error (non-fatal): {e}")
            return False, f"Push failed: {e}"

    # ─── Helpers ─────────────────────────────────────────────────

    def _run_git(self, args: List[str], check: bool = True) -> str:
        """Run a git command in the repo directory."""
        cmd = ['git'] + args
        result = subprocess.run(
            cmd,
            cwd=str(self._repo_path),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, cmd,
                output=result.stdout,
                stderr=result.stderr,
            )
        return result.stdout + result.stderr
