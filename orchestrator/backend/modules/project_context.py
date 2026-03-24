"""
Project Context Manager

Manages .rapids/context.md — a shared breadcrumb file that provides
project environment, structure, conventions, and completed feature history
to builder agents. Engine-managed: agents read it, only the engine writes it.
"""

import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class ProjectContext:
    """Structured project context data."""
    project_name: str = ""
    environment: Dict[str, str] = field(default_factory=dict)
    structure: str = ""
    conventions: List[str] = field(default_factory=list)
    test_command: str = ""
    completed_features: List[Dict[str, Any]] = field(default_factory=list)
    known_issues: List[str] = field(default_factory=list)
    last_updated: str = ""
    last_updated_by: str = ""


class ProjectContextManager:
    """Manages .rapids/context.md for a project."""

    def __init__(self, repo_path: str, project_name: str = ""):
        self._repo_path = Path(repo_path)
        self._context_path = self._repo_path / ".rapids" / "context.md"
        self._project_name = project_name

    def load(self) -> ProjectContext:
        """Load context from file, or return empty context."""
        ctx = ProjectContext(project_name=self._project_name)
        if not self._context_path.exists():
            return ctx

        try:
            content = self._context_path.read_text()
            ctx = self._parse_context(content)
            ctx.project_name = self._project_name or ctx.project_name
        except Exception:
            pass
        return ctx

    def get_context_for_prompt(self) -> str:
        """Get context.md content formatted for injection into agent prompts."""
        if self._context_path.exists():
            content = self._context_path.read_text()
            if content.strip():
                return (
                    "## Project Context (auto-generated — do not modify this section)\n\n"
                    + content
                )
        return ""

    def detect_environment(self) -> Dict[str, str]:
        """Auto-detect project environment from files."""
        env = {}
        repo = self._repo_path

        # Python version
        if (repo / "pyproject.toml").exists():
            try:
                content = (repo / "pyproject.toml").read_text()
                if "requires-python" in content:
                    for line in content.split("\n"):
                        if "requires-python" in line:
                            env["Python"] = line.split("=", 1)[-1].strip().strip('"').strip("'")
                            break
            except Exception:
                pass

        # Check for Python via version file or shebang
        if "Python" not in env:
            for py_marker in [".python-version", "runtime.txt"]:
                marker = repo / py_marker
                if marker.exists():
                    env["Python"] = marker.read_text().strip()
                    break

        # Package manager
        if (repo / "uv.lock").exists() or "uv" in (repo / "pyproject.toml").read_text() if (repo / "pyproject.toml").exists() else "":
            env["Package Manager"] = "uv"
        elif (repo / "poetry.lock").exists():
            env["Package Manager"] = "poetry"
        elif (repo / "Pipfile.lock").exists():
            env["Package Manager"] = "pipenv"
        elif (repo / "requirements.txt").exists():
            env["Package Manager"] = "pip"
        elif (repo / "package-lock.json").exists():
            env["Package Manager"] = "npm"
        elif (repo / "yarn.lock").exists():
            env["Package Manager"] = "yarn"

        # Test framework
        if (repo / "pytest.ini").exists() or (repo / "conftest.py").exists() or (repo / "tests").is_dir():
            env["Test Framework"] = "pytest"
            env["Test Command"] = "uv run pytest" if env.get("Package Manager") == "uv" else "pytest"
        elif (repo / "jest.config.js").exists() or (repo / "jest.config.ts").exists():
            env["Test Framework"] = "jest"
            env["Test Command"] = "npm test"

        # Framework detection
        for fname in ["app/main.py", "main.py", "src/main.py"]:
            fpath = repo / fname
            if fpath.exists():
                try:
                    content = fpath.read_text()
                    if "FastAPI" in content or "fastapi" in content:
                        env["Framework"] = "FastAPI"
                    elif "Flask" in content or "flask" in content:
                        env["Framework"] = "Flask"
                    elif "Django" in content or "django" in content:
                        env["Framework"] = "Django"
                except Exception:
                    pass
                break

        # Database
        if (repo / "docker-compose.yml").exists():
            try:
                dc = (repo / "docker-compose.yml").read_text()
                if "postgres" in dc.lower():
                    env["Database"] = "PostgreSQL"
                    if "pgvector" in dc.lower():
                        env["Database"] += " with pgvector"
                elif "mysql" in dc.lower():
                    env["Database"] = "MySQL"
                elif "redis" in dc.lower() and "Database" not in env:
                    env["Cache"] = "Redis"
            except Exception:
                pass

        return env

    def scan_structure(self, max_depth: int = 3) -> str:
        """Scan project directory structure."""
        lines = []
        repo = self._repo_path
        ignore = {".git", ".rapids", "__pycache__", "node_modules", ".venv", "venv", ".mypy_cache", ".pytest_cache", ".ruff_cache"}

        def _scan(path: Path, prefix: str, depth: int):
            if depth > max_depth:
                return
            try:
                items = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
            except PermissionError:
                return
            dirs = [i for i in items if i.is_dir() and i.name not in ignore]
            files = [i for i in items if i.is_file() and not i.name.startswith(".")]

            for f in files[:15]:  # Limit files per directory
                lines.append(f"{prefix}{f.name}")
            for d in dirs[:10]:  # Limit subdirectories
                lines.append(f"{prefix}{d.name}/")
                _scan(d, prefix + "  ", depth + 1)

        _scan(repo, "", 0)
        return "\n".join(lines[:50])  # Cap total lines

    def update_after_feature(
        self,
        feature_name: str,
        agent_name: str,
        files_changed: List[Dict[str, str]],
    ) -> None:
        """Update context.md after a feature completes."""
        ctx = self.load()

        # Auto-detect environment on first run
        if not ctx.environment:
            ctx.environment = self.detect_environment()

        # Update structure
        ctx.structure = self.scan_structure()

        # Detect test command
        if not ctx.test_command:
            ctx.test_command = ctx.environment.get("Test Command", "")

        # Append completed feature
        file_summaries = [f.get("path", "?") for f in files_changed[:5]]
        ctx.completed_features.append({
            "name": feature_name,
            "files": file_summaries,
            "agent": agent_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        ctx.last_updated = datetime.now(timezone.utc).isoformat()
        ctx.last_updated_by = agent_name

        self._save(ctx)

    def initialize(self) -> None:
        """Initialize context.md with auto-detected environment."""
        ctx = ProjectContext(project_name=self._project_name)
        ctx.environment = self.detect_environment()
        ctx.structure = self.scan_structure()
        ctx.test_command = ctx.environment.get("Test Command", "")
        ctx.last_updated = datetime.now(timezone.utc).isoformat()
        ctx.last_updated_by = "execution-engine"
        self._save(ctx)

    def _save(self, ctx: ProjectContext) -> None:
        """Write context to .rapids/context.md."""
        self._context_path.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            f"# Project Context — {ctx.project_name}",
            f"Updated: {ctx.last_updated} by {ctx.last_updated_by}",
            "",
        ]

        if ctx.environment:
            lines.append("## Environment")
            for k, v in ctx.environment.items():
                if k != "Test Command":  # Don't expose internal
                    lines.append(f"- {k}: {v}")
            lines.append("")

        if ctx.test_command:
            lines.append(f"## Test Command")
            lines.append(f"```")
            lines.append(ctx.test_command)
            lines.append(f"```")
            lines.append("")

        if ctx.structure:
            lines.append("## Project Structure")
            lines.append("```")
            lines.append(ctx.structure)
            lines.append("```")
            lines.append("")

        if ctx.conventions:
            lines.append("## Conventions")
            for c in ctx.conventions:
                lines.append(f"- {c}")
            lines.append("")

        if ctx.completed_features:
            lines.append("## Completed Features")
            for f in ctx.completed_features:
                files_str = ", ".join(f.get("files", [])[:3])
                lines.append(f"- **{f['name']}**: {files_str}")
            lines.append("")

        if ctx.known_issues:
            lines.append("## Known Issues")
            for issue in ctx.known_issues:
                lines.append(f"- {issue}")
            lines.append("")

        self._context_path.write_text("\n".join(lines))

    def _parse_context(self, content: str) -> ProjectContext:
        """Parse context.md back to structured data."""
        ctx = ProjectContext()
        current_section = ""

        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("# Project Context"):
                parts = line.split("—")
                if len(parts) > 1:
                    ctx.project_name = parts[1].strip()
            elif line.startswith("Updated:"):
                parts = line.split(" by ")
                ctx.last_updated = parts[0].replace("Updated: ", "").strip()
                if len(parts) > 1:
                    ctx.last_updated_by = parts[1].strip()
            elif line.startswith("## "):
                current_section = line[3:].strip().lower()
            elif line.startswith("- ") and current_section == "environment":
                parts = line[2:].split(": ", 1)
                if len(parts) == 2:
                    ctx.environment[parts[0].strip()] = parts[1].strip()
            elif line.startswith("- ") and current_section == "conventions":
                ctx.conventions.append(line[2:])
            elif line.startswith("- **") and current_section == "completed features":
                name = line.split("**")[1] if "**" in line else line[2:]
                ctx.completed_features.append({"name": name})
            elif line.startswith("- ") and current_section == "known issues":
                ctx.known_issues.append(line[2:])

        return ctx
