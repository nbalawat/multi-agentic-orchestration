"""
RAPIDS Phase Engine

State machine for the RAPIDS workflow: Research -> Analysis -> Plan -> Implement -> Deploy -> Sustain.
Manages phase transitions with configurable entry/exit criteria.
"""

from typing import Dict, List, Optional, Any, Literal
from pathlib import Path
from datetime import datetime, timezone
import json

PHASE_ORDER = ['research', 'analysis', 'plan', 'implement', 'deploy', 'sustain']

PHASE_TRANSITIONS = {
    'research':  {'next': 'analysis',  'prev': None},
    'analysis':  {'next': 'plan',      'prev': 'research'},
    'plan':      {'next': 'implement', 'prev': 'analysis'},
    'implement': {'next': 'deploy',    'prev': 'plan'},
    'deploy':    {'next': 'sustain',   'prev': 'implement'},
    'sustain':   {'next': None,        'prev': 'deploy'},
}

# Default entry/exit criteria (can be overridden by plugins)
DEFAULT_CRITERIA = {
    'research': {
        'entry': [],
        'exit': ['research_artifacts_exist'],  # .rapids/research/ has files
    },
    'analysis': {
        'entry': ['research_complete'],
        'exit': ['analysis_artifacts_exist'],
    },
    'plan': {
        'entry': ['analysis_complete'],
        'exit': ['spec_exists', 'feature_dag_valid', 'feature_specs_exist'],
    },
    'implement': {
        'entry': ['plan_complete', 'feature_dag_valid'],
        'exit': ['all_features_complete'],
    },
    'deploy': {
        'entry': ['implement_complete'],
        'exit': ['deployment_artifacts_exist'],
    },
    'sustain': {
        'entry': ['deploy_complete'],
        'exit': [],  # Ongoing, no exit
    },
}


class PhaseEngine:
    """RAPIDS phase state machine with entry/exit criteria checking."""

    def __init__(self, rapids_dir: Path, criteria_overrides: Optional[Dict] = None):
        """
        Args:
            rapids_dir: Path to the project's .rapids/ directory
            criteria_overrides: Plugin-provided criteria overrides per phase
        """
        self._rapids_dir = rapids_dir
        self._criteria = {}
        for phase, criteria in DEFAULT_CRITERIA.items():
            self._criteria[phase] = {**criteria}
        if criteria_overrides:
            for phase, overrides in criteria_overrides.items():
                if phase in self._criteria:
                    self._criteria[phase].update(overrides)

    def get_current_phase(self) -> str:
        """Read current phase from state.json."""
        state = self._read_state()
        return state.get('current_phase', 'research')

    def get_phase_status(self, phase: str) -> str:
        """Get status of a specific phase."""
        if phase not in PHASE_ORDER:
            raise ValueError(f"Invalid phase: {phase}. Must be one of {PHASE_ORDER}")
        state = self._read_state()
        phases = state.get('phases', {})
        phase_info = phases.get(phase, {})
        return phase_info.get('status', 'not_started')

    def get_all_phases(self) -> Dict[str, Dict]:
        """Get status of all phases."""
        state = self._read_state()
        phases = state.get('phases', {})
        result = {}
        for phase in PHASE_ORDER:
            result[phase] = phases.get(phase, {
                'status': 'not_started',
                'started_at': None,
                'completed_at': None,
            })
        return result

    def can_start_phase(self, phase: str) -> tuple[bool, List[str]]:
        """Check if a phase can be started. Returns (can_start, unmet_criteria)."""
        if phase not in PHASE_ORDER:
            raise ValueError(f"Invalid phase: {phase}. Must be one of {PHASE_ORDER}")
        entry_criteria = self._criteria.get(phase, {}).get('entry', [])
        unmet = self._check_criteria(entry_criteria)
        return (len(unmet) == 0, unmet)

    def can_complete_phase(self, phase: str) -> tuple[bool, List[str]]:
        """Check if a phase can be completed. Returns (can_complete, unmet_criteria)."""
        if phase not in PHASE_ORDER:
            raise ValueError(f"Invalid phase: {phase}. Must be one of {PHASE_ORDER}")
        exit_criteria = self._criteria.get(phase, {}).get('exit', [])
        unmet = self._check_criteria(exit_criteria)
        return (len(unmet) == 0, unmet)

    def start_phase(self, phase: str, force: bool = False) -> Dict:
        """Start a phase. Updates state.json. Returns updated phase info.
        Raises ValueError if entry criteria not met (unless force=True)."""
        if phase not in PHASE_ORDER:
            raise ValueError(f"Invalid phase: {phase}. Must be one of {PHASE_ORDER}")

        can_start, unmet = self.can_start_phase(phase)
        if not can_start and not force:
            raise ValueError(
                f"Cannot start phase '{phase}': unmet entry criteria: {unmet}"
            )

        state = self._read_state()
        now = datetime.now(timezone.utc).isoformat()

        if 'phases' not in state:
            state['phases'] = {}
        if phase not in state['phases']:
            state['phases'][phase] = {
                'status': 'not_started',
                'started_at': None,
                'completed_at': None,
            }

        state['phases'][phase]['status'] = 'in_progress'
        state['phases'][phase]['started_at'] = now
        state['current_phase'] = phase

        self._write_state(state)
        return state['phases'][phase]

    def complete_phase(self, phase: str, force: bool = False) -> Dict:
        """Complete a phase. Updates state.json. Returns updated phase info.
        Raises ValueError if exit criteria not met (unless force=True)."""
        if phase not in PHASE_ORDER:
            raise ValueError(f"Invalid phase: {phase}. Must be one of {PHASE_ORDER}")

        can_complete, unmet = self.can_complete_phase(phase)
        if not can_complete and not force:
            raise ValueError(
                f"Cannot complete phase '{phase}': unmet exit criteria: {unmet}"
            )

        state = self._read_state()
        now = datetime.now(timezone.utc).isoformat()

        if 'phases' not in state:
            state['phases'] = {}
        if phase not in state['phases']:
            state['phases'][phase] = {
                'status': 'not_started',
                'started_at': None,
                'completed_at': None,
            }

        state['phases'][phase]['status'] = 'completed'
        state['phases'][phase]['completed_at'] = now

        self._write_state(state)
        return state['phases'][phase]

    def advance_phase(self, force: bool = False) -> Dict:
        """Complete current phase and start the next one."""
        current = self.get_current_phase()
        next_phase = self.get_next_phase(current)

        if next_phase is None:
            raise ValueError(
                f"Cannot advance: '{current}' is the last phase in the RAPIDS workflow."
            )

        self.complete_phase(current, force=force)
        return self.start_phase(next_phase, force=force)

    def get_next_phase(self, current: str) -> Optional[str]:
        """Get the next phase in the sequence."""
        if current not in PHASE_TRANSITIONS:
            raise ValueError(f"Invalid phase: {current}. Must be one of {PHASE_ORDER}")
        return PHASE_TRANSITIONS[current]['next']

    def get_phase_index(self, phase: str) -> int:
        """Get the index of a phase (0-5)."""
        if phase not in PHASE_ORDER:
            raise ValueError(f"Invalid phase: {phase}. Must be one of {PHASE_ORDER}")
        return PHASE_ORDER.index(phase)

    def is_convergence_phase(self, phase: str) -> bool:
        """Returns True for RAP phases (research, analysis, plan)."""
        return phase in ('research', 'analysis', 'plan')

    def is_execution_phase(self, phase: str) -> bool:
        """Returns True for IDS phases (implement, deploy, sustain)."""
        return phase in ('implement', 'deploy', 'sustain')

    # -------------------------------------------------------------------------
    # Criteria checking
    # -------------------------------------------------------------------------

    def _check_criteria(self, criteria_list: List[str]) -> List[str]:
        """Check a list of criteria. Returns unmet criteria names."""
        unmet = []
        for criterion in criteria_list:
            # Map criterion names to checker methods
            if criterion == 'research_artifacts_exist':
                if not self._check_research_artifacts_exist():
                    unmet.append(criterion)
            elif criterion == 'analysis_artifacts_exist':
                if not self._check_analysis_artifacts_exist():
                    unmet.append(criterion)
            elif criterion == 'spec_exists':
                if not self._check_spec_exists():
                    unmet.append(criterion)
            elif criterion == 'feature_dag_valid':
                if not self._check_feature_dag_valid():
                    unmet.append(criterion)
            elif criterion == 'feature_specs_exist':
                if not self._check_feature_specs_exist():
                    unmet.append(criterion)
            elif criterion == 'all_features_complete':
                if not self._check_all_features_complete():
                    unmet.append(criterion)
            elif criterion == 'deployment_artifacts_exist':
                if not self._check_deployment_artifacts_exist():
                    unmet.append(criterion)
            elif criterion.endswith('_complete'):
                # Generic phase completion check: e.g. research_complete -> research
                phase_name = criterion.replace('_complete', '')
                if phase_name in PHASE_ORDER:
                    if not self._check_phase_complete(phase_name):
                        unmet.append(criterion)
                else:
                    # Unknown criterion, treat as unmet
                    unmet.append(criterion)
            else:
                # Unknown criterion, treat as unmet
                unmet.append(criterion)
        return unmet

    def _check_research_artifacts_exist(self) -> bool:
        """Check that .rapids/research/ directory has files."""
        research_dir = self._rapids_dir / 'research'
        if not research_dir.exists():
            return False
        files = [f for f in research_dir.iterdir() if f.is_file()]
        return len(files) > 0

    def _check_analysis_artifacts_exist(self) -> bool:
        """Check that .rapids/analysis/ directory has files."""
        analysis_dir = self._rapids_dir / 'analysis'
        if not analysis_dir.exists():
            return False
        files = [f for f in analysis_dir.iterdir() if f.is_file()]
        return len(files) > 0

    def _check_spec_exists(self) -> bool:
        """Check that .rapids/plan/spec.md exists."""
        spec_path = self._rapids_dir / 'plan' / 'spec.md'
        return spec_path.exists() and spec_path.stat().st_size > 0

    def _check_feature_dag_valid(self) -> bool:
        """Check that features exist for the project.

        Returns True here — the actual validation happens in the API layer
        which queries the database (the single source of truth for features).
        The phase engine no longer reads feature_dag.json.
        """
        return True

    def _check_feature_specs_exist(self) -> bool:
        """Check that .rapids/features/ directory has spec files."""
        features_dir = self._rapids_dir / 'features'
        if not features_dir.exists():
            return False
        # Check for any files or subdirectories with content
        items = list(features_dir.iterdir())
        return len(items) > 0

    def _check_all_features_complete(self) -> bool:
        """Check that all features are complete.

        Returns True here — the actual enforcement happens in the API layer
        which queries the database (the single source of truth for features).
        The phase engine no longer reads feature_dag.json.
        """
        return True

    def _check_deployment_artifacts_exist(self) -> bool:
        """Check that .rapids/deploy/ directory has files."""
        deploy_dir = self._rapids_dir / 'deploy'
        if not deploy_dir.exists():
            return False
        files = [f for f in deploy_dir.iterdir() if f.is_file()]
        return len(files) > 0

    def _check_phase_complete(self, phase: str) -> bool:
        """Check if a specific phase has been completed."""
        if phase not in PHASE_ORDER:
            return False
        state = self._read_state()
        phases = state.get('phases', {})
        phase_info = phases.get(phase, {})
        return phase_info.get('status') == 'completed'

    # -------------------------------------------------------------------------
    # State file I/O
    # -------------------------------------------------------------------------

    def _read_state(self) -> Dict:
        """Read state.json from .rapids/"""
        state_path = self._rapids_dir / 'state.json'
        if not state_path.exists():
            return self._default_state()
        try:
            with open(state_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return self._default_state()

    def _write_state(self, state: Dict) -> None:
        """Write state.json to .rapids/"""
        self._rapids_dir.mkdir(parents=True, exist_ok=True)
        state_path = self._rapids_dir / 'state.json'
        with open(state_path, 'w') as f:
            json.dump(state, f, indent=2)

    def _default_state(self) -> Dict:
        """Return a default state dictionary."""
        return {
            'project_id': None,
            'archetype': None,
            'plugin': None,
            'current_phase': 'research',
            'phases': {
                phase: {
                    'status': 'not_started',
                    'started_at': None,
                    'completed_at': None,
                }
                for phase in PHASE_ORDER
            },
        }
