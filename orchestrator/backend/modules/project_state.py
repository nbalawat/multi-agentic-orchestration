"""
Project State Manager

Manages the .rapids/ directory within each project repository.
Handles initialization, state file I/O, and artifact management.
"""

from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
import json

# Phase directories that map directly to RAPIDS phases
PHASE_DIRS = ['research', 'analysis', 'plan', 'features', 'deploy', 'sustain']


class ProjectState:
    """Manages per-project .rapids/ state directory."""

    def __init__(self, repo_path: str, project_id: str, archetype: str, plugin: str):
        self._repo_path = Path(repo_path)
        self._rapids_dir = self._repo_path / '.rapids'
        self._project_id = project_id
        self._archetype = archetype
        self._plugin = plugin

    @property
    def rapids_dir(self) -> Path:
        """Return the path to the .rapids/ directory."""
        return self._rapids_dir

    @property
    def is_initialized(self) -> bool:
        """Check if the .rapids/ directory has been initialized."""
        state_path = self._rapids_dir / 'state.json'
        return self._rapids_dir.exists() and state_path.exists()

    def init_rapids_dir(self) -> None:
        """Create the full .rapids/ directory structure:
        .rapids/
        |- state.json
        |- config.json
        |- research/
        |- analysis/
        |- plan/
        |- features/
        |- deploy/
        |- sustain/
        """
        # Create the root .rapids directory
        self._rapids_dir.mkdir(parents=True, exist_ok=True)

        # Create phase subdirectories
        for dir_name in PHASE_DIRS:
            (self._rapids_dir / dir_name).mkdir(exist_ok=True)

        # Initialize state.json if it doesn't exist
        state_path = self._rapids_dir / 'state.json'
        if not state_path.exists():
            initial_state = {
                'project_id': self._project_id,
                'archetype': self._archetype,
                'plugin': self._plugin,
                'current_phase': 'research',
                'phases': {
                    'research':  {'status': 'not_started', 'started_at': None, 'completed_at': None},
                    'analysis':  {'status': 'not_started', 'started_at': None, 'completed_at': None},
                    'plan':      {'status': 'not_started', 'started_at': None, 'completed_at': None},
                    'implement': {'status': 'not_started', 'started_at': None, 'completed_at': None},
                    'deploy':    {'status': 'not_started', 'started_at': None, 'completed_at': None},
                    'sustain':   {'status': 'not_started', 'started_at': None, 'completed_at': None},
                },
            }
            self.write_state(initial_state)

        # Initialize config.json if it doesn't exist
        config_path = self._rapids_dir / 'config.json'
        if not config_path.exists():
            initial_config = {
                'project_id': self._project_id,
                'archetype': self._archetype,
                'plugin': self._plugin,
                'created_at': datetime.now(timezone.utc).isoformat(),
            }
            self.write_config(initial_config)

    # -------------------------------------------------------------------------
    # State management
    # -------------------------------------------------------------------------

    def read_state(self) -> Dict:
        """Read state.json from .rapids/"""
        state_path = self._rapids_dir / 'state.json'
        if not state_path.exists():
            return {}
        try:
            with open(state_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def write_state(self, state: Dict) -> None:
        """Write state.json to .rapids/"""
        self._rapids_dir.mkdir(parents=True, exist_ok=True)
        state_path = self._rapids_dir / 'state.json'
        with open(state_path, 'w') as f:
            json.dump(state, f, indent=2)

    def read_config(self) -> Dict:
        """Read config.json from .rapids/"""
        config_path = self._rapids_dir / 'config.json'
        if not config_path.exists():
            return {}
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def write_config(self, config: Dict) -> None:
        """Write config.json to .rapids/"""
        self._rapids_dir.mkdir(parents=True, exist_ok=True)
        config_path = self._rapids_dir / 'config.json'
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)

    # -------------------------------------------------------------------------
    # Artifact management
    # -------------------------------------------------------------------------

    def _phase_dir(self, phase: str) -> Path:
        """Map a phase name to its directory under .rapids/.
        The 'implement' phase uses the 'features' directory."""
        if phase == 'implement':
            return self._rapids_dir / 'features'
        return self._rapids_dir / phase

    def get_phase_artifacts(self, phase: str) -> List[Path]:
        """List all artifact files in a phase directory."""
        phase_dir = self._phase_dir(phase)
        if not phase_dir.exists():
            return []
        return sorted([f for f in phase_dir.rglob('*') if f.is_file()])

    def save_phase_artifact(self, phase: str, filename: str, content: str) -> Path:
        """Save an artifact file to a phase directory. Returns the file path."""
        phase_dir = self._phase_dir(phase)
        phase_dir.mkdir(parents=True, exist_ok=True)
        file_path = phase_dir / filename
        # Create intermediate directories if filename contains path separators
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding='utf-8')
        return file_path

    def read_phase_artifact(self, phase: str, filename: str) -> Optional[str]:
        """Read an artifact file from a phase directory."""
        phase_dir = self._phase_dir(phase)
        file_path = phase_dir / filename
        if not file_path.exists():
            return None
        try:
            return file_path.read_text(encoding='utf-8')
        except OSError:
            return None

    def delete_phase_artifact(self, phase: str, filename: str) -> bool:
        """Delete an artifact file. Returns True if deleted."""
        phase_dir = self._phase_dir(phase)
        file_path = phase_dir / filename
        if not file_path.exists():
            return False
        try:
            file_path.unlink()
            return True
        except OSError:
            return False

    # -------------------------------------------------------------------------
    # Feature management
    # -------------------------------------------------------------------------

    def get_feature_dag_path(self) -> Path:
        """Returns path to .rapids/plan/feature_dag.json"""
        return self._rapids_dir / 'plan' / 'feature_dag.json'

    def get_feature_specs(self) -> List[Path]:
        """List all feature spec files in .rapids/features/"""
        features_dir = self._rapids_dir / 'features'
        if not features_dir.exists():
            return []
        return sorted([f for f in features_dir.rglob('*') if f.is_file()])

    def save_feature_spec(self, feature_id: str, name: str, content: str) -> Path:
        """Save a feature spec file. Returns the path.
        Saved to .rapids/features/<feature_id>/<name>"""
        feature_dir = self._rapids_dir / 'features' / feature_id
        feature_dir.mkdir(parents=True, exist_ok=True)
        file_path = feature_dir / name
        file_path.write_text(content, encoding='utf-8')
        return file_path

    def read_feature_spec(self, feature_id: str, name: str) -> Optional[str]:
        """Read a feature spec file."""
        file_path = self._rapids_dir / 'features' / feature_id / name
        if not file_path.exists():
            return None
        try:
            return file_path.read_text(encoding='utf-8')
        except OSError:
            return None

    # -------------------------------------------------------------------------
    # Spec management
    # -------------------------------------------------------------------------

    def get_spec_path(self) -> Path:
        """Returns path to .rapids/plan/spec.md"""
        return self._rapids_dir / 'plan' / 'spec.md'

    def save_spec(self, content: str) -> Path:
        """Save the consolidated specification."""
        plan_dir = self._rapids_dir / 'plan'
        plan_dir.mkdir(parents=True, exist_ok=True)
        spec_path = plan_dir / 'spec.md'
        spec_path.write_text(content, encoding='utf-8')
        return spec_path

    def read_spec(self) -> Optional[str]:
        """Read the consolidated specification."""
        spec_path = self._rapids_dir / 'plan' / 'spec.md'
        if not spec_path.exists():
            return None
        try:
            return spec_path.read_text(encoding='utf-8')
        except OSError:
            return None
