"""
Comprehensive tests for the PluginLoader module.

All tests use real implementations -- no mocks.
Uses the actual .claude/rapids-plugins/ directory in the repo for
integration-style tests, and tmp_path for isolation tests.
"""

import json
import pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.plugin_loader import PluginLoader, PluginManifest, PhaseConfig, AgentTemplate


# ======================================================================
# Paths
# ======================================================================

REPO_ROOT = Path(__file__).resolve().parents[3]  # orchestrator/backend/tests -> repo root
REAL_PLUGINS_DIR = REPO_ROOT / ".claude" / "rapids-plugins"

REAL_PLUGINS_AVAILABLE = REAL_PLUGINS_DIR.exists() and (REAL_PLUGINS_DIR / "greenfield" / "plugin.json").exists()


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture
def real_loader():
    """Loader pointed at the real plugins directory."""
    loader = PluginLoader(REAL_PLUGINS_DIR)
    loader.discover_plugins()
    return loader


@pytest.fixture
def tmp_plugins_dir(tmp_path):
    """Create a temporary plugins directory with a test plugin."""
    plugins_dir = tmp_path / "plugins"
    plugin_dir = plugins_dir / "test-plugin"
    plugin_dir.mkdir(parents=True)

    manifest = {
        "name": "test-plugin",
        "archetype": "test-archetype",
        "description": "A test plugin",
        "version": "1.0.0",
        "phases": {
            "research": {
                "entry_criteria": [],
                "exit_criteria": ["research_artifacts_exist"],
                "default_agents": ["test-researcher"],
                "skills": ["web-research"],
                "prompt_supplement": "Test supplement"
            },
            "plan": {
                "entry_criteria": ["research_complete"],
                "exit_criteria": ["spec_exists"],
                "default_agents": ["test-planner"],
                "skills": [],
            },
        }
    }
    (plugin_dir / "plugin.json").write_text(json.dumps(manifest, indent=2))

    # Create agents directory with a sample agent
    agents_dir = plugin_dir / "agents"
    agents_dir.mkdir()
    (agents_dir / "test-researcher.md").write_text(
        "---\n"
        "name: test-researcher\n"
        "description: A test researcher agent\n"
        "model: sonnet\n"
        "tools:\n"
        "  - Read\n"
        "  - Write\n"
        "  - WebSearch\n"
        "color: blue\n"
        "---\n"
        "\n"
        "# Test Researcher\n"
        "\n"
        "You are a test researcher agent.\n"
    )

    # Create commands and skills directories
    (plugin_dir / "commands").mkdir()
    (plugin_dir / "commands" / "research.md").write_text("# Research command")
    (plugin_dir / "skills").mkdir()
    (plugin_dir / "skills" / "web-research.md").write_text("# Web research skill")
    (plugin_dir / "workflows").mkdir()
    (plugin_dir / "workflows" / "research.md").write_text(
        "# Research Workflow\n\n"
        "## Section 1: Problem Statement\n"
        "> Guide: Define the problem.\n"
    )

    return plugins_dir


@pytest.fixture
def tmp_loader(tmp_plugins_dir):
    """Loader pointed at the temporary plugins directory."""
    loader = PluginLoader(tmp_plugins_dir)
    loader.discover_plugins()
    return loader


# ======================================================================
# discover_plugins
# ======================================================================


class TestDiscoverPlugins:
    @pytest.mark.skipif(not REAL_PLUGINS_AVAILABLE, reason="Real plugins directory not available")
    def test_discovers_greenfield_plugin(self, real_loader):
        plugins = real_loader.list_plugins()
        names = [p.name for p in plugins]
        assert "greenfield" in names

    def test_discovers_test_plugin(self, tmp_loader):
        plugins = tmp_loader.list_plugins()
        assert len(plugins) == 1
        assert plugins[0].name == "test-plugin"

    def test_empty_directory(self, tmp_path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        loader = PluginLoader(empty_dir)
        plugins = loader.discover_plugins()
        assert len(plugins) == 0

    def test_nonexistent_directory(self, tmp_path):
        loader = PluginLoader(tmp_path / "nonexistent")
        plugins = loader.discover_plugins()
        assert len(plugins) == 0

    def test_skips_non_directories(self, tmp_plugins_dir):
        # Add a file at the top level (not a directory)
        (tmp_plugins_dir / "README.md").write_text("ignore me")
        loader = PluginLoader(tmp_plugins_dir)
        plugins = loader.discover_plugins()
        assert len(plugins) == 1  # Only the test-plugin directory

    def test_skips_dirs_without_manifest(self, tmp_plugins_dir):
        (tmp_plugins_dir / "no-manifest").mkdir()
        loader = PluginLoader(tmp_plugins_dir)
        plugins = loader.discover_plugins()
        assert len(plugins) == 1

    def test_discover_clears_previous(self, tmp_loader, tmp_plugins_dir):
        assert len(tmp_loader.list_plugins()) == 1
        # Discover again after removing plugin
        import shutil
        shutil.rmtree(tmp_plugins_dir / "test-plugin")
        tmp_loader.discover_plugins()
        assert len(tmp_loader.list_plugins()) == 0


# ======================================================================
# get_plugin
# ======================================================================


class TestGetPlugin:
    @pytest.mark.skipif(not REAL_PLUGINS_AVAILABLE, reason="Real plugins directory not available")
    def test_get_greenfield_plugin(self, real_loader):
        plugin = real_loader.get_plugin("greenfield")
        assert plugin is not None
        assert isinstance(plugin, PluginManifest)
        assert plugin.archetype == "greenfield"

    def test_get_test_plugin(self, tmp_loader):
        plugin = tmp_loader.get_plugin("test-plugin")
        assert plugin is not None
        assert plugin.archetype == "test-archetype"
        assert plugin.description == "A test plugin"
        assert plugin.version == "1.0.0"

    def test_get_missing_plugin(self, tmp_loader):
        assert tmp_loader.get_plugin("nonexistent") is None


# ======================================================================
# get_plugin_for_archetype
# ======================================================================


class TestGetPluginForArchetype:
    @pytest.mark.skipif(not REAL_PLUGINS_AVAILABLE, reason="Real plugins directory not available")
    def test_find_greenfield(self, real_loader):
        plugin = real_loader.get_plugin_for_archetype("greenfield")
        assert plugin is not None
        assert plugin.name == "greenfield"

    def test_find_test_archetype(self, tmp_loader):
        plugin = tmp_loader.get_plugin_for_archetype("test-archetype")
        assert plugin is not None
        assert plugin.name == "test-plugin"

    def test_case_insensitive(self, tmp_loader):
        plugin = tmp_loader.get_plugin_for_archetype("TEST-ARCHETYPE")
        assert plugin is not None

    def test_missing_archetype(self, tmp_loader):
        assert tmp_loader.get_plugin_for_archetype("unknown") is None


# ======================================================================
# get_phase_config
# ======================================================================


class TestGetPhaseConfig:
    @pytest.mark.skipif(not REAL_PLUGINS_AVAILABLE, reason="Real plugins directory not available")
    def test_greenfield_research_config(self, real_loader):
        config = real_loader.get_phase_config("greenfield", "research")
        assert config is not None
        assert isinstance(config, PhaseConfig)
        assert "researcher" in config.default_agents

    @pytest.mark.skipif(not REAL_PLUGINS_AVAILABLE, reason="Real plugins directory not available")
    def test_greenfield_all_phases_have_config(self, real_loader):
        for phase in ["research", "analysis", "plan", "implement", "deploy", "sustain"]:
            config = real_loader.get_phase_config("greenfield", phase)
            assert config is not None, f"Missing config for phase: {phase}"

    def test_test_plugin_research_config(self, tmp_loader):
        config = tmp_loader.get_phase_config("test-plugin", "research")
        assert config is not None
        assert config.default_agents == ["test-researcher"]
        assert config.skills == ["web-research"]
        assert config.prompt_supplement == "Test supplement"

    def test_test_plugin_plan_config(self, tmp_loader):
        config = tmp_loader.get_phase_config("test-plugin", "plan")
        assert config is not None
        assert "research_complete" in config.entry_criteria
        assert "spec_exists" in config.exit_criteria

    def test_missing_plugin(self, tmp_loader):
        assert tmp_loader.get_phase_config("nonexistent", "research") is None

    def test_missing_phase(self, tmp_loader):
        assert tmp_loader.get_phase_config("test-plugin", "deploy") is None


# ======================================================================
# get_agents_for_phase / load_agent_templates
# ======================================================================


class TestAgentTemplates:
    @pytest.mark.skipif(not REAL_PLUGINS_AVAILABLE, reason="Real plugins directory not available")
    def test_greenfield_research_agents(self, real_loader):
        agents = real_loader.get_agents_for_phase("greenfield", "research")
        assert len(agents) >= 1
        names = [a.name for a in agents]
        assert "researcher" in names

    @pytest.mark.skipif(not REAL_PLUGINS_AVAILABLE, reason="Real plugins directory not available")
    def test_greenfield_agent_has_tools(self, real_loader):
        agents = real_loader.get_agents_for_phase("greenfield", "research")
        researcher = next(a for a in agents if a.name == "researcher")
        assert isinstance(researcher.tools, list)
        assert len(researcher.tools) > 0

    @pytest.mark.skipif(not REAL_PLUGINS_AVAILABLE, reason="Real plugins directory not available")
    def test_greenfield_agent_has_prompt(self, real_loader):
        agents = real_loader.get_agents_for_phase("greenfield", "research")
        researcher = next(a for a in agents if a.name == "researcher")
        assert len(researcher.system_prompt) > 0

    def test_load_agent_templates_from_test_plugin(self, tmp_loader):
        templates = tmp_loader.load_agent_templates("test-plugin")
        assert "test-researcher" in templates
        agent = templates["test-researcher"]
        assert isinstance(agent, AgentTemplate)
        assert agent.model == "sonnet"
        assert "Read" in agent.tools
        assert "WebSearch" in agent.tools
        assert agent.color == "blue"
        assert "test researcher" in agent.system_prompt.lower()

    def test_get_agents_for_phase_test_plugin(self, tmp_loader):
        agents = tmp_loader.get_agents_for_phase("test-plugin", "research")
        assert len(agents) == 1
        assert agents[0].name == "test-researcher"

    def test_get_agents_for_missing_phase(self, tmp_loader):
        agents = tmp_loader.get_agents_for_phase("test-plugin", "deploy")
        assert agents == []

    def test_get_agents_for_missing_plugin(self, tmp_loader):
        agents = tmp_loader.get_agents_for_phase("nonexistent", "research")
        assert agents == []


class TestParseAgentMd:
    def test_parse_yaml_frontmatter(self, tmp_plugins_dir):
        loader = PluginLoader(tmp_plugins_dir)
        loader.discover_plugins()
        templates = loader.load_agent_templates("test-plugin")
        agent = templates["test-researcher"]
        assert agent.description == "A test researcher agent"

    def test_no_frontmatter(self, tmp_plugins_dir):
        """Agent file without --- frontmatter is skipped."""
        agents_dir = tmp_plugins_dir / "test-plugin" / "agents"
        (agents_dir / "bad-agent.md").write_text("# No frontmatter\nJust content")
        loader = PluginLoader(tmp_plugins_dir)
        loader.discover_plugins()
        templates = loader.load_agent_templates("test-plugin")
        assert "bad-agent" not in templates

    def test_missing_name_in_frontmatter(self, tmp_plugins_dir):
        agents_dir = tmp_plugins_dir / "test-plugin" / "agents"
        (agents_dir / "nameless.md").write_text(
            "---\n"
            "description: no name field\n"
            "---\n"
            "content\n"
        )
        loader = PluginLoader(tmp_plugins_dir)
        loader.discover_plugins()
        templates = loader.load_agent_templates("test-plugin")
        assert "nameless" not in templates

    def test_tools_as_comma_string(self, tmp_plugins_dir):
        agents_dir = tmp_plugins_dir / "test-plugin" / "agents"
        (agents_dir / "comma-tools.md").write_text(
            "---\n"
            "name: comma-tools\n"
            "tools: Read, Write, Bash\n"
            "---\n"
            "content\n"
        )
        loader = PluginLoader(tmp_plugins_dir)
        loader.discover_plugins()
        templates = loader.load_agent_templates("test-plugin")
        assert "comma-tools" in templates
        assert templates["comma-tools"].tools == ["Read", "Write", "Bash"]


# ======================================================================
# get_criteria_overrides
# ======================================================================


class TestGetCriteriaOverrides:
    @pytest.mark.skipif(not REAL_PLUGINS_AVAILABLE, reason="Real plugins directory not available")
    def test_greenfield_overrides(self, real_loader):
        overrides = real_loader.get_criteria_overrides("greenfield")
        assert isinstance(overrides, dict)
        # greenfield plugin defines criteria for research, analysis, etc.
        assert "research" in overrides

    def test_test_plugin_overrides(self, tmp_loader):
        overrides = tmp_loader.get_criteria_overrides("test-plugin")
        assert "research" in overrides
        assert overrides["research"]["exit"] == ["research_artifacts_exist"]
        assert "plan" in overrides
        assert overrides["plan"]["entry"] == ["research_complete"]

    def test_missing_plugin_overrides(self, tmp_loader):
        assert tmp_loader.get_criteria_overrides("nonexistent") == {}

    def test_phase_with_no_custom_criteria(self, tmp_plugins_dir):
        """Phase with empty criteria lists should not appear in overrides."""
        plugins_dir = tmp_plugins_dir
        plugin_dir = plugins_dir / "minimal"
        plugin_dir.mkdir()
        manifest = {
            "name": "minimal",
            "archetype": "minimal",
            "description": "Minimal plugin",
            "phases": {
                "research": {
                    "entry_criteria": [],
                    "exit_criteria": [],
                    "default_agents": [],
                    "skills": [],
                },
            }
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest))
        loader = PluginLoader(plugins_dir)
        loader.discover_plugins()
        overrides = loader.get_criteria_overrides("minimal")
        # research has empty lists, so no overrides for it
        assert "research" not in overrides


# ======================================================================
# Handling of missing/corrupt plugins
# ======================================================================


class TestCorruptPlugins:
    def test_corrupt_manifest_json(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        bad_plugin = plugins_dir / "bad"
        bad_plugin.mkdir(parents=True)
        (bad_plugin / "plugin.json").write_text("{not valid json")
        loader = PluginLoader(plugins_dir)
        plugins = loader.discover_plugins()
        assert len(plugins) == 0

    def test_manifest_missing_required_fields(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        bad_plugin = plugins_dir / "incomplete"
        bad_plugin.mkdir(parents=True)
        (bad_plugin / "plugin.json").write_text(json.dumps({"name": "incomplete"}))
        loader = PluginLoader(plugins_dir)
        plugins = loader.discover_plugins()
        # Should be skipped due to missing archetype/description
        assert len(plugins) == 0


# ======================================================================
# Directory getters
# ======================================================================


class TestDirectoryGetters:
    def test_get_commands_dir(self, tmp_loader):
        cmd_dir = tmp_loader.get_commands_dir("test-plugin")
        assert cmd_dir is not None
        assert cmd_dir.name == "commands"
        assert cmd_dir.is_dir()

    def test_get_skills_dir(self, tmp_loader):
        skills_dir = tmp_loader.get_skills_dir("test-plugin")
        assert skills_dir is not None
        assert skills_dir.name == "skills"

    def test_get_workflows_dir(self, tmp_loader):
        wf_dir = tmp_loader.get_workflows_dir("test-plugin")
        assert wf_dir is not None
        assert wf_dir.name == "workflows"

    def test_get_plugin_dir(self, tmp_loader):
        plugin_dir = tmp_loader.get_plugin_dir("test-plugin")
        assert plugin_dir is not None
        assert (plugin_dir / "plugin.json").exists()

    def test_get_commands_dir_missing_plugin(self, tmp_loader):
        assert tmp_loader.get_commands_dir("nonexistent") is None

    def test_get_skills_dir_missing_plugin(self, tmp_loader):
        assert tmp_loader.get_skills_dir("nonexistent") is None

    def test_get_workflows_dir_missing_plugin(self, tmp_loader):
        assert tmp_loader.get_workflows_dir("nonexistent") is None

    @pytest.mark.skipif(not REAL_PLUGINS_AVAILABLE, reason="Real plugins directory not available")
    def test_real_greenfield_commands_dir(self, real_loader):
        cmd_dir = real_loader.get_commands_dir("greenfield")
        assert cmd_dir is not None
        assert cmd_dir.is_dir()
        # Should contain command files
        files = list(cmd_dir.glob("*.md"))
        assert len(files) > 0

    @pytest.mark.skipif(not REAL_PLUGINS_AVAILABLE, reason="Real plugins directory not available")
    def test_real_greenfield_agents_dir_exists(self, real_loader):
        plugin_dir = real_loader.get_plugin_dir("greenfield")
        agents_dir = plugin_dir / "agents"
        assert agents_dir.exists()
        files = list(agents_dir.glob("*.md"))
        assert len(files) > 0
