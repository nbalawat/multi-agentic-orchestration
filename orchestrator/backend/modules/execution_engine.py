"""
Execution Engine

Single module that owns the entire feature execution lifecycle.
Replaces the scattered logic across agent_manager hooks, auto_merge,
cleanup hooks, and builder_registry.

Flow:
1. execute_features() → creates agents, inserts execution_runs
2. _dispatch_feature() → awaits command_agent, then runs validation + cleanup
3. get_execution_status() → single API for frontend polling
"""

import asyncio
import json
import logging
import subprocess
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from . import config
from .feature_dag import FeatureDAG

logger = logging.getLogger(__name__)

# Base URL for internal API calls
_API_BASE = f"http://{config.BACKEND_HOST}:{config.BACKEND_PORT}"


class ExecutionEngine:
    """Manages the lifecycle of feature execution runs."""

    def __init__(self, agent_manager, ws_manager):
        self.agent_manager = agent_manager
        self.ws_manager = ws_manager
        self._running_tasks: Dict[str, asyncio.Task] = {}  # feature_id → dispatch task

    async def execute_features(
        self,
        project_id: str,
        max_parallel: int = 3,
    ) -> Dict[str, Any]:
        """
        Execute ready features by creating builder agents.
        Returns summary of what was started.
        """
        from .database import get_connection
        from .rapids_database import load_dag_features
        from .project_context import ProjectContextManager

        pid = _uuid.UUID(project_id)

        # Load DAG to find ready features
        dag = await FeatureDAG.from_database(project_id)
        ready_ids = dag.get_ready_features()

        if not ready_ids:
            summary = dag.status_summary()
            return {
                "started": 0,
                "message": f"No ready features. {summary.get('complete', 0)}/{dag.feature_count} complete.",
            }

        # Filter out features that already have active runs
        async with get_connection() as conn:
            active_rows = await conn.fetch(
                "SELECT feature_id FROM execution_runs WHERE project_id = $1 AND status IN ('queued', 'building', 'testing')",
                pid,
            )
        active_feature_ids = {str(r["feature_id"]) for r in active_rows}
        ready_ids = [fid for fid in ready_ids if fid not in active_feature_ids]

        if not ready_ids:
            return {"started": 0, "message": "All ready features already have active runs."}

        # Limit parallelism
        features_to_run = [dag._features[fid] for fid in ready_ids[:max_parallel] if fid in dag._features]

        # Get project info
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{_API_BASE}/api/projects/{project_id}", timeout=15.0)
            proj_data = resp.json()
        project_info = proj_data.get("project", proj_data.get("data", {}))
        repo_path = project_info.get("repo_path", ".")
        project_name = project_info.get("name", "unknown")
        archetype = project_info.get("archetype", "")

        # Initialize project context
        ctx_mgr = ProjectContextManager(repo_path, project_name)
        project_context = ctx_mgr.get_context_for_prompt()

        # Read project spec
        spec_content = ""
        for spec_name in ["specification.md", "spec.md"]:
            spec_path = Path(repo_path) / ".rapids" / "plan" / spec_name
            if spec_path.exists():
                spec_content = spec_path.read_text()[:3000]
                break

        # Compute wave number
        groups = dag.get_parallel_groups()
        feature_waves = {}
        for wave_num, group in enumerate(groups):
            for fid in group:
                feature_waves[fid] = wave_num

        # Start features concurrently via asyncio.gather (same pattern as old code that worked)
        async def _safe_start(feature):
            try:
                run_id = await self._start_feature(
                    project_id=project_id,
                    feature=feature,
                    repo_path=repo_path,
                    project_name=project_name,
                    archetype=archetype,
                    spec_content=spec_content,
                    project_context=project_context,
                    wave_number=feature_waves.get(feature.id, 0),
                    ctx_mgr=ctx_mgr,
                )
                return {"feature": feature.name, "run_id": str(run_id)}
            except Exception as e:
                logger.error(f"[ExecutionEngine] Failed to start '{feature.name}': {e}")
                return {"feature": feature.name, "error": str(e)}

        results = await asyncio.gather(*[_safe_start(f) for f in features_to_run])

        return {
            "started": len([r for r in results if "error" not in r]),
            "runs": list(results),
            "message": f"Started {len(results)} features.",
        }

    async def _start_feature(
        self,
        project_id: str,
        feature,
        repo_path: str,
        project_name: str,
        archetype: str,
        spec_content: str,
        project_context: str,
        wave_number: int,
        ctx_mgr,
    ) -> _uuid.UUID:
        """Start a single feature: create run, agent, dispatch."""
        from .database import get_connection
        from .rapids_database import update_feature_dag_status

        pid = _uuid.UUID(project_id)
        fid = _uuid.UUID(feature.id) if len(feature.id) > 8 else None

        # Read per-feature spec
        feature_spec = ""
        for spec_dir in [
            Path(repo_path) / ".rapids" / "plan" / "features" / feature.id,
            Path(repo_path) / ".rapids" / "plan" / "features" / feature.name,
        ]:
            spec_file = spec_dir / "spec.md"
            if spec_file.exists():
                feature_spec = spec_file.read_text()
                break

        # Build agent prompt
        acceptance_text = "\n".join(f"  - {c}" for c in feature.acceptance_criteria) if feature.acceptance_criteria else "No specific criteria defined."
        agent_name = f"builder-{feature.name}"[:40]

        prompt = (
            f"# Feature Builder Agent — {feature.name}\n\n"
            f"You are implementing a single feature for the **{project_name}** project.\n\n"
            f"## Feature\n"
            f"**Name:** {feature.name}\n"
            f"**Description:** {feature.description or 'No description'}\n\n"
            f"## Acceptance Criteria\n{acceptance_text}\n\n"
            f"## Working Directory\n`{repo_path}`\n\n"
        )
        if project_context:
            prompt += f"{project_context}\n\n"
        if spec_content:
            prompt += f"## Project Specification (excerpt)\n{spec_content}\n\n"
        if feature_spec:
            prompt += f"## Feature Specification\n{feature_spec}\n\n"
        prompt += (
            f"## Instructions\n"
            f"1. Read the project context and feature spec carefully\n"
            f"2. Implement the feature following project conventions\n"
            f"3. Write tests covering all acceptance criteria\n"
            f"4. Run tests and ensure they pass\n"
            f"5. When done, summarize what you implemented and which files you changed\n"
        )

        # 1. Insert execution run
        run_id = _uuid.uuid4()
        async with get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO execution_runs (id, project_id, feature_id, feature_name, agent_name, status, wave_number, created_at)
                VALUES ($1, $2, $3, $4, $5, 'queued', $6, NOW())
                """,
                run_id, pid, fid or _uuid.UUID(feature.id), feature.name, agent_name, wave_number,
            )

        # 2. Create agent
        result = await self.agent_manager.create_agent(
            name=agent_name,
            system_prompt=prompt,
            model=config.get_model_for_phase("implement"),
            phase_metadata={
                "phase": "implement",
                "project_id": project_id,
                "archetype": archetype,
            },
        )
        agent_id_str = result.get("agent_id") if isinstance(result, dict) else None
        if not agent_id_str:
            raise RuntimeError(f"Agent creation failed: {result}")

        agent_id = _uuid.UUID(agent_id_str)

        # 3. Update run → building, feature → in_progress
        async with get_connection() as conn:
            await conn.execute(
                "UPDATE execution_runs SET status = 'building', agent_id = $1, started_at = NOW() WHERE id = $2",
                agent_id, run_id,
            )
        await update_feature_dag_status(pid, feature.id, "in_progress", assigned_agent=agent_name)

        logger.info(f"[ExecutionEngine] Started: {feature.name} → agent={agent_name}, run={run_id}")

        # 4. Broadcast feature_started
        await self.ws_manager.broadcast({
            "type": "feature_started",
            "data": {
                "project_id": project_id,
                "feature_id": feature.id,
                "feature_name": feature.name,
                "agent_name": agent_name,
            }
        })

        # 5. Dispatch agent command — await in a background task
        task = asyncio.create_task(
            self._dispatch_and_complete(
                run_id=run_id,
                project_id=project_id,
                feature=feature,
                agent_id=agent_id,
                agent_name=agent_name,
                repo_path=repo_path,
                ctx_mgr=ctx_mgr,
            )
        )
        self._running_tasks[feature.id] = task

        return run_id

    async def _dispatch_and_complete(
        self,
        run_id: _uuid.UUID,
        project_id: str,
        feature,
        agent_id: _uuid.UUID,
        agent_name: str,
        repo_path: str,
        ctx_mgr,
    ):
        """
        Dispatch command_agent and handle EVERYTHING after it returns.
        This is the single sequential cleanup path — no hooks, no races.
        """
        from .database import get_connection, delete_agent
        from .rapids_database import update_feature_dag_status

        pid = _uuid.UUID(project_id)
        error_message = None

        try:
            # Execute the agent
            logger.info(f"[ExecutionEngine] Dispatching: {agent_name}")
            await self.agent_manager.command_agent(
                agent_id=agent_id,
                command=f"Implement the '{feature.name}' feature. Follow the spec and acceptance criteria. Run tests when done.",
            )
            logger.info(f"[ExecutionEngine] Agent completed: {agent_name}")

        except Exception as e:
            error_message = str(e)
            logger.error(f"[ExecutionEngine] Agent failed: {agent_name}: {e}")

        # === SEQUENTIAL CLEANUP — everything happens here ===

        try:
            # 1. Update run → testing
            async with get_connection() as conn:
                await conn.execute(
                    "UPDATE execution_runs SET status = 'testing', updated_at = NOW() WHERE id = $1",
                    run_id,
                )

            # 2. Get agent cost from DB
            async with get_connection() as conn:
                agent_row = await conn.fetchrow(
                    "SELECT input_tokens, output_tokens, total_cost FROM agents WHERE id = $1",
                    agent_id,
                )
            cost_data = dict(agent_row) if agent_row else {"input_tokens": 0, "output_tokens": 0, "total_cost": 0}

            # 3. Validate: check files changed
            files_changed = self._get_changed_files(repo_path)
            test_results = {"passed": 0, "failed": 0, "skipped": 0, "errors": [], "output": ""}

            if error_message:
                test_results["errors"].append(f"Agent error: {error_message}")

            # 4. Run tests
            test_command = ctx_mgr.load().test_command if ctx_mgr else ""
            if test_command and not error_message:
                try:
                    test_output = await self._run_tests(repo_path, test_command)
                    test_results = self._parse_test_results(test_output)
                    test_results["output"] = test_output[-2000:]
                except Exception as test_err:
                    test_results["errors"].append(f"Test execution failed: {test_err}")

            # 5. Determine final status
            is_success = not error_message and len(test_results["errors"]) == 0 and test_results["failed"] == 0
            final_status = "complete" if is_success else "failed"

            # 6. Update execution run
            async with get_connection() as conn:
                await conn.execute(
                    """
                    UPDATE execution_runs
                    SET status = $1, completed_at = NOW(),
                        input_tokens = $2, output_tokens = $3, total_cost = $4,
                        test_results = $5, files_changed = $6, error_message = $7,
                        updated_at = NOW()
                    WHERE id = $8
                    """,
                    final_status,
                    cost_data.get("input_tokens", 0),
                    cost_data.get("output_tokens", 0),
                    float(cost_data.get("total_cost", 0)),
                    json.dumps(test_results),
                    json.dumps(files_changed),
                    error_message,
                    run_id,
                )

            # 7. Update feature status
            feature_status = "complete" if is_success else "blocked"
            await update_feature_dag_status(pid, feature.id, feature_status, assigned_agent=agent_name)
            logger.info(f"[ExecutionEngine] Feature '{feature.name}' → {feature_status}")

            # 8. Archive agent
            try:
                from .database import update_agent_status
                await update_agent_status(agent_id, "completed")
                await delete_agent(agent_id)
                logger.info(f"[ExecutionEngine] Agent '{agent_name}' archived")
            except Exception as del_err:
                logger.warning(f"[ExecutionEngine] Agent archive failed: {del_err}")

            # 9. Update project context
            if is_success and ctx_mgr:
                try:
                    ctx_mgr.update_after_feature(feature.name, agent_name, files_changed)
                except Exception as ctx_err:
                    logger.warning(f"[ExecutionEngine] Context update failed: {ctx_err}")

            # 10. Broadcast events
            await self.ws_manager.broadcast({
                "type": "feature_merged",
                "data": {
                    "project_id": project_id,
                    "feature_id": feature.id,
                    "feature_name": feature.name,
                    "agent_name": agent_name,
                    "success": is_success,
                    "test_results": test_results,
                    "cost": float(cost_data.get("total_cost", 0)),
                }
            })

            await self.ws_manager.broadcast({
                "type": "agent_deleted",
                "data": {"agent_id": str(agent_id), "agent_name": agent_name},
            })

            # 11. Check DAG progress + auto-execute next wave
            dag = await FeatureDAG.from_database(project_id)
            summary = dag.status_summary()
            total = dag.feature_count
            completed = summary.get("complete", 0)
            ready = dag.get_ready_features()

            await self.ws_manager.broadcast({
                "type": "dag_progress",
                "data": {
                    "project_id": project_id,
                    "total": total,
                    "completed": completed,
                    "in_progress": summary.get("in_progress", 0),
                    "ready": len(ready),
                }
            })

            # Chat notification
            test_str = ""
            if test_results.get("passed", 0) > 0 or test_results.get("failed", 0) > 0:
                test_str = f" ({test_results['passed']} passed, {test_results['failed']} failed)"
            icon = "✅" if is_success else "❌"
            await self.ws_manager.broadcast({
                "type": "orchestrator_chat",
                "message": {
                    "id": str(_uuid.uuid4()),
                    "orchestrator_agent_id": str(self.agent_manager.orchestrator_agent_id),
                    "sender_type": "system",
                    "receiver_type": "user",
                    "message": f"{icon} **{feature.name}** — {final_status}{test_str} | ${float(cost_data.get('total_cost', 0)):.3f}",
                    "agent_id": None,
                    "metadata": {"event": "feature_" + final_status},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            })

            if completed == total and total > 0:
                await self.ws_manager.broadcast({
                    "type": "dag_complete",
                    "data": {"project_id": project_id, "total": total},
                })
                await self.ws_manager.broadcast({
                    "type": "orchestrator_chat",
                    "message": {
                        "id": str(_uuid.uuid4()),
                        "orchestrator_agent_id": str(self.agent_manager.orchestrator_agent_id),
                        "sender_type": "system",
                        "receiver_type": "user",
                        "message": f"🎉 **All {total} features complete!** Ready to advance to Deploy.",
                        "agent_id": None,
                        "metadata": {"event": "dag_complete"},
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                })
            elif ready and is_success:
                # Auto-execute next wave
                logger.info(f"[ExecutionEngine] Auto-executing next wave: {len(ready)} features ready")
                asyncio.create_task(self.execute_features(project_id))

        except Exception as cleanup_err:
            logger.error(f"[ExecutionEngine] Cleanup failed for '{feature.name}': {cleanup_err}", exc_info=True)

        # Remove from running tasks
        self._running_tasks.pop(feature.id, None)

    async def get_execution_status(self, project_id: str) -> Dict[str, Any]:
        """
        Single API response for the frontend Kanban board.
        Returns DAG summary + all execution runs with agent/cost/test info.
        """
        from .database import get_connection

        pid = _uuid.UUID(project_id)

        # Get DAG summary
        dag = await FeatureDAG.from_database(project_id)
        summary = dag.status_summary()

        # Get all execution runs for this project
        async with get_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT er.*, a.status as agent_status, a.input_tokens as agent_tokens_in,
                       a.output_tokens as agent_tokens_out, a.total_cost as agent_cost
                FROM execution_runs er
                LEFT JOIN agents a ON er.agent_id = a.id AND a.archived = false
                WHERE er.project_id = $1
                ORDER BY er.wave_number ASC, er.created_at ASC
                """,
                pid,
            )

        runs = []
        for row in rows:
            r = dict(row)
            test_results = r.get("test_results", {})
            if isinstance(test_results, str):
                test_results = json.loads(test_results)
            files_changed = r.get("files_changed", [])
            if isinstance(files_changed, str):
                files_changed = json.loads(files_changed)

            # Use live agent cost if available, otherwise use stored cost
            cost = float(r.get("agent_cost") or r.get("total_cost") or 0)

            runs.append({
                "id": str(r["id"]),
                "feature_id": str(r["feature_id"]),
                "feature_name": r["feature_name"],
                "agent_name": r["agent_name"],
                "status": r["status"],
                "agent_status": r.get("agent_status"),
                "started_at": r["started_at"].isoformat() if r.get("started_at") else None,
                "completed_at": r["completed_at"].isoformat() if r.get("completed_at") else None,
                "cost": cost,
                "input_tokens": r.get("agent_tokens_in") or r.get("input_tokens") or 0,
                "output_tokens": r.get("agent_tokens_out") or r.get("output_tokens") or 0,
                "test_results": test_results,
                "files_changed": files_changed,
                "error_message": r.get("error_message"),
                "wave_number": r.get("wave_number", 0),
            })

        # Also include features that have NO execution run yet (planned/queued)
        all_features = list(dag._features.values())
        run_feature_ids = {r["feature_id"] for r in runs}

        for feat in all_features:
            if feat.id not in run_feature_ids:
                # Compute wave number
                groups = dag.get_parallel_groups()
                wave = 0
                for i, group in enumerate(groups):
                    if feat.id in group:
                        wave = i
                        break

                # Determine if it's ready
                is_ready = feat.id in dag.get_ready_features()

                runs.append({
                    "id": None,
                    "feature_id": feat.id,
                    "feature_name": feat.name,
                    "agent_name": None,
                    "status": "ready" if is_ready else "queued",
                    "agent_status": None,
                    "started_at": None,
                    "completed_at": None,
                    "cost": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "test_results": {},
                    "files_changed": [],
                    "error_message": None,
                    "wave_number": wave,
                    "priority": feat.priority,
                    "depends_on": feat.depends_on,
                })

        return {
            "project_id": project_id,
            "dag": {
                "total": dag.feature_count,
                "complete": summary.get("complete", 0),
                "in_progress": summary.get("in_progress", 0),
                "blocked": summary.get("blocked", 0),
                "planned": summary.get("planned", 0),
                "completion_pct": dag.completion_percentage(),
            },
            "runs": sorted(runs, key=lambda r: (r.get("wave_number", 0), r.get("priority", 999))),
            "total_cost": sum(r.get("cost", 0) for r in runs),
        }

    def _get_changed_files(self, repo_path: str) -> List[Dict[str, str]]:
        """Get list of changed files via git."""
        try:
            result = subprocess.run(
                ["git", "diff", "--name-status", "HEAD~1"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            files = []
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    parts = line.split("\t", 1)
                    if len(parts) == 2:
                        action_map = {"A": "added", "M": "modified", "D": "deleted"}
                        files.append({
                            "path": parts[1],
                            "action": action_map.get(parts[0], parts[0]),
                        })
            return files
        except Exception:
            return []

    async def _run_tests(self, cwd: str, test_command: str, timeout: int = 120) -> str:
        """Run test command and return output."""
        try:
            proc = await asyncio.create_subprocess_shell(
                test_command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return stdout.decode("utf-8", errors="replace")
        except asyncio.TimeoutError:
            return "TIMEOUT: Tests exceeded time limit"
        except Exception as e:
            return f"ERROR: {e}"

    def _parse_test_results(self, output: str) -> Dict[str, Any]:
        """Parse pytest/jest output for pass/fail counts."""
        results = {"passed": 0, "failed": 0, "skipped": 0, "errors": [], "output": output[-2000:]}

        # pytest format: "5 passed, 2 failed, 1 skipped"
        import re
        passed = re.search(r"(\d+) passed", output)
        failed = re.search(r"(\d+) failed", output)
        skipped = re.search(r"(\d+) skipped", output)
        errors = re.search(r"(\d+) error", output)

        if passed:
            results["passed"] = int(passed.group(1))
        if failed:
            results["failed"] = int(failed.group(1))
        if skipped:
            results["skipped"] = int(skipped.group(1))
        if errors:
            results["errors"].append(f"{errors.group(1)} test errors")

        # jest format: "Tests: 5 passed, 2 failed, 7 total"
        jest_match = re.search(r"Tests:\s+(\d+) passed.*?(\d+) failed", output)
        if jest_match:
            results["passed"] = int(jest_match.group(1))
            results["failed"] = int(jest_match.group(2))

        return results
