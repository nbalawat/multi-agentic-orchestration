"""
Plugin Loader

Discovers and loads archetype plugins from .claude/rapids-plugins/.
Each plugin provides commands, skills, agents, workflows, and hooks
for a specific project archetype.
"""

from typing import Dict, List, Optional, Any
from pathlib import Path
from pydantic import BaseModel, Field
import json
import yaml
import re


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
