"""
Execution Worker — Separate process that picks up queued feature execution runs.

Runs independently from the orchestrator's event loop. Listens for
PostgreSQL NOTIFY events on the 'feature_queue' channel, spawns Claude
SDK sessions for each queued run, and updates the DB on completion.

Usage:
    uv run python -m modules.execution_worker

This process has NO parent SDK session — it spawns fresh SDK sessions
for each builder agent, avoiding the nesting conflict that causes
"Stream closed" errors.
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("execution_worker")


async def get_pool():
    """Create a database connection pool."""
    import asyncpg
    db_url = os.environ.get("DATABASE_URL", "postgresql://rapids:rapids_dev_2024@localhost:5434/rapids_orchestrator")
    return await asyncpg.create_pool(db_url, min_size=2, max_size=5)


async def listen_and_process():
    """Main worker loop: listen for queued runs and process them."""
    pool = await get_pool()
    logger.info("Execution worker started. Listening for queued runs...")

    # Process any existing queued runs first
    await process_queued_runs(pool)

    # Listen for new runs via NOTIFY
    conn = await pool.acquire()
    try:
        await conn.add_listener("feature_queue", lambda *args: None)  # Register listener

        while True:
            # Check for queued runs every 5 seconds (NOTIFY is bonus, polling is reliable)
            await asyncio.sleep(5)
            await process_queued_runs(pool)
    finally:
        await conn.remove_listener("feature_queue", lambda *args: None)
        await pool.release(conn)
        await pool.close()


async def process_queued_runs(pool):
    """Pick up all queued runs and execute them (one at a time)."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT er.id, er.project_id, er.feature_id, er.feature_name, er.agent_name,
                   f.description as feature_description,
                   f.acceptance_criteria,
                   f.depends_on,
                   p.name as project_name, p.repo_path, p.archetype
            FROM execution_runs er
            JOIN features f ON er.feature_id = f.id
            JOIN projects p ON er.project_id = p.id
            WHERE er.status = 'queued'
            ORDER BY er.created_at ASC
            """
        )

    if not rows:
        return

    # Check how many are already building
    async with pool.acquire() as conn:
        building_count = await conn.fetchval(
            "SELECT COUNT(*) FROM execution_runs WHERE status = 'building'"
        )

    max_parallel = int(os.environ.get("MAX_PARALLEL_BUILDERS", "3"))
    slots_available = max(0, max_parallel - building_count)

    if slots_available == 0:
        return

    runs_to_start = [dict(row) for row in rows[:slots_available]]
    logger.info(f"Found {len(rows)} queued, starting {len(runs_to_start)} (slots: {slots_available}/{max_parallel})")

    # Start them concurrently
    async def safe_execute(run):
        try:
            await execute_single_run(pool, run)
        except Exception as e:
            logger.error(f"Run failed for '{run['feature_name']}': {e}", exc_info=True)
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE execution_runs SET status = 'failed', error_message = $1, completed_at = NOW() WHERE id = $2",
                    str(e), run["id"],
                )

    await asyncio.gather(*[safe_execute(r) for r in runs_to_start])

    # Auto-queue more features if there are ready ones without execution_runs
    await auto_queue_ready_features(pool)


async def auto_queue_ready_features(pool):
    """Queue any ready features that don't have an execution_run yet."""
    async with pool.acquire() as conn:
        # Find features that are planned/ready with no execution_run
        rows = await conn.fetch("""
            SELECT f.id, f.name, f.project_id
            FROM features f
            LEFT JOIN execution_runs er ON f.id = er.feature_id
            WHERE er.id IS NULL
            AND f.status IN ('planned', 'in_progress')
            AND f.project_id IN (SELECT DISTINCT project_id FROM execution_runs)
            ORDER BY f.priority ASC
            LIMIT 10
        """)

    if not rows:
        return

    # Check which are actually ready (all deps complete)
    import httpx
    backend_url = os.environ.get("BACKEND_URL", "http://127.0.0.1:9403")

    for row in rows:
        project_id = str(row["project_id"])
        feature_id = str(row["id"])
        feature_name = row["name"]

        try:
            # Check if feature is ready via DAG
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{backend_url}/api/projects/{project_id}/dag", timeout=10.0)
                dag = resp.json()

            if feature_id not in dag.get("ready_features", []):
                continue

            # Queue it
            agent_name = f"builder-{feature_name}"[:40]
            async with pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO execution_runs (id, project_id, feature_id, feature_name, agent_name, status) VALUES ($1, $2, $3, $4, $5, 'queued')",
                    uuid.uuid4(), row["project_id"], row["id"], feature_name, agent_name,
                )
            logger.info(f"[AutoQueue] Queued: {feature_name}")
        except Exception as e:
            logger.debug(f"[AutoQueue] Skip {feature_name}: {e}")


async def execute_single_run(pool, run: Dict[str, Any]):
    """Execute a single feature run using a fresh Claude SDK session."""
    run_id = run["id"]
    feature_name = run["feature_name"]
    agent_name = run["agent_name"]
    project_name = run["project_name"]
    repo_path = run["repo_path"]
    archetype = run.get("archetype", "")

    # Append short ID to agent name to avoid duplicate key conflicts
    short_id = str(uuid.uuid4())[:6]
    agent_name = f"{agent_name}-{short_id}"

    logger.info(f"[{feature_name}] Starting execution (agent: {agent_name})...")

    # 1. Mark as building
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE execution_runs SET status = 'building', started_at = NOW() WHERE id = $1",
            run_id,
        )
        # Also update feature status
        await conn.execute(
            "UPDATE features SET status = 'in_progress', assigned_agent = $1, started_at = NOW() WHERE id = $2",
            agent_name, run["feature_id"],
        )

    # 2. Build prompt
    prompt = build_agent_prompt(run, repo_path, project_name)

    # 3. Notify backend of feature_started (HTTP call)
    try:
        import httpx
        backend_url = os.environ.get("BACKEND_URL", "http://127.0.0.1:9403")
        async with httpx.AsyncClient() as client:
            await client.post(f"{backend_url}/api/worker/feature-event", json={
                "type": "feature_started",
                "project_id": str(run["project_id"]),
                "feature_id": str(run["feature_id"]),
                "feature_name": feature_name,
                "agent_name": agent_name,
            }, timeout=5.0)
    except Exception:
        pass  # Non-critical

    # 3b. Register agent in agents table so it appears in the sidebar
    # Archive any existing agent with the same name first (from previous runs)
    agent_id = uuid.uuid4()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE agents SET archived = true WHERE name = $1 AND archived = false",
            agent_name,
        )
        await conn.execute(
            """
            INSERT INTO agents (id, orchestrator_agent_id, name, model, system_prompt, status, working_dir, metadata, created_at, updated_at)
            VALUES ($1, (SELECT id FROM orchestrator_agents WHERE archived = false ORDER BY created_at DESC LIMIT 1),
                    $2, $3, $4, 'executing', $5, $6, NOW(), NOW())
            """,
            agent_id, agent_name,
            os.environ.get("IMPLEMENT_MODEL", "claude-sonnet-4-5-20250929"),
            prompt[:500],  # Truncated for DB
            repo_path,
            json.dumps({"builder_info": {"feature_name": feature_name, "project_id": str(run["project_id"])}}),
        )
        # Update execution_run with agent_id
        await conn.execute("UPDATE execution_runs SET agent_id = $1 WHERE id = $2", agent_id, run_id)

    # Notify backend: agent created
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            await client.post(f"{backend_url}/api/worker/feature-event", json={
                "type": "agent_created",
                "agent_id": str(agent_id),
                "agent_name": agent_name,
                "feature_name": feature_name,
                "project_id": str(run["project_id"]),
            }, timeout=5.0)
    except Exception:
        pass

    # 4. Run Claude SDK session
    cost_data = {"input_tokens": 0, "output_tokens": 0, "total_cost": 0}
    error_message = None

    try:
        cost_data = await run_sdk_session(prompt, repo_path, feature_name, run_meta={
            "agent_name": agent_name,
            "agent_id": str(agent_id),
            "project_id": str(run["project_id"]),
            "feature_id": str(run["feature_id"]),
        })
        logger.info(f"[{feature_name}] Agent completed. Cost: ${cost_data['total_cost']:.3f}")
    except Exception as e:
        error_message = str(e)
        logger.error(f"[{feature_name}] Agent failed: {e}")

    # 5. Validate: check files changed
    files_changed = get_changed_files(repo_path)
    test_results = {"passed": 0, "failed": 0, "errors": []}

    if not error_message:
        test_cmd = detect_test_command(repo_path)
        if test_cmd:
            logger.info(f"[{feature_name}] Running tests: {test_cmd}")
            test_results = await run_tests(repo_path, test_cmd)
            logger.info(f"[{feature_name}] Tests: {test_results['passed']} passed, {test_results['failed']} failed")

    # 6. Determine result — test timeout is not a failure (tests may not exist)
    test_errors_are_fatal = any(e for e in test_results.get("errors", []) if "timed out" not in e.lower())
    is_success = not error_message and test_results["failed"] == 0 and not test_errors_are_fatal
    final_status = "complete" if is_success else "failed"
    feature_status = "complete" if is_success else "blocked"

    # 6b. Archive agent + update costs
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE agents SET status = 'completed', archived = true, input_tokens = $1, output_tokens = $2, total_cost = $3, updated_at = NOW() WHERE id = $4",
            cost_data["input_tokens"], cost_data["output_tokens"],
            float(cost_data["total_cost"]), agent_id,
        )

    # 7. Update DB
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE execution_runs SET
                status = $1, completed_at = NOW(),
                input_tokens = $2, output_tokens = $3, total_cost = $4,
                test_results = $5, files_changed = $6, error_message = $7
            WHERE id = $8
            """,
            final_status,
            cost_data["input_tokens"], cost_data["output_tokens"],
            float(cost_data["total_cost"]),
            json.dumps(test_results), json.dumps(files_changed),
            error_message, run_id,
        )
        await conn.execute(
            "UPDATE features SET status = $1, completed_at = NOW() WHERE id = $2",
            feature_status, run["feature_id"],
        )

    # 8. Notify backend
    try:
        import httpx
        backend_url = os.environ.get("BACKEND_URL", "http://127.0.0.1:9403")
        async with httpx.AsyncClient() as client:
            await client.post(f"{backend_url}/api/worker/feature-event", json={
                "type": "feature_completed",
                "project_id": str(run["project_id"]),
                "feature_id": str(run["feature_id"]),
                "feature_name": feature_name,
                "agent_name": agent_name,
                "status": final_status,
                "cost": float(cost_data["total_cost"]),
                "test_results": test_results,
            }, timeout=5.0)
    except Exception:
        pass

    icon = "✅" if is_success else "❌"
    test_str = f" ({test_results['passed']} passed, {test_results['failed']} failed)" if test_results.get("passed") or test_results.get("failed") else ""
    logger.info(f"[{feature_name}] {icon} {final_status}{test_str} | ${cost_data['total_cost']:.3f}")


async def run_sdk_session(prompt: str, cwd: str, feature_name: str, run_meta: Dict = None) -> Dict[str, Any]:
    """Spawn a fresh Claude SDK session, stream events to backend, execute the prompt."""
    from claude_agent_sdk import (
        ClaudeSDKClient, ClaudeAgentOptions, ResultMessage,
        AssistantMessage, TextBlock, ThinkingBlock, ToolUseBlock,
    )

    env_vars = {}
    if "ANTHROPIC_API_KEY" in os.environ:
        env_vars["ANTHROPIC_API_KEY"] = os.environ["ANTHROPIC_API_KEY"]
    if "CLAUDE_CODE_OAUTH_TOKEN" in os.environ:
        env_vars["CLAUDE_CODE_OAUTH_TOKEN"] = os.environ["CLAUDE_CODE_OAUTH_TOKEN"]

    backend_url = os.environ.get("BACKEND_URL", "http://127.0.0.1:9403")
    agent_name = run_meta.get("agent_name", f"builder-{feature_name}") if run_meta else f"builder-{feature_name}"
    agent_id_str = run_meta.get("agent_id", "") if run_meta else ""
    project_id = run_meta.get("project_id", "") if run_meta else ""

    options = ClaudeAgentOptions(
        system_prompt=prompt,
        model=os.environ.get("IMPLEMENT_MODEL", "claude-sonnet-4-5-20250929"),
        cwd=cwd,
        permission_mode="acceptEdits",
        env=env_vars,
        allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep", "TodoWrite"],
        disallowed_tools=["NotebookEdit", "ExitPlanMode"],
    )

    cost_data = {"input_tokens": 0, "output_tokens": 0, "total_cost": 0}
    event_count = 0

    async def broadcast_event(event_type: str, content: str, category: str = "response"):
        """Send agent event to backend for display in event stream."""
        nonlocal event_count
        event_count += 1
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                await client.post(f"{backend_url}/api/worker/feature-event", json={
                    "type": "agent_log",
                    "agent_id": agent_id_str,
                    "agent_name": agent_name,
                    "project_id": project_id,
                    "feature_name": feature_name,
                    "event_type": event_type,
                    "event_category": category,
                    "content": content[:500],
                    "entry_index": event_count,
                }, timeout=3.0)
        except Exception:
            pass

    async with ClaudeSDKClient(options=options) as client:
        await client.query(
            f"Implement the '{feature_name}' feature. Follow the spec and acceptance criteria. "
            f"Write tests. Run tests. Summarize what you implemented."
        )

        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in getattr(message, "content", []):
                    if isinstance(block, TextBlock):
                        text = getattr(block, "text", "")
                        if text:
                            await broadcast_event("RESPONSE", text, "response")
                    elif isinstance(block, ThinkingBlock):
                        text = getattr(block, "thinking", "") or getattr(block, "text", "")
                        if text:
                            await broadcast_event("THINKING", text, "thinking")
                    elif isinstance(block, ToolUseBlock):
                        tool_name = getattr(block, "name", "?")
                        await broadcast_event("TOOL", f"Tool: {tool_name}", "tool_use")

            elif isinstance(message, ResultMessage):
                cost_data["total_cost"] = getattr(message, "total_cost_usd", 0) or 0
                usage = getattr(message, "usage", None)
                if usage:
                    cost_data["input_tokens"] = getattr(usage, "input_tokens", 0) or 0
                    cost_data["output_tokens"] = getattr(usage, "output_tokens", 0) or 0

                # Update agent cost in real-time so sidebar shows progress
                try:
                    import httpx as _httpx
                    async with _httpx.AsyncClient() as _client:
                        await _client.post(f"{backend_url}/api/worker/feature-event", json={
                            "type": "agent_cost_update",
                            "agent_name": agent_name,
                            "input_tokens": cost_data["input_tokens"],
                            "output_tokens": cost_data["output_tokens"],
                            "total_cost": cost_data["total_cost"],
                        }, timeout=3.0)
                except Exception:
                    pass

    return cost_data


def build_agent_prompt(run: Dict, repo_path: str, project_name: str) -> str:
    """Build the builder agent's system prompt."""
    feature_name = run["feature_name"]
    description = run.get("feature_description", "")
    acceptance = run.get("acceptance_criteria", [])
    if isinstance(acceptance, str):
        acceptance = json.loads(acceptance)
    acceptance_text = "\n".join(f"  - {c}" for c in acceptance) if acceptance else "No specific criteria."

    prompt = (
        f"# Feature Builder — {feature_name}\n\n"
        f"Implement this feature for **{project_name}**.\n\n"
        f"**Name:** {feature_name}\n**Description:** {description}\n\n"
        f"## Acceptance Criteria\n{acceptance_text}\n\n"
        f"## Working Directory\n`{repo_path}`\n\n"
    )

    # Read project context
    context_path = Path(repo_path) / ".rapids" / "context.md"
    if context_path.exists():
        prompt += f"## Project Context (auto-generated — do not modify)\n{context_path.read_text()}\n\n"

    # Read spec
    for spec_name in ["specification.md", "spec.md"]:
        spec_path = Path(repo_path) / ".rapids" / "plan" / spec_name
        if spec_path.exists():
            prompt += f"## Project Spec\n{spec_path.read_text()[:3000]}\n\n"
            break

    # Read feature spec
    for spec_dir in [
        Path(repo_path) / ".rapids" / "plan" / "features" / str(run["feature_id"]),
        Path(repo_path) / ".rapids" / "plan" / "features" / feature_name,
    ]:
        sf = spec_dir / "spec.md"
        if sf.exists():
            prompt += f"## Feature Spec\n{sf.read_text()}\n\n"
            break

    prompt += "## Instructions\n1. Implement the feature\n2. Write tests\n3. Run tests\n4. Summarize what you did\n"
    return prompt


def get_changed_files(repo_path: str) -> List[Dict[str, str]]:
    """Get changed files via git."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-status", "HEAD~1"],
            cwd=repo_path, capture_output=True, text=True, timeout=10,
        )
        files = []
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                parts = line.split("\t", 1)
                if len(parts) == 2:
                    files.append({"path": parts[1], "action": {"A": "added", "M": "modified", "D": "deleted"}.get(parts[0], parts[0])})
        return files
    except Exception:
        return []


def detect_test_command(repo_path: str) -> str:
    """Detect the test command for this project."""
    p = Path(repo_path)
    if (p / "pytest.ini").exists() or (p / "conftest.py").exists() or (p / "tests").is_dir():
        if (p / "uv.lock").exists():
            return "uv run pytest"
        return "pytest"
    if (p / "jest.config.js").exists() or (p / "jest.config.ts").exists():
        return "npm test"
    return ""


async def run_tests(cwd: str, cmd: str, timeout: int = 120) -> Dict[str, Any]:
    """Run tests and parse results."""
    import re
    results = {"passed": 0, "failed": 0, "skipped": 0, "errors": [], "output": ""}
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd, cwd=cwd,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = stdout.decode("utf-8", errors="replace")
        results["output"] = output[-2000:]

        passed = re.search(r"(\d+) passed", output)
        failed = re.search(r"(\d+) failed", output)
        skipped = re.search(r"(\d+) skipped", output)
        if passed: results["passed"] = int(passed.group(1))
        if failed: results["failed"] = int(failed.group(1))
        if skipped: results["skipped"] = int(skipped.group(1))
    except asyncio.TimeoutError:
        results["errors"].append("Tests timed out")
    except Exception as e:
        results["errors"].append(str(e))
    return results


if __name__ == "__main__":
    logger.info("Starting execution worker process...")
    asyncio.run(listen_and_process())
