"""
Plugin Loader & Registry

Discovers and loads archetype plugins from .claude/rapids-plugins/.
Each plugin provides commands, skills, agents, workflows, and hooks
for a specific project archetype.

The PluginRegistry extends PluginLoader with multi-plugin management,
project binding, and capability enumeration for the orchestrator.
"""

from typing import Dict, List, Optional, Any
from pathlib import Path
from pydantic import BaseModel, Field
import json
import yaml
import re
import logging

logger = logging.getLogger(__name__)


class PhaseConfig(BaseModel):
    """Configuration for a specific phase within a plugin."""
    entry_criteria: List[str] = Field(default_factory=list)
    exit_criteria: List[str] = Field(default_factory=list)
    default_agents: List[str] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    prompt_supplement: Optional[str] = None


class PluginManifest(BaseModel):
    """Plugin manifest loaded from plugin.json."""
    name: str
    archetype: str
    description: str
    version: str = "1.0.0"
    phases: Dict[str, PhaseConfig] = Field(default_factory=dict)


class AgentTemplate(BaseModel):
    """Agent template loaded from an agent .md file."""
    name: str
    description: Optional[str] = None
    model: str = "sonnet"
    tools: List[str] = Field(default_factory=list)
    system_prompt: str = ""
    color: Optional[str] = None


class PluginLoader:
    """Discovers and loads archetype plugins."""

    def __init__(self, plugins_dir: Path):
        self._plugins_dir = plugins_dir
        self._plugins: Dict[str, PluginManifest] = {}
        self._agent_templates: Dict[str, Dict[str, AgentTemplate]] = {}  # plugin_name -> {agent_name -> template}

    def discover_plugins(self) -> Dict[str, PluginManifest]:
        """Scan plugins directory, load all plugin.json manifests. Returns plugin dict."""
        self._plugins.clear()

        if not self._plugins_dir.exists() or not self._plugins_dir.is_dir():
            return self._plugins

        for candidate in sorted(self._plugins_dir.iterdir()):
            if not candidate.is_dir():
                continue

            manifest_path = candidate / "plugin.json"
            if not manifest_path.exists():
                continue

            try:
                raw = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest = PluginManifest(**raw)
                self._plugins[manifest.name] = manifest
            except (json.JSONDecodeError, Exception):
                # Skip malformed manifests silently
                continue

        return self._plugins

    def get_plugin(self, name: str) -> Optional[PluginManifest]:
        """Get a loaded plugin by name."""
        return self._plugins.get(name)

    def list_plugins(self) -> List[PluginManifest]:
        """List all discovered plugins."""
        return list(self._plugins.values())

    def get_plugin_for_archetype(self, archetype: str) -> Optional[PluginManifest]:
        """Find a plugin that matches the given archetype."""
        archetype_lower = archetype.lower()
        for plugin in self._plugins.values():
            if plugin.archetype.lower() == archetype_lower:
                return plugin
        return None

    def get_phase_config(self, plugin_name: str, phase: str) -> Optional[PhaseConfig]:
        """Get phase configuration from a plugin."""
        plugin = self._plugins.get(plugin_name)
        if plugin is None:
            return None
        return plugin.phases.get(phase)

    def get_agents_for_phase(self, plugin_name: str, phase: str) -> List[AgentTemplate]:
        """Get agent templates for a specific phase from a plugin."""
        phase_config = self.get_phase_config(plugin_name, phase)
        if phase_config is None:
            return []

        # Ensure agent templates are loaded
        if plugin_name not in self._agent_templates:
            self.load_agent_templates(plugin_name)

        templates = self._agent_templates.get(plugin_name, {})
        result: List[AgentTemplate] = []
        for agent_name in phase_config.default_agents:
            if agent_name in templates:
                result.append(templates[agent_name])
        return result

    def load_agent_templates(self, plugin_name: str) -> Dict[str, AgentTemplate]:
        """Load all agent templates from a plugin's agents/ directory.
        Parses YAML frontmatter from .md files."""
        agents_dir = self._get_subdir(plugin_name, "agents")
        loaded: Dict[str, AgentTemplate] = {}

        if agents_dir is None or not agents_dir.exists():
            self._agent_templates[plugin_name] = loaded
            return loaded

        for md_file in sorted(agents_dir.glob("*.md")):
            template = self._parse_agent_md(md_file)
            if template is not None:
                loaded[template.name] = template

        self._agent_templates[plugin_name] = loaded
        return loaded

    def _parse_agent_md(self, path: Path) -> Optional[AgentTemplate]:
        """Parse an agent .md file with YAML frontmatter."""
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            return None

        if not content.startswith("---"):
            return None

        parts = content.split("---", 2)
        if len(parts) < 3:
            return None

        frontmatter_text = parts[1].strip()
        prompt_body = parts[2].strip()

        try:
            meta = yaml.safe_load(frontmatter_text)
        except yaml.YAMLError:
            return None

        if not isinstance(meta, dict) or "name" not in meta:
            return None

        tools_raw = meta.get("tools", [])
        if isinstance(tools_raw, str):
            tools_raw = [t.strip() for t in tools_raw.split(",") if t.strip()]

        return AgentTemplate(
            name=meta["name"],
            description=meta.get("description"),
            model=meta.get("model", "sonnet"),
            tools=tools_raw,
            system_prompt=prompt_body,
            color=meta.get("color"),
        )

    def get_plugin_dir(self, plugin_name: str) -> Optional[Path]:
        """Get the directory path for a plugin."""
        plugin = self._plugins.get(plugin_name)
        if plugin is None:
            return None
        # Find directory by matching archetype folder name or plugin name
        for candidate in self._plugins_dir.iterdir():
            if not candidate.is_dir():
                continue
            manifest_path = candidate / "plugin.json"
            if manifest_path.exists():
                try:
                    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
                    if raw.get("name") == plugin_name:
                        return candidate
                except Exception:
                    continue
        return None

    def _get_subdir(self, plugin_name: str, subdir: str) -> Optional[Path]:
        """Get a subdirectory within a plugin directory."""
        plugin_dir = self.get_plugin_dir(plugin_name)
        if plugin_dir is None:
            return None
        target = plugin_dir / subdir
        if target.is_dir():
            return target
        return None

    def get_commands_dir(self, plugin_name: str) -> Optional[Path]:
        """Get the commands/ directory for a plugin."""
        return self._get_subdir(plugin_name, "commands")

    def get_skills_dir(self, plugin_name: str) -> Optional[Path]:
        """Get the skills/ directory for a plugin."""
        return self._get_subdir(plugin_name, "skills")

    def get_workflows_dir(self, plugin_name: str) -> Optional[Path]:
        """Get the workflows/ directory for a plugin."""
        return self._get_subdir(plugin_name, "workflows")

    def get_criteria_overrides(self, plugin_name: str) -> Dict[str, Dict]:
        """Get entry/exit criteria overrides from plugin for the phase engine."""
        plugin = self._plugins.get(plugin_name)
        if plugin is None:
            return {}

        overrides: Dict[str, Dict] = {}
        for phase_name, phase_config in plugin.phases.items():
            phase_overrides: Dict[str, Any] = {}
            if phase_config.entry_criteria:
                phase_overrides["entry"] = phase_config.entry_criteria
            if phase_config.exit_criteria:
                phase_overrides["exit"] = phase_config.exit_criteria
            if phase_overrides:
                overrides[phase_name] = phase_overrides

        return overrides

    @property
    def plugins_dir(self) -> Path:
        """Expose plugins directory path."""
        return self._plugins_dir


class PluginCapabilities(BaseModel):
    """Structured capabilities report for a plugin."""
    name: str
    archetype: str
    description: str
    version: str
    phases: List[str] = Field(default_factory=list)
    agents: List[Dict[str, Any]] = Field(default_factory=list)
    commands: List[str] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)  # Actual SKILL.md implementations
    workflows: List[str] = Field(default_factory=list)
    skills_per_phase: Dict[str, List[str]] = Field(default_factory=dict)
    plugin_dir: Optional[str] = None
    has_sdk_manifest: bool = False  # Has .claude-plugin/plugin.json


class PluginRegistry:
    """
    Multi-plugin registry that wraps PluginLoader with:
    - Auto-discovery of all plugins on init
    - Project-to-plugin binding
    - Capability enumeration for orchestrator prompts
    - Dual-format support (plugin.json or rapids-manifest.json)
    """

    def __init__(self, plugins_dir: Path):
        self._loader = PluginLoader(plugins_dir)
        self._project_bindings: Dict[str, str] = {}  # project_id -> plugin_name
        self._discover()

    def _discover(self):
        """Discover all plugins, supporting both plugin.json and rapids-manifest.json."""
        # Standard discovery (plugin.json)
        self._loader.discover_plugins()

        # Also check for rapids-manifest.json (new format)
        if self._loader.plugins_dir.exists():
            for candidate in sorted(self._loader.plugins_dir.iterdir()):
                if not candidate.is_dir():
                    continue
                rapids_manifest = candidate / "rapids-manifest.json"
                if rapids_manifest.exists() and not (candidate / "plugin.json").exists():
                    try:
                        raw = json.loads(rapids_manifest.read_text(encoding="utf-8"))
                        manifest = PluginManifest(**raw)
                        self._loader._plugins[manifest.name] = manifest
                        logger.info(f"Loaded plugin from rapids-manifest.json: {manifest.name}")
                    except Exception as e:
                        logger.warning(f"Failed to load rapids-manifest.json in {candidate}: {e}")

        count = len(self._loader._plugins)
        logger.info(f"PluginRegistry discovered {count} plugins: {list(self._loader._plugins.keys())}")

    @property
    def loader(self) -> PluginLoader:
        """Access the underlying PluginLoader."""
        return self._loader

    def list_all(self) -> List[PluginManifest]:
        """List all discovered plugins."""
        return self._loader.list_plugins()

    def get_plugin(self, name: str) -> Optional[PluginManifest]:
        """Get a plugin by name."""
        return self._loader.get_plugin(name)

    def get_for_archetype(self, archetype: str) -> Optional[PluginManifest]:
        """Find a plugin matching an archetype."""
        return self._loader.get_plugin_for_archetype(archetype)

    def bind_project(self, project_id: str, plugin_name: str):
        """Bind a project to a specific plugin."""
        if self._loader.get_plugin(plugin_name) is None:
            raise ValueError(f"Plugin not found: {plugin_name}")
        self._project_bindings[project_id] = plugin_name
        logger.info(f"Bound project {project_id} to plugin {plugin_name}")

    def get_for_project(self, project_id: str) -> Optional[PluginManifest]:
        """Get the plugin bound to a project."""
        plugin_name = self._project_bindings.get(project_id)
        if plugin_name is None:
            return None
        return self._loader.get_plugin(plugin_name)

    def get_plugin_dir(self, plugin_name: str) -> Optional[Path]:
        """Get the filesystem path for a plugin."""
        return self._loader.get_plugin_dir(plugin_name)

    def list_capabilities(self, plugin_name: str) -> Optional[PluginCapabilities]:
        """
        Enumerate ALL capabilities of a plugin: agents, commands, workflows, skills.
        Used by the orchestrator to understand what a plugin offers.
        """
        plugin = self._loader.get_plugin(plugin_name)
        if plugin is None:
            return None

        # Load agent templates
        self._loader.load_agent_templates(plugin_name)
        agent_templates = self._loader._agent_templates.get(plugin_name, {})

        # Enumerate commands
        commands_dir = self._loader.get_commands_dir(plugin_name)
        command_names = []
        if commands_dir and commands_dir.exists():
            command_names = [f.stem for f in sorted(commands_dir.glob("*.md"))]

        # Enumerate workflows
        workflows_dir = self._loader.get_workflows_dir(plugin_name)
        workflow_names = []
        if workflows_dir and workflows_dir.exists():
            workflow_names = [f.stem for f in sorted(workflows_dir.glob("*.md"))]

        # Enumerate skills from skills/ directory (SDK SKILL.md format)
        skills_dir = self._loader.get_skills_dir(plugin_name)
        skill_names = []
        if skills_dir and skills_dir.exists():
            for skill_subdir in sorted(skills_dir.iterdir()):
                if skill_subdir.is_dir() and (skill_subdir / "SKILL.md").exists():
                    skill_names.append(skill_subdir.name)

        # Collect skills per phase from manifest
        skills_per_phase: Dict[str, List[str]] = {}
        for phase_name, phase_config in plugin.phases.items():
            if phase_config.skills:
                skills_per_phase[phase_name] = phase_config.skills

        # Build agent info list
        agents_info = []
        for name, tmpl in agent_templates.items():
            agents_info.append({
                "name": name,
                "description": tmpl.description or "",
                "model": tmpl.model,
                "tools": tmpl.tools,
                "color": tmpl.color,
            })

        plugin_dir = self._loader.get_plugin_dir(plugin_name)

        # Check for SDK manifest
        has_sdk = False
        if plugin_dir:
            has_sdk = (plugin_dir / ".claude-plugin" / "plugin.json").exists()

        return PluginCapabilities(
            name=plugin.name,
            archetype=plugin.archetype,
            description=plugin.description,
            version=plugin.version,
            phases=list(plugin.phases.keys()),
            agents=agents_info,
            commands=command_names,
            skills=skill_names,
            workflows=workflow_names,
            skills_per_phase=skills_per_phase,
            plugin_dir=str(plugin_dir) if plugin_dir else None,
            has_sdk_manifest=has_sdk,
        )

    def build_plugin_catalog(self) -> str:
        """
        Build a markdown catalog of ALL plugins for the orchestrator's system prompt.
        This lets the orchestrator know what's available and make informed decisions.
        """
        plugins = self._loader.list_plugins()
        if not plugins:
            return "No plugins discovered."

        lines = ["## Available Archetype Plugins\n"]

        for plugin in plugins:
            caps = self.list_capabilities(plugin.name)
            if caps is None:
                continue

            lines.append(f"### {plugin.name} (v{plugin.version})")
            lines.append(f"**Archetype:** {plugin.archetype}")
            lines.append(f"**Description:** {plugin.description}")
            lines.append(f"**Phases:** {', '.join(caps.phases)}")

            if caps.agents:
                agent_list = ", ".join(a["name"] for a in caps.agents)
                lines.append(f"**Agents:** {agent_list}")

            if caps.skills:
                skill_list = ", ".join(f"/{plugin.name}:{s}" for s in caps.skills)
                lines.append(f"**Skills (auto-invocable):** {skill_list}")

            if caps.commands:
                cmd_list = ", ".join(f"/{c}" for c in caps.commands)
                lines.append(f"**Commands:** {cmd_list}")

            if caps.workflows:
                wf_list = ", ".join(caps.workflows)
                lines.append(f"**Workflows:** {wf_list}")

            if caps.has_sdk_manifest:
                lines.append(f"**SDK Compatible:** Yes (agents get auto-discovery of skills via SDK plugin loading)")

            # Show phase→agent mapping
            for phase_name, phase_config in plugin.phases.items():
                if phase_config.default_agents:
                    agents_str = ", ".join(phase_config.default_agents)
                    lines.append(f"  - {phase_name}: agents=[{agents_str}]")

            lines.append("")  # blank line between plugins

        return "\n".join(lines)

    def get_agent_template(self, plugin_name: str, agent_name: str) -> Optional[AgentTemplate]:
        """Get a specific agent template from a plugin."""
        if plugin_name not in self._loader._agent_templates:
            self._loader.load_agent_templates(plugin_name)
        templates = self._loader._agent_templates.get(plugin_name, {})
        return templates.get(agent_name)

    def get_phase_agents(self, plugin_name: str, phase: str) -> List[AgentTemplate]:
        """Get agent templates for a specific phase."""
        return self._loader.get_agents_for_phase(plugin_name, phase)

    def get_phase_workflow_path(self, plugin_name: str, phase: str) -> Optional[Path]:
        """Get the workflow file path for a specific phase."""
        workflows_dir = self._loader.get_workflows_dir(plugin_name)
        if workflows_dir is None:
            return None
        # Try exact match first, then partial match
        for pattern in [f"{phase}-workflow.md", f"{phase}.md", f"{phase}-*.md"]:
            matches = list(workflows_dir.glob(pattern))
            if matches:
                return matches[0]
        return None

    def get_phase_config(self, plugin_name: str, phase: str) -> Optional[PhaseConfig]:
        """Get phase configuration from a plugin."""
        return self._loader.get_phase_config(plugin_name, phase)
