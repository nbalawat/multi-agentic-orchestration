"""
Autonomous Executor

Executes features from the DAG with fresh-context agent sessions.
Inspired by Anthropic's autonomous-coding quickstart pattern.

Each feature gets its own agent with:
- Fresh context (no conversation history pollution)
- The project specification for global context
- The specific feature spec with acceptance criteria
- Current project state (git log, completed features)
"""

import asyncio
import uuid
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from .feature_dag import FeatureDAG, FeatureNode
from .project_state import ProjectState
from .git_worktree import GitWorktreeManager
from .logger import OrchestratorLogger


class FeatureExecution(BaseModel):
    """Tracks a single feature's execution state."""

    feature_id: str
    agent_name: str
    agent_id: Optional[str] = None
    worktree_path: Optional[str] = None  # Git worktree path for this feature
    worktree_branch: Optional[str] = None  # Git branch name for this feature
    status: str = "pending"  # pending, running, complete, failed
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None


class AutonomousExecutor:
    """Executes features from DAG with fresh-context agent sessions."""

    def __init__(
        self,
        project_state: ProjectState,
        dag: FeatureDAG,
        agent_create_fn: Callable,  # async fn(name, system_prompt, model, working_dir) -> agent_id
        agent_command_fn: Callable,  # async fn(agent_name, command) -> result
        agent_status_fn: Callable,  # async fn(agent_name) -> status dict
        repo_path: Optional[str] = None,
        logger: Optional[OrchestratorLogger] = None,
        max_parallel: int = 3,
        use_worktrees: bool = True,
    ):
        self._project_state = project_state
        self._dag = dag
        self._create_agent = agent_create_fn
        self._command_agent = agent_command_fn
        self._check_status = agent_status_fn
        self._logger = logger
        self._max_parallel = max_parallel
        self._use_worktrees = use_worktrees
        self._executions: Dict[str, FeatureExecution] = {}
        self._running_count = 0
        self._stop_requested = False

        # Git worktree manager for parallel feature isolation
        self._git_mgr: Optional[GitWorktreeManager] = None
        if repo_path and use_worktrees:
            self._git_mgr = GitWorktreeManager(repo_path)
            self._git_mgr.ensure_git_repo()

    # ------------------------------------------------------------------
    #  Logging helpers
    # ------------------------------------------------------------------

    def _log_info(self, msg: str) -> None:
        if self._logger:
            self._logger.info(msg)

    def _log_error(self, msg: str, exc_info: bool = False) -> None:
        if self._logger:
            self._logger.error(msg, exc_info=exc_info)

    def _log_warning(self, msg: str) -> None:
        if self._logger:
            self._logger.warning(msg)

    # ------------------------------------------------------------------
    #  Prompt construction
    # ------------------------------------------------------------------

    def build_feature_prompt(self, feature: FeatureNode) -> str:
        """
        Build the fresh-context prompt for a feature agent.

        Includes:
        - Project specification (from .rapids/plan/spec.md)
        - Feature spec (from .rapids/features/<feat_id>/spec.md or similar)
        - Acceptance criteria
        - List of completed features (context of what's been built)
        - Instructions to implement and verify
        """
        sections: List[str] = []

        # --- Section 1: Project specification ---
        project_spec = self._project_state.read_spec()
        if project_spec:
            sections.append(
                "## Project Specification\n\n"
                "Below is the full project specification. Use it to understand "
                "the overall architecture, conventions, and goals.\n\n"
                f"{project_spec}"
            )
        else:
            sections.append(
                "## Project Specification\n\n"
                "No project specification found at .rapids/plan/spec.md. "
                "Proceed using your best judgement based on the feature details below."
            )

        # --- Section 2: Feature specification file (if any) ---
        feature_spec_content: Optional[str] = None
        if feature.spec_file:
            # spec_file is relative to .rapids/features/<feature_id>/
            feature_spec_content = self._project_state.read_feature_spec(
                feature.id, feature.spec_file
            )
        else:
            # Try common filenames
            for candidate in ("spec.md", "README.md", "feature.md"):
                content = self._project_state.read_feature_spec(feature.id, candidate)
                if content:
                    feature_spec_content = content
                    break

        if feature_spec_content:
            sections.append(
                f"## Feature Specification: {feature.name}\n\n"
                f"{feature_spec_content}"
            )

        # --- Section 3: Feature metadata and acceptance criteria ---
        meta_lines = [
            f"## Feature Details\n",
            f"- **Feature ID:** {feature.id}",
            f"- **Name:** {feature.name}",
        ]
        if feature.description:
            meta_lines.append(f"- **Description:** {feature.description}")
        if feature.category:
            meta_lines.append(f"- **Category:** {feature.category}")
        if feature.estimated_complexity:
            meta_lines.append(f"- **Estimated Complexity:** {feature.estimated_complexity}")
        if feature.depends_on:
            meta_lines.append(f"- **Dependencies:** {', '.join(feature.depends_on)}")

        if feature.acceptance_criteria:
            meta_lines.append("\n### Acceptance Criteria\n")
            for i, criterion in enumerate(feature.acceptance_criteria, 1):
                meta_lines.append(f"{i}. {criterion}")

        sections.append("\n".join(meta_lines))

        # --- Section 4: Completed features (what's already been built) ---
        completed_features = [
            f for f in self._dag.list_features() if f.status == "complete"
        ]
        if completed_features:
            completed_lines = ["## Already Completed Features\n"]
            completed_lines.append(
                "The following features have already been implemented. "
                "Your work may build on or integrate with them.\n"
            )
            for cf in completed_features:
                completed_lines.append(f"- **{cf.name}** (`{cf.id}`): {cf.description or 'N/A'}")
            sections.append("\n".join(completed_lines))
        else:
            sections.append(
                "## Already Completed Features\n\n"
                "No features have been completed yet. You are working on one of the first features."
            )

        # --- Section 5: In-progress features (parallel awareness) ---
        in_progress_features = [
            f
            for f in self._dag.list_features()
            if f.status == "in_progress" and f.id != feature.id
        ]
        if in_progress_features:
            ip_lines = ["## Currently In-Progress Features\n"]
            ip_lines.append(
                "These features are being worked on in parallel by other agents. "
                "Avoid conflicting changes where possible.\n"
            )
            for ipf in in_progress_features:
                ip_lines.append(f"- **{ipf.name}** (`{ipf.id}`): {ipf.description or 'N/A'}")
            sections.append("\n".join(ip_lines))

        # --- Section 6: Implementation instructions ---
        sections.append(
            "## Implementation Instructions\n\n"
            "1. **Read the codebase** to understand the current project structure before making changes.\n"
            "2. **Implement the feature** according to the specification and acceptance criteria above.\n"
            "3. **Follow existing code conventions** (naming, file structure, patterns) found in the project.\n"
            "4. **Write tests** if the project has a testing framework set up.\n"
            "5. **Verify your work** by running any relevant tests or build commands.\n"
            "6. **Commit your changes** with a clear commit message referencing the feature ID.\n\n"
            "When you are finished, provide a summary of what was implemented and "
            "confirm that all acceptance criteria have been met."
        )

        return "\n\n---\n\n".join(sections)

    # ------------------------------------------------------------------
    #  Single-feature execution
    # ------------------------------------------------------------------

    async def execute_feature(self, feature_id: str) -> FeatureExecution:
        """
        Execute a single feature:
        1. Load feature from DAG
        2. Build fresh-context prompt
        3. Create agent with unique name
        4. Command agent with feature prompt
        5. Return execution tracking object
        """
        feature = self._dag.get_feature(feature_id)
        if feature is None:
            raise KeyError(f"Feature '{feature_id}' not found in the DAG.")

        # Generate a unique agent name for this feature execution
        short_id = uuid.uuid4().hex[:6]
        agent_name = f"feat-{feature_id}-{short_id}"

        # Create execution tracker
        execution = FeatureExecution(
            feature_id=feature_id,
            agent_name=agent_name,
            status="pending",
        )
        self._executions[feature_id] = execution

        try:
            # Mark in-progress in DAG
            self._dag.mark_in_progress(feature_id, agent_id=agent_name)

            # Create git worktree for isolated parallel execution
            working_dir = None
            if self._git_mgr and self._use_worktrees:
                try:
                    worktree_path = self._git_mgr.create_worktree(feature_id)
                    working_dir = str(worktree_path)
                    execution.worktree_path = working_dir
                    execution.worktree_branch = f"rapids/{feature_id}"
                    self._log_info(
                        f"Created git worktree for feature '{feature_id}' at {working_dir}"
                    )
                except Exception as wt_err:
                    self._log_warning(
                        f"Failed to create worktree for '{feature_id}', "
                        f"falling back to main repo: {wt_err}"
                    )

            # Build the system prompt for fresh context
            system_prompt = (
                "You are an expert software engineer implementing a specific feature "
                "for a project. You have been given the project specification, feature "
                "details, and acceptance criteria. Implement the feature thoroughly, "
                "following the project's existing conventions."
            )
            if execution.worktree_branch:
                system_prompt += (
                    f"\n\nYou are working in a git worktree on branch '{execution.worktree_branch}'. "
                    "Commit your changes to this branch when done."
                )

            # Build the comprehensive feature prompt
            feature_prompt = self.build_feature_prompt(feature)

            # Create agent with fresh context, using worktree as working dir
            self._log_info(f"Creating agent '{agent_name}' for feature '{feature.name}'")
            agent_id = await self._create_agent(
                agent_name, system_prompt, None, working_dir
            )

            execution.agent_id = str(agent_id) if agent_id else None
            execution.status = "running"
            execution.started_at = datetime.now(timezone.utc).isoformat()
            self._running_count += 1

            # Command the agent with the feature prompt
            self._log_info(
                f"Dispatching feature '{feature.name}' to agent '{agent_name}'"
            )
            await self._command_agent(agent_name, feature_prompt)

            return execution

        except Exception as e:
            self._log_error(
                f"Failed to execute feature '{feature_id}': {e}", exc_info=True
            )
            execution.status = "failed"
            execution.error = str(e)
            execution.completed_at = datetime.now(timezone.utc).isoformat()
            # Revert DAG state on launch failure
            try:
                self._dag.mark_blocked(feature_id, reason=f"Launch failed: {e}")
            except Exception:
                pass
            return execution

    # ------------------------------------------------------------------
    #  Batch execution of ready features
    # ------------------------------------------------------------------

    async def execute_ready_features(self) -> List[FeatureExecution]:
        """
        Find and execute all ready features (up to max_parallel).
        Returns list of started executions.
        """
        ready_ids = self._dag.get_ready_features()
        if not ready_ids:
            self._log_info("No features are ready for execution.")
            return []

        # Calculate how many slots are available
        available_slots = self._max_parallel - self._running_count
        if available_slots <= 0:
            self._log_info(
                f"All {self._max_parallel} parallel slots are occupied. "
                f"Waiting for completions."
            )
            return []

        # Take up to available_slots features, ordered by priority
        features_to_run = []
        for fid in ready_ids:
            if len(features_to_run) >= available_slots:
                break
            # Skip features that already have an execution tracker in running state
            existing = self._executions.get(fid)
            if existing and existing.status == "running":
                continue
            features_to_run.append(fid)

        if not features_to_run:
            return []

        self._log_info(
            f"Launching {len(features_to_run)} feature(s): "
            f"{', '.join(features_to_run)}"
        )

        # Launch features concurrently
        tasks = [self.execute_feature(fid) for fid in features_to_run]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        executions: List[FeatureExecution] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                fid = features_to_run[i]
                self._log_error(f"Exception launching feature '{fid}': {result}")
                # Create a failed execution record
                execution = FeatureExecution(
                    feature_id=fid,
                    agent_name=f"feat-{fid}-failed",
                    status="failed",
                    error=str(result),
                    completed_at=datetime.now(timezone.utc).isoformat(),
                )
                self._executions[fid] = execution
                executions.append(execution)
            else:
                executions.append(result)

        return executions

    # ------------------------------------------------------------------
    #  Completion / failure handlers
    # ------------------------------------------------------------------

    async def on_feature_complete(self, feature_id: str) -> List[str]:
        """
        Handle feature completion:
        1. Mark complete in DAG
        2. Save updated DAG
        3. Update execution tracking
        4. Return newly-unblocked feature IDs
        """
        self._log_info(f"Feature '{feature_id}' completed successfully.")

        # Mark complete in DAG (returns newly-ready feature IDs)
        newly_ready = self._dag.mark_complete(feature_id)

        # Persist DAG to disk
        try:
            self._dag.save()
        except Exception as e:
            self._log_error(f"Failed to save DAG after completing '{feature_id}': {e}")

        # Update execution tracker
        execution = self._executions.get(feature_id)
        if execution:
            execution.status = "complete"
            execution.completed_at = datetime.now(timezone.utc).isoformat()

            # Merge worktree branch back to main and clean up
            if execution.worktree_path and self._git_mgr:
                try:
                    success, msg = self._git_mgr.merge_worktree(
                        feature_id, delete_after=True
                    )
                    if success:
                        self._log_info(f"Merged worktree for '{feature_id}': {msg}")
                    else:
                        self._log_warning(
                            f"Worktree merge issue for '{feature_id}': {msg}"
                        )
                except Exception as merge_err:
                    self._log_warning(
                        f"Failed to merge worktree for '{feature_id}': {merge_err}"
                    )

        # Decrement running count
        self._running_count = max(0, self._running_count - 1)

        if newly_ready:
            self._log_info(
                f"Newly unblocked features after '{feature_id}': "
                f"{', '.join(newly_ready)}"
            )

        completion_pct = self._dag.completion_percentage()
        self._log_info(f"DAG completion: {completion_pct:.1f}%")

        return newly_ready

    async def on_feature_failed(self, feature_id: str, error: str) -> None:
        """Handle feature failure. Mark blocked in DAG."""
        self._log_error(f"Feature '{feature_id}' failed: {error}")

        # Mark blocked in DAG
        try:
            self._dag.mark_blocked(feature_id, reason=error)
        except Exception as e:
            self._log_error(
                f"Failed to mark '{feature_id}' as blocked: {e}"
            )

        # Persist DAG
        try:
            self._dag.save()
        except Exception as e:
            self._log_error(f"Failed to save DAG after failure of '{feature_id}': {e}")

        # Update execution tracker
        execution = self._executions.get(feature_id)
        if execution:
            execution.status = "failed"
            execution.error = error
            execution.completed_at = datetime.now(timezone.utc).isoformat()

        # Decrement running count
        self._running_count = max(0, self._running_count - 1)

    # ------------------------------------------------------------------
    #  Status checking for running agents
    # ------------------------------------------------------------------

    async def _check_running_features(self) -> None:
        """
        Poll status of all currently-running feature agents.
        Handle completions and failures detected via agent status.
        """
        running_executions = [
            ex for ex in self._executions.values() if ex.status == "running"
        ]

        for execution in running_executions:
            try:
                status = await self._check_status(execution.agent_name)

                if status is None:
                    # Agent not found; treat as failure
                    await self.on_feature_failed(
                        execution.feature_id,
                        "Agent not found during status check",
                    )
                    continue

                agent_status = status.get("status", "unknown")

                if agent_status in ("completed", "done", "idle"):
                    # Agent finished its work
                    await self.on_feature_complete(execution.feature_id)

                elif agent_status in ("failed", "error"):
                    error_msg = status.get("error", "Agent reported failure")
                    await self.on_feature_failed(execution.feature_id, error_msg)

                # "running" / "busy" / other => still working, do nothing

            except Exception as e:
                self._log_error(
                    f"Error checking status of '{execution.agent_name}': {e}",
                    exc_info=True,
                )

    # ------------------------------------------------------------------
    #  Main execution loop
    # ------------------------------------------------------------------

    async def run_loop(
        self,
        auto_continue: bool = True,
        poll_interval: float = 10.0,
    ) -> Dict:
        """
        Main autonomous execution loop:
        1. While DAG has incomplete features and not stopped:
           a. Execute ready features (up to max_parallel)
           b. Wait for poll_interval
           c. Check status of running features
           d. Handle completions/failures
           e. Continue with newly-ready features
        2. Return final status summary

        This is the equivalent of the quickstart's run_autonomous_agent loop.
        """
        self._stop_requested = False
        loop_iterations = 0

        self._log_info(
            f"Starting autonomous execution loop "
            f"(max_parallel={self._max_parallel}, poll_interval={poll_interval}s)"
        )

        try:
            while not self._stop_requested:
                loop_iterations += 1

                # Check if DAG is fully complete
                if self._dag.is_complete:
                    self._log_info("All features in DAG are complete. Execution finished.")
                    break

                # Check if there is anything left to do
                summary = self._dag.status_summary()
                actionable = summary.get("planned", 0) + summary.get("in_progress", 0)
                if actionable == 0:
                    self._log_warning(
                        "No planned or in-progress features remain. "
                        "Some features may be blocked or deferred."
                    )
                    break

                # Launch ready features
                launched = await self.execute_ready_features()
                if launched:
                    self._log_info(
                        f"Iteration {loop_iterations}: launched {len(launched)} feature(s)"
                    )

                # Wait before polling
                await asyncio.sleep(poll_interval)

                # Check on running agents
                await self._check_running_features()

                # If auto_continue is False, only run one iteration
                if not auto_continue:
                    break

        except asyncio.CancelledError:
            self._log_warning("Execution loop was cancelled.")
        except Exception as e:
            self._log_error(f"Execution loop error: {e}", exc_info=True)

        # Build final summary
        final_summary = self.get_status()
        final_summary["loop_iterations"] = loop_iterations
        self._log_info(
            f"Execution loop ended after {loop_iterations} iteration(s). "
            f"Status: {final_summary.get('dag_summary', {})}"
        )
        return final_summary

    # ------------------------------------------------------------------
    #  Control
    # ------------------------------------------------------------------

    def request_stop(self) -> None:
        """Request the execution loop to stop after current features complete."""
        self._log_info("Stop requested. Will halt after current features finish.")
        self._stop_requested = True

    # ------------------------------------------------------------------
    #  Status & history
    # ------------------------------------------------------------------

    def get_status(self) -> Dict:
        """Get current execution status: running features, completed, remaining, etc."""
        running = [
            ex.model_dump()
            for ex in self._executions.values()
            if ex.status == "running"
        ]
        completed = [
            ex.model_dump()
            for ex in self._executions.values()
            if ex.status == "complete"
        ]
        failed = [
            ex.model_dump()
            for ex in self._executions.values()
            if ex.status == "failed"
        ]

        return {
            "running_features": running,
            "completed_features": completed,
            "failed_features": failed,
            "running_count": self._running_count,
            "max_parallel": self._max_parallel,
            "stop_requested": self._stop_requested,
            "dag_summary": self._dag.status_summary(),
            "dag_completion_pct": self._dag.completion_percentage(),
            "dag_is_complete": self._dag.is_complete,
        }

    def get_execution_history(self) -> List[Dict]:
        """Get history of all feature executions."""
        return [ex.model_dump() for ex in self._executions.values()]

    @property
    def is_running(self) -> bool:
        """True if there are features currently being executed."""
        return self._running_count > 0

    @property
    def is_complete(self) -> bool:
        """True if the DAG is fully complete or no more work can be done."""
        if self._dag.is_complete:
            return True
        summary = self._dag.status_summary()
        actionable = summary.get("planned", 0) + summary.get("in_progress", 0)
        return actionable == 0
