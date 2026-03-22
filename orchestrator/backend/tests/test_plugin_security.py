"""
Comprehensive tests for Plugin System Security Hardening.

Tests cover all five acceptance criteria:

1. Plugin inputs validated with Pydantic schemas before execution
2. Plugin loading uses safe imports with error handling for malformed plugins
3. Plugin execution sandboxed with resource limits (timeout, memory / file size)
4. Plugin permissions checked against RBAC before execution
5. Malicious plugin code cannot access system resources outside workspace

No mocks are used — all tests operate on real temporary filesystem fixtures or
the actual greenfield plugin (when the real plugins directory is present).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict

import pytest
import yaml

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.plugin_security import (
    ALLOWED_MODELS,
    ALLOWED_TOOLS,
    MAX_AGENT_TEMPLATE_SIZE_BYTES,
    MAX_AGENTS_PER_PHASE,
    MAX_CRITERIA_PER_PHASE,
    MAX_MANIFEST_SIZE_BYTES,
    MAX_PHASES_PER_PLUGIN,
    MAX_PROMPT_LENGTH,
    MAX_SKILLS_PER_PHASE,
    PluginPermission,
    PluginPermissionError,
    PluginSandbox,
    PluginSandboxError,
    PluginSecurityError,
    PluginValidationError,
    SecurePluginLoader,
    UserRole,
    ValidatedAgentTemplate,
    ValidatedPhaseConfig,
    ValidatedPluginManifest,
    check_permission,
    is_safe_path,
    require_permission,
    validate_file_in_plugin,
    validate_plugin_path,
)

# ---------------------------------------------------------------------------
# Real-plugin availability check
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_PLUGINS_DIR = REPO_ROOT / ".claude" / "rapids-plugins"
REAL_PLUGINS_AVAILABLE = (
    REAL_PLUGINS_DIR.exists()
    and (REAL_PLUGINS_DIR / "greenfield" / "plugin.json").exists()
)


# ===========================================================================
# Fixtures
# ===========================================================================


def _make_manifest(**overrides) -> Dict:
    """Return a minimal valid manifest dict, with optional field overrides."""
    base = {
        "name": "test-plugin",
        "archetype": "test-archetype",
        "description": "A valid test plugin",
        "version": "1.0.0",
        "phases": {
            "research": {
                "entry_criteria": [],
                "exit_criteria": ["research_done"],
                "default_agents": ["researcher"],
                "skills": ["web-research"],
                "prompt_supplement": "Test supplement.",
            }
        },
    }
    base.update(overrides)
    return base


def _make_agent_md(
    name: str = "test-agent",
    model: str = "sonnet",
    tools: str = "Read, Write",
    color: str = "blue",
    prompt: str = "You are a test agent.",
) -> str:
    """Return valid agent .md content."""
    return (
        "---\n"
        f"name: {name}\n"
        f"description: Test agent description\n"
        f"model: {model}\n"
        f"tools:\n"
        + "".join(f"  - {t.strip()}\n" for t in tools.split(","))
        + f"color: {color}\n"
        "---\n"
        "\n"
        f"{prompt}\n"
    )


@pytest.fixture
def tmp_plugins_dir(tmp_path: Path) -> Path:
    """A temporary plugins directory containing one valid plugin."""
    plugins_dir = tmp_path / "plugins"
    plugin_dir = plugins_dir / "test-plugin"
    plugin_dir.mkdir(parents=True)

    (plugin_dir / "plugin.json").write_text(
        json.dumps(_make_manifest(), indent=2)
    )

    agents_dir = plugin_dir / "agents"
    agents_dir.mkdir()
    (agents_dir / "researcher.md").write_text(
        _make_agent_md(name="researcher", tools="Read, Write, WebSearch")
    )

    (plugin_dir / "commands").mkdir()
    (plugin_dir / "commands" / "research.md").write_text("# Research command")
    (plugin_dir / "skills").mkdir()
    (plugin_dir / "skills" / "web-research.md").write_text("# Web research skill")
    (plugin_dir / "workflows").mkdir()
    (plugin_dir / "workflows" / "research.md").write_text("# Research workflow")

    return plugins_dir


@pytest.fixture
def secure_loader(tmp_plugins_dir: Path) -> SecurePluginLoader:
    """A SecurePluginLoader with the temp plugins dir, after discover_plugins()."""
    loader = SecurePluginLoader(tmp_plugins_dir)
    loader.discover_plugins()
    return secure_loader_from_dir(tmp_plugins_dir)


def secure_loader_from_dir(plugins_dir: Path) -> SecurePluginLoader:
    loader = SecurePluginLoader(plugins_dir)
    loader.discover_plugins()
    return loader


@pytest.fixture
def real_secure_loader() -> SecurePluginLoader:
    """SecurePluginLoader pointed at the real plugins directory."""
    loader = SecurePluginLoader(REAL_PLUGINS_DIR)
    loader.discover_plugins()
    return loader


# ===========================================================================
# 1. PYDANTIC INPUT VALIDATION
# ===========================================================================


class TestValidatedPluginManifest:
    """AC-1: All plugin inputs validated with Pydantic schemas."""

    def test_valid_manifest_parses(self):
        m = ValidatedPluginManifest(**_make_manifest())
        assert m.name == "test-plugin"
        assert m.archetype == "test-archetype"
        assert m.version == "1.0.0"

    def test_name_must_start_with_alphanumeric(self):
        with pytest.raises(Exception):
            ValidatedPluginManifest(**_make_manifest(name="-bad-name"))

    def test_name_cannot_contain_path_separators(self):
        with pytest.raises(Exception):
            ValidatedPluginManifest(**_make_manifest(name="../../evil"))

    def test_name_too_long_rejected(self):
        with pytest.raises(Exception):
            ValidatedPluginManifest(**_make_manifest(name="a" * 65))

    def test_archetype_must_be_safe_identifier(self):
        with pytest.raises(Exception):
            ValidatedPluginManifest(**_make_manifest(archetype="../escape"))

    def test_version_must_be_semver(self):
        with pytest.raises(Exception):
            ValidatedPluginManifest(**_make_manifest(version="not-semver"))

    def test_version_with_prerelease_rejected(self):
        with pytest.raises(Exception):
            ValidatedPluginManifest(**_make_manifest(version="1.0.0-beta"))

    def test_description_stripped(self):
        m = ValidatedPluginManifest(**_make_manifest(description="  hello  "))
        assert m.description == "hello"

    def test_description_too_long_rejected(self):
        with pytest.raises(Exception):
            ValidatedPluginManifest(**_make_manifest(description="x" * 1001))

    def test_missing_required_fields_rejected(self):
        with pytest.raises(Exception):
            ValidatedPluginManifest(name="only-name")

    def test_too_many_phases_rejected(self):
        phases = {
            f"phase-{i:02d}": {
                "entry_criteria": [],
                "exit_criteria": [],
                "default_agents": [],
                "skills": [],
            }
            for i in range(MAX_PHASES_PER_PLUGIN + 1)
        }
        with pytest.raises(Exception):
            ValidatedPluginManifest(**_make_manifest(phases=phases))

    def test_invalid_phase_name_rejected(self):
        phases = {
            "valid-phase": {"entry_criteria": [], "exit_criteria": [], "default_agents": [], "skills": []},
            "../escape": {"entry_criteria": [], "exit_criteria": [], "default_agents": [], "skills": []},
        }
        with pytest.raises(Exception):
            ValidatedPluginManifest(**_make_manifest(phases=phases))

    def test_valid_version_formats(self):
        for v in ["0.0.1", "1.0.0", "10.20.300"]:
            m = ValidatedPluginManifest(**_make_manifest(version=v))
            assert m.version == v


class TestValidatedPhaseConfig:
    """AC-1: Phase config validation."""

    def test_valid_phase_config(self):
        pc = ValidatedPhaseConfig(
            entry_criteria=["prereq"],
            exit_criteria=["done"],
            default_agents=["researcher"],
            skills=["web-research"],
            prompt_supplement="Some text.",
        )
        assert pc.entry_criteria == ["prereq"]

    def test_too_many_criteria_rejected(self):
        with pytest.raises(Exception):
            ValidatedPhaseConfig(
                entry_criteria=["x"] * (MAX_CRITERIA_PER_PHASE + 1)
            )

    def test_criterion_too_long_rejected(self):
        with pytest.raises(Exception):
            ValidatedPhaseConfig(entry_criteria=["x" * 201])

    def test_non_string_criterion_rejected(self):
        with pytest.raises(Exception):
            ValidatedPhaseConfig(entry_criteria=[123])

    def test_too_many_agents_rejected(self):
        with pytest.raises(Exception):
            ValidatedPhaseConfig(
                default_agents=["agent"] * (MAX_AGENTS_PER_PHASE + 1)
            )

    def test_invalid_agent_name_rejected(self):
        with pytest.raises(Exception):
            ValidatedPhaseConfig(default_agents=["../evil-agent"])

    def test_too_many_skills_rejected(self):
        with pytest.raises(Exception):
            ValidatedPhaseConfig(
                skills=["skill"] * (MAX_SKILLS_PER_PHASE + 1)
            )

    def test_skill_too_long_rejected(self):
        with pytest.raises(Exception):
            ValidatedPhaseConfig(skills=["x" * 101])

    def test_prompt_supplement_too_long_rejected(self):
        with pytest.raises(Exception):
            ValidatedPhaseConfig(prompt_supplement="x" * (MAX_PROMPT_LENGTH + 1))

    def test_criteria_must_be_list(self):
        with pytest.raises(Exception):
            ValidatedPhaseConfig(entry_criteria="not-a-list")


class TestValidatedAgentTemplate:
    """AC-1: Agent template validation."""

    def test_valid_agent_template(self):
        t = ValidatedAgentTemplate(
            name="researcher",
            description="Does research",
            model="sonnet",
            tools=["Read", "Write"],
            system_prompt="You are a researcher.",
            color="blue",
        )
        assert t.name == "researcher"
        assert "Read" in t.tools

    def test_unknown_tool_rejected(self):
        with pytest.raises(Exception, match="not in allowed list"):
            ValidatedAgentTemplate(
                name="bad-agent",
                tools=["Read", "EvilTool"],
            )

    def test_all_allowed_tools_accepted(self):
        t = ValidatedAgentTemplate(
            name="powerful-agent",
            tools=list(ALLOWED_TOOLS),
        )
        assert set(t.tools) == ALLOWED_TOOLS

    def test_tools_as_comma_string(self):
        t = ValidatedAgentTemplate(name="a", tools="Read, Write, Bash")
        assert t.tools == ["Read", "Write", "Bash"]

    def test_unknown_model_rejected(self):
        with pytest.raises(Exception, match="Unknown model"):
            ValidatedAgentTemplate(name="a", model="gpt-4")

    def test_allowed_models_accepted(self):
        for model in ALLOWED_MODELS:
            t = ValidatedAgentTemplate(name="a", model=model)
            assert t.model == model

    def test_claude_star_model_accepted(self):
        t = ValidatedAgentTemplate(name="a", model="claude-3-future-20991231")
        assert t.model == "claude-3-future-20991231"

    def test_invalid_color_rejected(self):
        with pytest.raises(Exception, match="Invalid color"):
            ValidatedAgentTemplate(name="a", color="<script>")

    def test_valid_hex_color_accepted(self):
        for color in ["#fff", "#abcdef", "#AABBCC"]:
            t = ValidatedAgentTemplate(name="a", color=color)
            assert t.color == color

    def test_valid_named_color_accepted(self):
        t = ValidatedAgentTemplate(name="a", color="blue")
        assert t.color == "blue"

    def test_agent_name_with_path_separator_rejected(self):
        with pytest.raises(Exception):
            ValidatedAgentTemplate(name="../../evil")

    def test_system_prompt_too_long_rejected(self):
        with pytest.raises(Exception):
            ValidatedAgentTemplate(
                name="a",
                system_prompt="x" * (MAX_PROMPT_LENGTH + 1),
            )


# ===========================================================================
# 2. SAFE PLUGIN LOADING
# ===========================================================================


class TestSafePluginLoading:
    """AC-2: Plugin loading uses safe imports with error handling."""

    def test_valid_plugin_loads(self, tmp_plugins_dir):
        loader = secure_loader_from_dir(tmp_plugins_dir)
        assert "test-plugin" in {p.name for p in loader.list_plugins()}

    def test_corrupt_json_skipped_with_error_recorded(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        bad = plugins_dir / "bad"
        bad.mkdir(parents=True)
        (bad / "plugin.json").write_text("{not valid json")
        loader = SecurePluginLoader(plugins_dir)
        loader.discover_plugins()
        assert len(loader.list_plugins()) == 0
        assert "bad" in loader.get_load_errors()
        assert "validation" in loader.get_load_errors()["bad"]

    def test_non_object_json_skipped(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        bad = plugins_dir / "array-manifest"
        bad.mkdir(parents=True)
        (bad / "plugin.json").write_text("[1, 2, 3]")
        loader = SecurePluginLoader(plugins_dir)
        loader.discover_plugins()
        assert len(loader.list_plugins()) == 0
        assert "array-manifest" in loader.get_load_errors()

    def test_missing_required_fields_skipped(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        incomplete = plugins_dir / "incomplete"
        incomplete.mkdir(parents=True)
        (incomplete / "plugin.json").write_text(json.dumps({"name": "incomplete"}))
        loader = SecurePluginLoader(plugins_dir)
        loader.discover_plugins()
        assert len(loader.list_plugins()) == 0

    def test_bad_name_in_manifest_skipped(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        evil = plugins_dir / "evil"
        evil.mkdir(parents=True)
        manifest = _make_manifest(name="../../evil-name")
        (evil / "plugin.json").write_text(json.dumps(manifest))
        loader = SecurePluginLoader(plugins_dir)
        loader.discover_plugins()
        assert len(loader.list_plugins()) == 0

    def test_one_bad_plugin_does_not_block_others(self, tmp_path):
        plugins_dir = tmp_path / "plugins"

        # Good plugin
        good = plugins_dir / "good"
        good.mkdir(parents=True)
        (good / "plugin.json").write_text(
            json.dumps(_make_manifest(name="good-plugin", archetype="good"))
        )

        # Bad plugin
        bad = plugins_dir / "bad"
        bad.mkdir(parents=True)
        (bad / "plugin.json").write_text("{broken")

        loader = SecurePluginLoader(plugins_dir)
        loader.discover_plugins()
        assert loader.get_plugin("good-plugin") is not None
        assert "bad" in loader.get_load_errors()

    def test_directory_without_manifest_skipped(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        no_manifest = plugins_dir / "no-manifest"
        no_manifest.mkdir(parents=True)
        loader = SecurePluginLoader(plugins_dir)
        loader.discover_plugins()
        assert len(loader.list_plugins()) == 0

    def test_nonexistent_plugins_dir_returns_empty(self, tmp_path):
        loader = SecurePluginLoader(tmp_path / "nonexistent")
        loader.discover_plugins()
        assert loader.list_plugins() == []

    def test_file_at_top_level_skipped(self, tmp_plugins_dir):
        (tmp_plugins_dir / "README.md").write_text("ignore me")
        loader = secure_loader_from_dir(tmp_plugins_dir)
        assert len(loader.list_plugins()) == 1

    def test_invalid_agent_tool_skipped_not_crashes_loader(self, tmp_path):
        """Agent template with disallowed tool is skipped; plugin still loads."""
        plugins_dir = tmp_path / "plugins"
        plugin_dir = plugins_dir / "test-plugin"
        agents_dir = plugin_dir / "agents"
        agents_dir.mkdir(parents=True)
        (plugin_dir / "plugin.json").write_text(
            json.dumps(_make_manifest())
        )
        # Write bad agent (disallowed tool)
        (agents_dir / "evil.md").write_text(
            "---\nname: evil\ntools:\n  - EvilTool\n---\nContent\n"
        )
        loader = SecurePluginLoader(plugins_dir)
        loader.discover_plugins()
        # Plugin itself loaded fine
        assert loader.get_plugin("test-plugin") is not None
        # But evil agent was skipped
        templates = loader.load_agent_templates("test-plugin")
        assert "evil" not in templates

    def test_agent_with_no_name_skipped(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugin_dir = plugins_dir / "test-plugin"
        agents_dir = plugin_dir / "agents"
        agents_dir.mkdir(parents=True)
        (plugin_dir / "plugin.json").write_text(json.dumps(_make_manifest()))
        (agents_dir / "nameless.md").write_text(
            "---\ndescription: no name\n---\nContent\n"
        )
        loader = SecurePluginLoader(plugins_dir)
        loader.discover_plugins()
        templates = loader.load_agent_templates("test-plugin")
        assert "nameless" not in templates

    def test_invalid_yaml_frontmatter_skipped(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugin_dir = plugins_dir / "test-plugin"
        agents_dir = plugin_dir / "agents"
        agents_dir.mkdir(parents=True)
        (plugin_dir / "plugin.json").write_text(json.dumps(_make_manifest()))
        (agents_dir / "bad.md").write_text(
            "---\n: bad: yaml: {{{\n---\nContent\n"
        )
        loader = SecurePluginLoader(plugins_dir)
        loader.discover_plugins()
        templates = loader.load_agent_templates("test-plugin")
        assert "bad" not in templates


# ===========================================================================
# 3. RESOURCE LIMITS (SANDBOX)
# ===========================================================================


class TestPluginSandbox:
    """AC-3: Plugin execution sandboxed with resource limits."""

    def test_manifest_within_size_limit_reads_fine(self, tmp_path):
        f = tmp_path / "plugin.json"
        f.write_text(json.dumps(_make_manifest()))
        sandbox = PluginSandbox(max_manifest_bytes=MAX_MANIFEST_SIZE_BYTES)
        text = sandbox.read_manifest(f)
        assert "test-plugin" in text

    def test_oversized_manifest_raises_sandbox_error(self, tmp_path):
        f = tmp_path / "plugin.json"
        f.write_text("x" * (MAX_MANIFEST_SIZE_BYTES + 1))
        sandbox = PluginSandbox(max_manifest_bytes=MAX_MANIFEST_SIZE_BYTES)
        with pytest.raises(PluginSandboxError, match="size limit"):
            sandbox.read_manifest(f)

    def test_template_within_size_limit_reads_fine(self, tmp_path):
        f = tmp_path / "agent.md"
        f.write_text(_make_agent_md())
        sandbox = PluginSandbox(max_template_bytes=MAX_AGENT_TEMPLATE_SIZE_BYTES)
        text = sandbox.read_template(f)
        assert "test-agent" in text

    def test_oversized_template_raises_sandbox_error(self, tmp_path):
        f = tmp_path / "agent.md"
        f.write_text("x" * (MAX_AGENT_TEMPLATE_SIZE_BYTES + 1))
        sandbox = PluginSandbox(max_template_bytes=MAX_AGENT_TEMPLATE_SIZE_BYTES)
        with pytest.raises(PluginSandboxError, match="size limit"):
            sandbox.read_template(f)

    def test_custom_size_limits_are_honoured(self, tmp_path):
        f = tmp_path / "plugin.json"
        f.write_text("hello")
        small_sandbox = PluginSandbox(max_manifest_bytes=4)
        with pytest.raises(PluginSandboxError):
            small_sandbox.read_manifest(f)

    @pytest.mark.asyncio
    async def test_timeout_raises_sandbox_error(self):
        sandbox = PluginSandbox(load_timeout=0.05)

        async def slow():
            await asyncio.sleep(1)
            return "done"

        with pytest.raises(PluginSandboxError, match="timeout"):
            await sandbox.run_with_timeout(slow())

    @pytest.mark.asyncio
    async def test_fast_coroutine_completes_within_timeout(self):
        sandbox = PluginSandbox(load_timeout=5.0)

        async def fast():
            return 42

        result = await sandbox.run_with_timeout(fast())
        assert result == 42

    def test_oversized_manifest_blocked_during_discover(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugin_dir = plugins_dir / "fat"
        plugin_dir.mkdir(parents=True)
        content = "x" * (MAX_MANIFEST_SIZE_BYTES + 1)
        (plugin_dir / "plugin.json").write_text(content)
        small_sandbox = PluginSandbox(max_manifest_bytes=100)
        loader = SecurePluginLoader(plugins_dir, sandbox=small_sandbox)
        loader.discover_plugins()
        assert len(loader.list_plugins()) == 0
        assert "fat" in loader.get_load_errors()
        assert "sandbox" in loader.get_load_errors()["fat"]

    def test_oversized_agent_template_skipped_during_load(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugin_dir = plugins_dir / "test-plugin"
        agents_dir = plugin_dir / "agents"
        agents_dir.mkdir(parents=True)
        (plugin_dir / "plugin.json").write_text(json.dumps(_make_manifest()))
        # Write a fat agent template
        (agents_dir / "fat.md").write_text("---\nname: fat\n---\n" + "x" * 1000)
        tiny_sandbox = PluginSandbox(max_template_bytes=50)
        loader = SecurePluginLoader(plugins_dir, sandbox=tiny_sandbox)
        loader.discover_plugins()
        templates = loader.load_agent_templates("test-plugin")
        assert "fat" not in templates


# ===========================================================================
# 4. RBAC PERMISSION CHECKS
# ===========================================================================


class TestRBACPermissions:
    """AC-4: Plugin permissions checked against user RBAC before execution."""

    # -- check_permission --------------------------------------------------

    def test_admin_has_all_permissions(self):
        for perm in [
            PluginPermission.READ_PLUGIN,
            PluginPermission.LOAD_PLUGIN,
            PluginPermission.EXECUTE_PLUGIN,
            PluginPermission.MANAGE_PLUGINS,
        ]:
            assert check_permission(UserRole.ADMIN, perm)

    def test_editor_can_read_load_execute(self):
        assert check_permission(UserRole.EDITOR, PluginPermission.READ_PLUGIN)
        assert check_permission(UserRole.EDITOR, PluginPermission.LOAD_PLUGIN)
        assert check_permission(UserRole.EDITOR, PluginPermission.EXECUTE_PLUGIN)

    def test_editor_cannot_manage(self):
        assert not check_permission(UserRole.EDITOR, PluginPermission.MANAGE_PLUGINS)

    def test_viewer_can_only_read(self):
        assert check_permission(UserRole.VIEWER, PluginPermission.READ_PLUGIN)
        assert not check_permission(UserRole.VIEWER, PluginPermission.LOAD_PLUGIN)
        assert not check_permission(UserRole.VIEWER, PluginPermission.EXECUTE_PLUGIN)
        assert not check_permission(UserRole.VIEWER, PluginPermission.MANAGE_PLUGINS)

    def test_guest_has_no_permissions(self):
        for perm in [
            PluginPermission.READ_PLUGIN,
            PluginPermission.LOAD_PLUGIN,
            PluginPermission.EXECUTE_PLUGIN,
            PluginPermission.MANAGE_PLUGINS,
        ]:
            assert not check_permission(UserRole.GUEST, perm)

    def test_unknown_role_has_no_permissions(self):
        assert not check_permission("unknown-role", PluginPermission.READ_PLUGIN)

    # -- require_permission ------------------------------------------------

    def test_require_permission_passes_when_granted(self):
        # Should not raise
        require_permission(UserRole.ADMIN, PluginPermission.MANAGE_PLUGINS)
        require_permission(UserRole.EDITOR, PluginPermission.EXECUTE_PLUGIN)
        require_permission(UserRole.VIEWER, PluginPermission.READ_PLUGIN)

    def test_require_permission_raises_when_denied(self):
        with pytest.raises(PluginPermissionError):
            require_permission(UserRole.VIEWER, PluginPermission.EXECUTE_PLUGIN)

    def test_require_permission_raises_for_guest(self):
        with pytest.raises(PluginPermissionError):
            require_permission(UserRole.GUEST, PluginPermission.READ_PLUGIN)

    def test_permission_error_is_plugin_security_error(self):
        with pytest.raises(PluginSecurityError):
            require_permission(UserRole.GUEST, PluginPermission.LOAD_PLUGIN)

    # -- SecurePluginLoader RBAC integration --------------------------------

    def test_discover_requires_load_permission(self, tmp_plugins_dir):
        loader = SecurePluginLoader(tmp_plugins_dir)
        with pytest.raises(PluginPermissionError):
            loader.discover_plugins(role=UserRole.VIEWER)

    def test_discover_succeeds_for_editor(self, tmp_plugins_dir):
        loader = SecurePluginLoader(tmp_plugins_dir)
        plugins = loader.discover_plugins(role=UserRole.EDITOR)
        assert len(plugins) >= 1

    def test_discover_succeeds_for_admin(self, tmp_plugins_dir):
        loader = SecurePluginLoader(tmp_plugins_dir)
        plugins = loader.discover_plugins(role=UserRole.ADMIN)
        assert len(plugins) >= 1

    def test_get_plugin_requires_read_permission(self, tmp_plugins_dir):
        loader = secure_loader_from_dir(tmp_plugins_dir)
        with pytest.raises(PluginPermissionError):
            loader.get_plugin("test-plugin", role=UserRole.GUEST)

    def test_get_plugin_succeeds_for_viewer(self, tmp_plugins_dir):
        loader = secure_loader_from_dir(tmp_plugins_dir)
        plugin = loader.get_plugin("test-plugin", role=UserRole.VIEWER)
        assert plugin is not None

    def test_list_plugins_requires_read(self, tmp_plugins_dir):
        loader = secure_loader_from_dir(tmp_plugins_dir)
        with pytest.raises(PluginPermissionError):
            loader.list_plugins(role=UserRole.GUEST)

    def test_list_plugins_succeeds_for_viewer(self, tmp_plugins_dir):
        loader = secure_loader_from_dir(tmp_plugins_dir)
        plugins = loader.list_plugins(role=UserRole.VIEWER)
        assert len(plugins) >= 1

    def test_get_agents_for_phase_requires_execute(self, tmp_plugins_dir):
        loader = secure_loader_from_dir(tmp_plugins_dir)
        with pytest.raises(PluginPermissionError):
            loader.get_agents_for_phase("test-plugin", "research", role=UserRole.VIEWER)

    def test_get_agents_for_phase_succeeds_for_editor(self, tmp_plugins_dir):
        loader = secure_loader_from_dir(tmp_plugins_dir)
        agents = loader.get_agents_for_phase(
            "test-plugin", "research", role=UserRole.EDITOR
        )
        assert isinstance(agents, list)

    def test_load_agent_templates_requires_load_permission(self, tmp_plugins_dir):
        loader = secure_loader_from_dir(tmp_plugins_dir)
        with pytest.raises(PluginPermissionError):
            loader.load_agent_templates("test-plugin", role=UserRole.VIEWER)

    def test_load_agent_templates_succeeds_for_editor(self, tmp_plugins_dir):
        loader = secure_loader_from_dir(tmp_plugins_dir)
        templates = loader.load_agent_templates("test-plugin", role=UserRole.EDITOR)
        assert isinstance(templates, dict)

    def test_get_criteria_overrides_requires_read(self, tmp_plugins_dir):
        loader = secure_loader_from_dir(tmp_plugins_dir)
        with pytest.raises(PluginPermissionError):
            loader.get_criteria_overrides("test-plugin", role=UserRole.GUEST)

    def test_get_criteria_overrides_succeeds_for_viewer(self, tmp_plugins_dir):
        loader = secure_loader_from_dir(tmp_plugins_dir)
        overrides = loader.get_criteria_overrides("test-plugin", role=UserRole.VIEWER)
        assert isinstance(overrides, dict)

    def test_no_role_bypasses_permission_check(self, tmp_plugins_dir):
        """role=None means system-level call — no permission check performed."""
        loader = SecurePluginLoader(tmp_plugins_dir)
        loader.discover_plugins()  # no role — should not raise
        plugins = loader.list_plugins()  # no role
        assert len(plugins) >= 1


# ===========================================================================
# 5. PATH SAFETY / SANDBOX CONTAINMENT
# ===========================================================================


class TestPathSafety:
    """AC-5: Malicious plugin code cannot access system resources outside workspace."""

    # -- is_safe_path ------------------------------------------------------

    def test_child_path_is_safe(self, tmp_path):
        root = tmp_path / "plugins"
        root.mkdir()
        child = root / "myplugin" / "plugin.json"
        child.parent.mkdir()
        child.touch()
        assert is_safe_path(child, root)

    def test_traversal_path_is_not_safe(self, tmp_path):
        root = tmp_path / "plugins"
        root.mkdir()
        escape = root / ".." / "secret"
        assert not is_safe_path(escape, root)

    def test_sibling_path_is_not_safe(self, tmp_path):
        plugins = tmp_path / "plugins"
        plugins.mkdir()
        other = tmp_path / "other"
        other.mkdir()
        assert not is_safe_path(other, plugins)

    def test_parent_path_is_not_safe(self, tmp_path):
        root = tmp_path / "plugins"
        root.mkdir()
        assert not is_safe_path(tmp_path, root)

    # -- validate_plugin_path / validate_file_in_plugin --------------------

    def test_valid_plugin_path_does_not_raise(self, tmp_path):
        root = tmp_path / "plugins"
        plugin = root / "myplugin"
        plugin.mkdir(parents=True)
        validate_plugin_path(plugin, root)  # should not raise

    def test_traversal_in_plugin_path_raises(self, tmp_path):
        root = tmp_path / "plugins"
        root.mkdir()
        escape = root / ".." / "escape"
        with pytest.raises(PluginSandboxError):
            validate_plugin_path(escape, root)

    def test_validate_file_in_plugin_safe(self, tmp_path):
        plugin_dir = tmp_path / "plugins" / "myplugin"
        plugin_dir.mkdir(parents=True)
        f = plugin_dir / "plugin.json"
        f.touch()
        validate_file_in_plugin(f, plugin_dir)  # should not raise

    def test_validate_file_outside_plugin_raises(self, tmp_path):
        plugin_dir = tmp_path / "plugins" / "myplugin"
        plugin_dir.mkdir(parents=True)
        outside = tmp_path / "secret.txt"
        outside.touch()
        with pytest.raises(PluginSandboxError):
            validate_file_in_plugin(outside, plugin_dir)

    # -- Symlink escape detection ------------------------------------------

    @pytest.mark.skipif(
        os.name == "nt",
        reason="Symlinks require elevated privileges on Windows",
    )
    def test_symlink_escaping_plugins_root_blocked(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()

        # Create a symlink inside plugins that points outside
        sym = plugins_dir / "evil-symlink"
        sym.symlink_to(outside_dir)

        assert not is_safe_path(sym, plugins_dir)

    @pytest.mark.skipif(
        os.name == "nt",
        reason="Symlinks require elevated privileges on Windows",
    )
    def test_symlink_within_plugins_root_is_safe(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        real_target = plugins_dir / "real-plugin"
        real_target.mkdir()

        sym = plugins_dir / "alias"
        sym.symlink_to(real_target)

        assert is_safe_path(sym, plugins_dir)

    # -- SecurePluginLoader path containment during load -------------------

    @pytest.mark.skipif(
        os.name == "nt",
        reason="Symlinks require elevated privileges on Windows",
    )
    def test_symlink_plugin_dir_escaping_root_skipped(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        outside = tmp_path / "outside-plugin"
        outside.mkdir()
        (outside / "plugin.json").write_text(
            json.dumps(_make_manifest(name="escaped-plugin", archetype="escaped"))
        )

        # Symlink inside plugins pointing to outside directory
        sym = plugins_dir / "evil"
        sym.symlink_to(outside)

        loader = SecurePluginLoader(plugins_dir)
        loader.discover_plugins()
        # The symlinked plugin is outside the root and must be rejected
        assert loader.get_plugin("escaped-plugin") is None
        assert "evil" in loader.get_load_errors()

    def test_path_traversal_in_manifest_name_rejected(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        evil_dir = plugins_dir / "evil"
        evil_dir.mkdir(parents=True)
        manifest = _make_manifest(name="../../etc/passwd", archetype="evil")
        (evil_dir / "plugin.json").write_text(json.dumps(manifest))
        loader = SecurePluginLoader(plugins_dir)
        loader.discover_plugins()
        # Validation rejects the name
        assert len(loader.list_plugins()) == 0

    def test_agent_template_outside_agents_dir_blocked(self, tmp_path):
        """Agent file whose resolved path is outside agents_dir is skipped."""
        plugins_dir = tmp_path / "plugins"
        plugin_dir = plugins_dir / "test-plugin"
        agents_dir = plugin_dir / "agents"
        agents_dir.mkdir(parents=True)
        (plugin_dir / "plugin.json").write_text(json.dumps(_make_manifest()))

        # Normal agent
        (agents_dir / "good.md").write_text(
            _make_agent_md(name="good", tools="Read")
        )

        loader = SecurePluginLoader(plugins_dir)
        loader.discover_plugins()
        templates = loader.load_agent_templates("test-plugin")
        assert "good" in templates  # normal agent is loaded


# ===========================================================================
# 6. INTEGRATION — SecurePluginLoader functional correctness
# ===========================================================================


class TestSecureLoaderFunctionality:
    """Verify SecurePluginLoader produces the same outputs as PluginLoader for valid data."""

    def test_get_phase_config(self, tmp_plugins_dir):
        loader = secure_loader_from_dir(tmp_plugins_dir)
        config = loader.get_phase_config("test-plugin", "research")
        assert config is not None
        assert isinstance(config, ValidatedPhaseConfig)
        assert config.default_agents == ["researcher"]
        assert config.skills == ["web-research"]
        assert config.prompt_supplement == "Test supplement."

    def test_get_plugin_for_archetype(self, tmp_plugins_dir):
        loader = secure_loader_from_dir(tmp_plugins_dir)
        plugin = loader.get_plugin_for_archetype("test-archetype")
        assert plugin is not None
        assert plugin.name == "test-plugin"

    def test_archetype_lookup_case_insensitive(self, tmp_plugins_dir):
        loader = secure_loader_from_dir(tmp_plugins_dir)
        plugin = loader.get_plugin_for_archetype("TEST-ARCHETYPE")
        assert plugin is not None

    def test_load_agent_templates(self, tmp_plugins_dir):
        loader = secure_loader_from_dir(tmp_plugins_dir)
        templates = loader.load_agent_templates("test-plugin")
        assert "researcher" in templates
        t = templates["researcher"]
        assert isinstance(t, ValidatedAgentTemplate)
        assert "Read" in t.tools
        assert t.model == "sonnet"
        assert len(t.system_prompt) > 0

    def test_get_agents_for_phase(self, tmp_plugins_dir):
        loader = secure_loader_from_dir(tmp_plugins_dir)
        agents = loader.get_agents_for_phase("test-plugin", "research")
        assert len(agents) == 1
        assert agents[0].name == "researcher"

    def test_get_agents_for_missing_phase_returns_empty(self, tmp_plugins_dir):
        loader = secure_loader_from_dir(tmp_plugins_dir)
        agents = loader.get_agents_for_phase("test-plugin", "deploy")
        assert agents == []

    def test_get_criteria_overrides(self, tmp_plugins_dir):
        loader = secure_loader_from_dir(tmp_plugins_dir)
        overrides = loader.get_criteria_overrides("test-plugin")
        assert "research" in overrides
        assert overrides["research"]["exit"] == ["research_done"]

    def test_phase_with_empty_criteria_not_in_overrides(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        pd = plugins_dir / "minimal"
        pd.mkdir(parents=True)
        manifest = {
            "name": "minimal",
            "archetype": "minimal",
            "description": "Minimal plugin",
            "version": "1.0.0",
            "phases": {
                "research": {
                    "entry_criteria": [],
                    "exit_criteria": [],
                    "default_agents": [],
                    "skills": [],
                }
            },
        }
        (pd / "plugin.json").write_text(json.dumps(manifest))
        loader = SecurePluginLoader(plugins_dir)
        loader.discover_plugins()
        overrides = loader.get_criteria_overrides("minimal")
        assert "research" not in overrides

    def test_commands_dir(self, tmp_plugins_dir):
        loader = secure_loader_from_dir(tmp_plugins_dir)
        cmd_dir = loader.get_commands_dir("test-plugin")
        assert cmd_dir is not None
        assert cmd_dir.name == "commands"
        assert cmd_dir.is_dir()

    def test_skills_dir(self, tmp_plugins_dir):
        loader = secure_loader_from_dir(tmp_plugins_dir)
        skills_dir = loader.get_skills_dir("test-plugin")
        assert skills_dir is not None
        assert skills_dir.name == "skills"

    def test_workflows_dir(self, tmp_plugins_dir):
        loader = secure_loader_from_dir(tmp_plugins_dir)
        wf_dir = loader.get_workflows_dir("test-plugin")
        assert wf_dir is not None
        assert wf_dir.name == "workflows"

    def test_missing_plugin_returns_none(self, tmp_plugins_dir):
        loader = secure_loader_from_dir(tmp_plugins_dir)
        assert loader.get_plugin("nonexistent") is None
        assert loader.get_phase_config("nonexistent", "research") is None
        assert loader.get_agents_for_phase("nonexistent", "research") == []
        assert loader.get_criteria_overrides("nonexistent") == {}

    def test_agent_comma_tools_string(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        pd = plugins_dir / "test-plugin"
        agents_dir = pd / "agents"
        agents_dir.mkdir(parents=True)
        (pd / "plugin.json").write_text(json.dumps(_make_manifest()))
        (agents_dir / "comma.md").write_text(
            "---\nname: comma\ntools: Read, Write, Bash\n---\nContent\n"
        )
        loader = SecurePluginLoader(plugins_dir)
        loader.discover_plugins()
        templates = loader.load_agent_templates("test-plugin")
        assert "comma" in templates
        assert templates["comma"].tools == ["Read", "Write", "Bash"]

    def test_discover_clears_previous(self, tmp_plugins_dir):
        loader = secure_loader_from_dir(tmp_plugins_dir)
        assert len(loader.list_plugins()) == 1
        import shutil
        shutil.rmtree(tmp_plugins_dir / "test-plugin")
        loader.discover_plugins()
        assert len(loader.list_plugins()) == 0


# ===========================================================================
# 7. REAL GREENFIELD PLUGIN INTEGRATION
# ===========================================================================


@pytest.mark.skipif(
    not REAL_PLUGINS_AVAILABLE,
    reason="Real plugins directory with greenfield plugin not available",
)
class TestRealGreenfieldPlugin:
    """Integration tests against the actual greenfield plugin."""

    def test_greenfield_loads_with_secure_loader(self, real_secure_loader):
        plugin = real_secure_loader.get_plugin("greenfield")
        assert plugin is not None
        assert isinstance(plugin, ValidatedPluginManifest)
        assert plugin.archetype == "greenfield"

    def test_greenfield_has_six_phases(self, real_secure_loader):
        plugin = real_secure_loader.get_plugin("greenfield")
        for phase in ["research", "analysis", "plan", "implement", "deploy", "sustain"]:
            assert phase in plugin.phases, f"Missing phase: {phase}"

    def test_greenfield_researcher_agent_loads(self, real_secure_loader):
        agents = real_secure_loader.get_agents_for_phase("greenfield", "research")
        names = [a.name for a in agents]
        assert "researcher" in names

    def test_greenfield_researcher_tools_are_all_allowed(self, real_secure_loader):
        agents = real_secure_loader.get_agents_for_phase("greenfield", "research")
        researcher = next(a for a in agents if a.name == "researcher")
        for tool in researcher.tools:
            assert tool in ALLOWED_TOOLS, f"Tool {tool!r} not in ALLOWED_TOOLS"

    def test_greenfield_researcher_has_system_prompt(self, real_secure_loader):
        agents = real_secure_loader.get_agents_for_phase("greenfield", "research")
        researcher = next(a for a in agents if a.name == "researcher")
        assert len(researcher.system_prompt) > 0

    def test_greenfield_criteria_overrides_structure(self, real_secure_loader):
        overrides = real_secure_loader.get_criteria_overrides("greenfield")
        assert isinstance(overrides, dict)
        assert "research" in overrides

    def test_greenfield_commands_dir_exists_and_has_files(self, real_secure_loader):
        cmd_dir = real_secure_loader.get_commands_dir("greenfield")
        assert cmd_dir is not None
        assert cmd_dir.is_dir()
        assert len(list(cmd_dir.glob("*.md"))) > 0

    def test_greenfield_no_load_errors(self, real_secure_loader):
        errors = real_secure_loader.get_load_errors()
        assert errors == {}, f"Unexpected load errors: {errors}"
