"""
Plugin System Security Hardening
=================================

Provides production-grade security for the archetype plugin system:

1. **Input Validation** — Strict Pydantic v2 schemas validate all plugin data
   (manifests, agent templates, phase configs) before use.

2. **Path Safety** — Directory-traversal and symlink-escape attacks are blocked
   by resolving every path and checking it sits inside the plugins root.

3. **Resource Limits (Sandbox)** — :class:`PluginSandbox` enforces file-size
   limits (preventing DoS via huge manifests) and an async timeout wrapper for
   long-running load operations.

4. **RBAC Permission Checks** — :class:`UserRole` + :class:`PluginPermission`
   define a role-permission matrix. Every public method on
   :class:`SecurePluginLoader` accepts an optional ``role`` argument; when
   supplied, the caller's permissions are verified before the operation runs.

5. **Secure Loader** — :class:`SecurePluginLoader` wires all the above together
   into a drop-in replacement for the original ``PluginLoader``.

Usage example::

    from pathlib import Path
    from modules.plugin_security import SecurePluginLoader, UserRole

    loader = SecurePluginLoader(Path(".claude/rapids-plugins"))
    loader.discover_plugins(role=UserRole.ADMIN)

    plugin = loader.get_plugin("greenfield", role=UserRole.VIEWER)
    agents  = loader.get_agents_for_phase("greenfield", "research", role=UserRole.EDITOR)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Security constants
# ---------------------------------------------------------------------------

#: Maximum bytes for a plugin.json manifest file.
MAX_MANIFEST_SIZE_BYTES: int = 64 * 1024          # 64 KB

#: Maximum bytes for a single agent-template .md file.
MAX_AGENT_TEMPLATE_SIZE_BYTES: int = 256 * 1024   # 256 KB

#: Maximum characters in a system_prompt / prompt_supplement field.
MAX_PROMPT_LENGTH: int = 50_000

#: Maximum characters in a description field.
MAX_DESCRIPTION_LENGTH: int = 1_000

#: Maximum items per criteria list (entry/exit).
MAX_CRITERIA_PER_PHASE: int = 50

#: Maximum agents declared per phase.
MAX_AGENTS_PER_PHASE: int = 20

#: Maximum skills declared per phase.
MAX_SKILLS_PER_PHASE: int = 50

#: Maximum phases per plugin manifest.
MAX_PHASES_PER_PLUGIN: int = 20

#: Default wall-clock timeout for a complete plugin-load cycle (seconds).
LOAD_TIMEOUT_SECONDS: float = 30.0

# ---------------------------------------------------------------------------
# Tool / model allowlists
# ---------------------------------------------------------------------------

#: Claude SDK tools that plugins are permitted to declare for their agents.
#: Any tool NOT in this set is rejected during agent-template validation.
ALLOWED_TOOLS: FrozenSet[str] = frozenset({
    "Agent",
    "Bash",
    "Edit",
    "ExitPlanMode",
    "Glob",
    "Grep",
    "MultiEdit",
    "NotebookEdit",
    "NotebookRead",
    "Read",
    "Task",
    "TodoRead",
    "TodoWrite",
    "WebFetch",
    "WebSearch",
    "Write",
})

#: Claude model identifiers that agents are permitted to declare.
#: Additionally, any value matching ``^claude-[a-zA-Z0-9._-]+$`` is accepted
#: to future-proof against new model versions.
ALLOWED_MODELS: FrozenSet[str] = frozenset({
    "haiku",
    "opus",
    "sonnet",
    "claude-3-5-haiku-20241022",
    "claude-3-5-sonnet-20241022",
    "claude-3-opus-20240229",
    "claude-opus-4-5",
    "claude-sonnet-4-5",
})

# ---------------------------------------------------------------------------
# Validation regex patterns
# ---------------------------------------------------------------------------

#: Safe identifier: starts with alphanumeric, then [a-zA-Z0-9._-], max 64 chars.
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")

#: Strict semver: MAJOR.MINOR.PATCH (all numeric, no pre-release suffix).
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

#: CSS color: named colour (letters only) or #hex with 3-8 hex digits.
_COLOR_RE = re.compile(r"^(?:#[0-9A-Fa-f]{3,8}|[a-zA-Z]{2,30})$")

#: Future claude-* model identifier pattern.
_CLAUDE_MODEL_RE = re.compile(r"^claude-[a-zA-Z0-9._-]+$")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class PluginSecurityError(Exception):
    """Base class for all plugin security errors."""


class PluginPermissionError(PluginSecurityError):
    """Raised when the caller lacks permission for a plugin operation."""


class PluginValidationError(PluginSecurityError):
    """Raised when plugin data fails Pydantic validation or schema rules."""


class PluginSandboxError(PluginSecurityError):
    """Raised when a sandbox constraint is violated (path escape, size limit, timeout)."""


# ---------------------------------------------------------------------------
# RBAC — roles and permissions
# ---------------------------------------------------------------------------

class UserRole(str):
    """
    User role constants for RBAC enforcement.

    Use the class-level attributes rather than constructing instances directly::

        role = UserRole.ADMIN
    """

    ADMIN: str = "admin"
    EDITOR: str = "editor"
    VIEWER: str = "viewer"
    GUEST: str = "guest"

    #: All defined role values (for validation).
    _ALL: FrozenSet[str] = frozenset({"admin", "editor", "viewer", "guest"})

    @classmethod
    def validate(cls, value: str) -> str:
        """Raise ``ValueError`` if *value* is not a known role."""
        if value not in cls._ALL:
            raise ValueError(f"Unknown role {value!r}. Must be one of: {sorted(cls._ALL)}")
        return value


class PluginPermission(str):
    """
    Granular permission constants for plugin operations.

    Use the class-level attributes::

        perm = PluginPermission.EXECUTE_PLUGIN
    """

    READ_PLUGIN: str = "plugin:read"       #: Read plugin manifests / list plugins.
    LOAD_PLUGIN: str = "plugin:load"       #: Discover / load plugins from disk.
    EXECUTE_PLUGIN: str = "plugin:execute" #: Use a plugin to drive an agent phase.
    MANAGE_PLUGINS: str = "plugin:manage"  #: Install / remove plugins (admin only).

    _ALL: FrozenSet[str] = frozenset({
        "plugin:read",
        "plugin:load",
        "plugin:execute",
        "plugin:manage",
    })


#: Default role → frozenset-of-permissions mapping.
ROLE_PERMISSIONS: Dict[str, FrozenSet[str]] = {
    UserRole.ADMIN: frozenset(PluginPermission._ALL),
    UserRole.EDITOR: frozenset({
        PluginPermission.READ_PLUGIN,
        PluginPermission.LOAD_PLUGIN,
        PluginPermission.EXECUTE_PLUGIN,
    }),
    UserRole.VIEWER: frozenset({
        PluginPermission.READ_PLUGIN,
    }),
    UserRole.GUEST: frozenset(),
}


def check_permission(role: str, permission: str) -> bool:
    """Return ``True`` if *role* grants *permission*.

    Parameters
    ----------
    role:
        A :class:`UserRole` string constant (e.g. ``UserRole.EDITOR``).
    permission:
        A :class:`PluginPermission` string constant.
    """
    return permission in ROLE_PERMISSIONS.get(role, frozenset())


def require_permission(role: str, permission: str) -> None:
    """Raise :class:`PluginPermissionError` if *role* does not grant *permission*.

    Parameters
    ----------
    role:
        A :class:`UserRole` string constant.
    permission:
        A :class:`PluginPermission` string constant.

    Raises
    ------
    PluginPermissionError
        When the role is not granted the requested permission.
    """
    if not check_permission(role, permission):
        raise PluginPermissionError(
            f"Role {role!r} does not have permission {permission!r}"
        )


# ---------------------------------------------------------------------------
# Path safety helpers
# ---------------------------------------------------------------------------

def is_safe_path(path: Path, allowed_root: Path) -> bool:
    """Return ``True`` if *path* resolves to a location inside *allowed_root*.

    Both paths are fully resolved (symlinks followed) before the check so that
    a symlink planted inside the plugins directory that points *outside* is
    caught.

    Parameters
    ----------
    path:
        The path to check.
    allowed_root:
        The directory that must be an ancestor of *path*.
    """
    try:
        resolved = path.resolve()
        root = allowed_root.resolve()
        resolved.relative_to(root)
        return True
    except (ValueError, OSError):
        return False


def validate_plugin_path(plugin_dir: Path, plugins_root: Path) -> None:
    """Assert that *plugin_dir* is safely inside *plugins_root*.

    Parameters
    ----------
    plugin_dir:
        Directory being checked (not yet resolved).
    plugins_root:
        The directory that all plugins must live under.

    Raises
    ------
    PluginSandboxError
        If the resolved path escapes *plugins_root*.
    """
    if not is_safe_path(plugin_dir, plugins_root):
        raise PluginSandboxError(
            f"Plugin directory {plugin_dir!r} is outside the allowed plugins "
            f"root {plugins_root!r}"
        )


def validate_file_in_plugin(file_path: Path, plugin_dir: Path) -> None:
    """Assert that *file_path* is inside *plugin_dir*.

    Parameters
    ----------
    file_path:
        The file being accessed.
    plugin_dir:
        The plugin's root directory.

    Raises
    ------
    PluginSandboxError
        If the resolved file path escapes *plugin_dir*.
    """
    if not is_safe_path(file_path, plugin_dir):
        raise PluginSandboxError(
            f"File {file_path!r} is outside plugin directory {plugin_dir!r}"
        )


# ---------------------------------------------------------------------------
# Pydantic validation schemas (strict, security-hardened)
# ---------------------------------------------------------------------------

class ValidatedPhaseConfig(BaseModel):
    """Strictly validated phase configuration.

    Enforces:
    - List-length limits on criteria / agents / skills
    - String-length limits on individual items
    - Safe identifier pattern on agent names
    - Maximum prompt_supplement length
    """

    entry_criteria: List[str] = Field(default_factory=list)
    exit_criteria: List[str] = Field(default_factory=list)
    default_agents: List[str] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    prompt_supplement: Optional[str] = Field(None, max_length=MAX_PROMPT_LENGTH)

    @field_validator("entry_criteria", "exit_criteria", mode="before")
    @classmethod
    def _validate_criteria(cls, v: Any) -> List[str]:
        if not isinstance(v, list):
            raise ValueError("Criteria must be a list")
        if len(v) > MAX_CRITERIA_PER_PHASE:
            raise ValueError(
                f"Too many criteria items: {len(v)} (max {MAX_CRITERIA_PER_PHASE})"
            )
        for item in v:
            if not isinstance(item, str):
                raise ValueError(f"Each criterion must be a string, got {type(item)!r}")
            if len(item) > 200:
                raise ValueError(
                    f"Criterion too long ({len(item)} chars, max 200): {item[:50]!r}…"
                )
        return v

    @field_validator("default_agents", mode="before")
    @classmethod
    def _validate_agent_names(cls, v: Any) -> List[str]:
        if not isinstance(v, list):
            raise ValueError("default_agents must be a list")
        if len(v) > MAX_AGENTS_PER_PHASE:
            raise ValueError(
                f"Too many default agents: {len(v)} (max {MAX_AGENTS_PER_PHASE})"
            )
        for name in v:
            if not isinstance(name, str) or not _SAFE_NAME_RE.match(name):
                raise ValueError(
                    f"Invalid agent name {name!r}. Must match [a-zA-Z0-9][a-zA-Z0-9._-]{{0,63}}"
                )
        return v

    @field_validator("skills", mode="before")
    @classmethod
    def _validate_skills(cls, v: Any) -> List[str]:
        if not isinstance(v, list):
            raise ValueError("skills must be a list")
        if len(v) > MAX_SKILLS_PER_PHASE:
            raise ValueError(
                f"Too many skills: {len(v)} (max {MAX_SKILLS_PER_PHASE})"
            )
        for skill in v:
            if not isinstance(skill, str) or len(skill) > 100:
                raise ValueError(
                    f"Invalid skill {skill!r}: must be a string ≤ 100 chars"
                )
        return v


class ValidatedPluginManifest(BaseModel):
    """Strictly validated plugin manifest.

    Enforces:
    - Safe identifier pattern on ``name`` and ``archetype``
    - Strict semver on ``version``
    - Length limit on ``description``
    - Phase count limit
    - Safe identifier pattern on phase names
    """

    name: str = Field(min_length=1, max_length=64)
    archetype: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)
    version: str = Field(default="1.0.0", max_length=32)
    phases: Dict[str, ValidatedPhaseConfig] = Field(default_factory=dict)

    @field_validator("name", "archetype")
    @classmethod
    def _validate_safe_name(cls, v: str) -> str:
        if not _SAFE_NAME_RE.match(v):
            raise ValueError(
                f"Name must start with alphanumeric and contain only "
                f"[a-zA-Z0-9._-] (1–64 chars): {v!r}"
            )
        return v

    @field_validator("version")
    @classmethod
    def _validate_semver(cls, v: str) -> str:
        if not _SEMVER_RE.match(v):
            raise ValueError(f"Version must follow semver (X.Y.Z): {v!r}")
        return v

    @field_validator("description")
    @classmethod
    def _sanitize_description(cls, v: str) -> str:
        return v.strip()

    @model_validator(mode="after")
    def _validate_phases(self) -> "ValidatedPluginManifest":
        if len(self.phases) > MAX_PHASES_PER_PLUGIN:
            raise ValueError(
                f"Too many phases: {len(self.phases)} (max {MAX_PHASES_PER_PLUGIN})"
            )
        for phase_name in self.phases:
            if not _SAFE_NAME_RE.match(phase_name):
                raise ValueError(
                    f"Invalid phase name {phase_name!r}. "
                    f"Must match [a-zA-Z0-9][a-zA-Z0-9._-]{{0,63}}"
                )
        return self


class ValidatedAgentTemplate(BaseModel):
    """Strictly validated agent template.

    Enforces:
    - Safe identifier pattern on ``name``
    - Model restricted to :data:`ALLOWED_MODELS` or ``claude-*`` prefix
    - Tools restricted to :data:`ALLOWED_TOOLS`
    - Color validated as CSS color name or ``#hex``
    - System prompt length cap
    """

    name: str = Field(min_length=1, max_length=64)
    description: Optional[str] = Field(None, max_length=MAX_DESCRIPTION_LENGTH)
    model: str = Field(default="sonnet", max_length=64)
    tools: List[str] = Field(default_factory=list)
    system_prompt: str = Field(default="", max_length=MAX_PROMPT_LENGTH)
    color: Optional[str] = Field(None, max_length=32)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not _SAFE_NAME_RE.match(v):
            raise ValueError(
                f"Agent name must match [a-zA-Z0-9][a-zA-Z0-9._-]{{0,63}}: {v!r}"
            )
        return v

    @field_validator("model")
    @classmethod
    def _validate_model(cls, v: str) -> str:
        if v in ALLOWED_MODELS:
            return v
        if _CLAUDE_MODEL_RE.match(v):
            return v
        raise ValueError(
            f"Unknown model {v!r}. Must be one of {sorted(ALLOWED_MODELS)} "
            f"or a 'claude-*' identifier."
        )

    @field_validator("tools", mode="before")
    @classmethod
    def _validate_tools(cls, v: Any) -> List[str]:
        # Accept comma-separated string or list
        if isinstance(v, str):
            v = [t.strip() for t in v.split(",") if t.strip()]
        if not isinstance(v, list):
            raise ValueError("tools must be a list or comma-separated string")
        unknown = [t for t in v if t not in ALLOWED_TOOLS]
        if unknown:
            raise ValueError(
                f"Tools not in allowed list: {unknown}. "
                f"Allowed tools: {sorted(ALLOWED_TOOLS)}"
            )
        return v

    @field_validator("color")
    @classmethod
    def _validate_color(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not _COLOR_RE.match(v):
            raise ValueError(
                f"Invalid color {v!r}. Must be a CSS color name or #hex (3–8 digits)."
            )
        return v


# ---------------------------------------------------------------------------
# Resource-limited sandbox
# ---------------------------------------------------------------------------

class PluginSandbox:
    """Enforces resource limits when reading plugin files.

    Currently enforces:

    - **File-size limits** on manifests and agent templates to prevent DoS via
      huge files that consume unbounded memory.
    - **Async timeout wrapper** (:meth:`run_with_timeout`) for long-running
      load operations.

    Parameters
    ----------
    max_manifest_bytes:
        Maximum allowed size for a ``plugin.json`` file (default 64 KB).
    max_template_bytes:
        Maximum allowed size for an agent-template ``.md`` file (default 256 KB).
    load_timeout:
        Maximum wall-clock seconds for a complete async load operation
        (default 30 s).
    """

    def __init__(
        self,
        *,
        max_manifest_bytes: int = MAX_MANIFEST_SIZE_BYTES,
        max_template_bytes: int = MAX_AGENT_TEMPLATE_SIZE_BYTES,
        load_timeout: float = LOAD_TIMEOUT_SECONDS,
    ) -> None:
        self.max_manifest_bytes = max_manifest_bytes
        self.max_template_bytes = max_template_bytes
        self.load_timeout = load_timeout

    def read_manifest(self, path: Path) -> str:
        """Read *path* as a plugin manifest, raising on size overflow.

        Parameters
        ----------
        path:
            Path to the ``plugin.json`` file.

        Returns
        -------
        str
            Raw file contents.

        Raises
        ------
        PluginSandboxError
            If the file size exceeds :attr:`max_manifest_bytes`.
        """
        size = path.stat().st_size
        if size > self.max_manifest_bytes:
            raise PluginSandboxError(
                f"Plugin manifest {path.name!r} exceeds size limit: "
                f"{size} bytes > {self.max_manifest_bytes} bytes"
            )
        return path.read_text(encoding="utf-8")

    def read_template(self, path: Path) -> str:
        """Read *path* as an agent-template file, raising on size overflow.

        Parameters
        ----------
        path:
            Path to the ``.md`` agent-template file.

        Returns
        -------
        str
            Raw file contents.

        Raises
        ------
        PluginSandboxError
            If the file size exceeds :attr:`max_template_bytes`.
        """
        size = path.stat().st_size
        if size > self.max_template_bytes:
            raise PluginSandboxError(
                f"Agent template {path.name!r} exceeds size limit: "
                f"{size} bytes > {self.max_template_bytes} bytes"
            )
        return path.read_text(encoding="utf-8")

    async def run_with_timeout(self, coro: Any) -> Any:
        """Await *coro* with the configured :attr:`load_timeout`.

        Parameters
        ----------
        coro:
            An awaitable to execute.

        Returns
        -------
        Any
            The result of the awaitable.

        Raises
        ------
        PluginSandboxError
            If the operation does not complete within :attr:`load_timeout` seconds.
        """
        try:
            return await asyncio.wait_for(coro, timeout=self.load_timeout)
        except asyncio.TimeoutError as exc:
            raise PluginSandboxError(
                f"Plugin operation exceeded timeout of {self.load_timeout}s"
            ) from exc


# ---------------------------------------------------------------------------
# Secure Plugin Loader
# ---------------------------------------------------------------------------

class SecurePluginLoader:
    """Security-hardened archetype plugin loader.

    Drop-in replacement for the original ``PluginLoader`` that adds:

    1. **Input validation** — All manifests and agent templates are parsed
       through strict Pydantic v2 schemas (:class:`ValidatedPluginManifest`,
       :class:`ValidatedAgentTemplate`) before being stored.

    2. **Path safety** — Every candidate directory and file is checked against
       the resolved plugins root.  Symlinks that escape the root and
       ``..``-style traversal are both blocked.

    3. **Resource limits** — The :class:`PluginSandbox` rejects files that
       exceed configured size caps and provides an async timeout wrapper.

    4. **RBAC** — Every public method accepts an optional ``role`` keyword
       argument.  When supplied, :func:`require_permission` is called with the
       appropriate :class:`PluginPermission` before the operation proceeds.
       Passing ``role=None`` (the default) bypasses permission checks, which is
       appropriate for system-level startup code that runs before a user session
       exists.

    Parameters
    ----------
    plugins_dir:
        Root directory that contains one sub-directory per plugin.
    sandbox:
        Optional custom :class:`PluginSandbox`; a default instance is created
        if not provided.
    """

    def __init__(
        self,
        plugins_dir: Path,
        sandbox: Optional[PluginSandbox] = None,
    ) -> None:
        self._plugins_dir: Path = plugins_dir.resolve()
        self._sandbox: PluginSandbox = sandbox or PluginSandbox()
        self._plugins: Dict[str, ValidatedPluginManifest] = {}
        # plugin_name → {agent_name → ValidatedAgentTemplate}
        self._agent_templates: Dict[str, Dict[str, ValidatedAgentTemplate]] = {}
        # plugin_dir_name → human-readable error message for failed loads
        self._load_errors: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover_plugins(
        self,
        role: Optional[str] = None,
    ) -> Dict[str, ValidatedPluginManifest]:
        """Scan the plugins directory and load all valid plugin manifests.

        Plugins that fail validation or sandbox checks are skipped with a
        warning; they do **not** prevent other plugins from loading.  Call
        :meth:`get_load_errors` to inspect failures.

        Parameters
        ----------
        role:
            If not ``None``, the caller's role is checked for
            :attr:`PluginPermission.LOAD_PLUGIN` before discovery begins.

        Returns
        -------
        Dict[str, ValidatedPluginManifest]
            Mapping of plugin name → validated manifest for all successfully
            loaded plugins.
        """
        if role is not None:
            require_permission(role, PluginPermission.LOAD_PLUGIN)

        self._plugins.clear()
        self._load_errors.clear()

        if not self._plugins_dir.exists() or not self._plugins_dir.is_dir():
            return self._plugins

        for candidate in sorted(self._plugins_dir.iterdir()):
            if not candidate.is_dir():
                continue

            manifest_path = candidate / "plugin.json"
            if not manifest_path.exists():
                continue

            try:
                self._load_single_plugin(candidate, manifest_path)
            except PluginSandboxError as exc:
                self._load_errors[candidate.name] = f"sandbox: {exc}"
                logger.warning(
                    "Skipping plugin %r — sandbox violation: %s", candidate.name, exc
                )
            except PluginValidationError as exc:
                self._load_errors[candidate.name] = f"validation: {exc}"
                logger.warning(
                    "Skipping plugin %r — validation error: %s", candidate.name, exc
                )
            except Exception as exc:  # noqa: BLE001 — catch-all must log & skip
                self._load_errors[candidate.name] = f"unexpected: {exc}"
                logger.warning(
                    "Skipping plugin %r — unexpected error: %s",
                    candidate.name,
                    exc,
                    exc_info=True,
                )

        return self._plugins

    def _load_single_plugin(self, plugin_dir: Path, manifest_path: Path) -> None:
        """Load and validate one plugin. Raises on any security or validation issue."""

        # 1. Path safety: plugin_dir must be inside the plugins root.
        validate_plugin_path(plugin_dir, self._plugins_dir)

        # 2. manifest_path must be inside plugin_dir.
        validate_file_in_plugin(manifest_path, plugin_dir)

        # 3. Read with size limit.
        raw_text = self._sandbox.read_manifest(manifest_path)

        # 4. Parse JSON — reject non-objects early.
        try:
            raw = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise PluginValidationError(
                f"Invalid JSON in {manifest_path.name}: {exc}"
            ) from exc

        if not isinstance(raw, dict):
            raise PluginValidationError(
                f"Plugin manifest must be a JSON object, got {type(raw).__name__}"
            )

        # 5. Validate with the strict Pydantic schema.
        try:
            manifest = ValidatedPluginManifest(**raw)
        except Exception as exc:
            raise PluginValidationError(
                f"Manifest schema validation failed for {manifest_path.name}: {exc}"
            ) from exc

        self._plugins[manifest.name] = manifest
        logger.debug("Loaded plugin %r (archetype=%r)", manifest.name, manifest.archetype)

    # ------------------------------------------------------------------
    # Read / lookup
    # ------------------------------------------------------------------

    def get_plugin(
        self,
        name: str,
        role: Optional[str] = None,
    ) -> Optional[ValidatedPluginManifest]:
        """Return a loaded plugin by name, or ``None`` if not found.

        Parameters
        ----------
        name:
            Plugin name (e.g. ``"greenfield"``).
        role:
            If not ``None``, checked for :attr:`PluginPermission.READ_PLUGIN`.
        """
        if role is not None:
            require_permission(role, PluginPermission.READ_PLUGIN)
        return self._plugins.get(name)

    def list_plugins(
        self,
        role: Optional[str] = None,
    ) -> List[ValidatedPluginManifest]:
        """Return all loaded plugins.

        Parameters
        ----------
        role:
            If not ``None``, checked for :attr:`PluginPermission.READ_PLUGIN`.
        """
        if role is not None:
            require_permission(role, PluginPermission.READ_PLUGIN)
        return list(self._plugins.values())

    def get_plugin_for_archetype(
        self,
        archetype: str,
        role: Optional[str] = None,
    ) -> Optional[ValidatedPluginManifest]:
        """Find the first plugin whose archetype matches *archetype* (case-insensitive).

        Parameters
        ----------
        archetype:
            Archetype string to match (e.g. ``"greenfield"``).
        role:
            If not ``None``, checked for :attr:`PluginPermission.READ_PLUGIN`.
        """
        if role is not None:
            require_permission(role, PluginPermission.READ_PLUGIN)
        archetype_lower = archetype.lower()
        for plugin in self._plugins.values():
            if plugin.archetype.lower() == archetype_lower:
                return plugin
        return None

    def get_phase_config(
        self,
        plugin_name: str,
        phase: str,
        role: Optional[str] = None,
    ) -> Optional[ValidatedPhaseConfig]:
        """Return the :class:`ValidatedPhaseConfig` for *phase* in *plugin_name*.

        Parameters
        ----------
        plugin_name:
            Plugin to look up.
        phase:
            Phase name (e.g. ``"research"``).
        role:
            If not ``None``, checked for :attr:`PluginPermission.READ_PLUGIN`.
        """
        plugin = self.get_plugin(plugin_name, role=role)
        if plugin is None:
            return None
        return plugin.phases.get(phase)

    # ------------------------------------------------------------------
    # Agent templates
    # ------------------------------------------------------------------

    def get_agents_for_phase(
        self,
        plugin_name: str,
        phase: str,
        role: Optional[str] = None,
    ) -> List[ValidatedAgentTemplate]:
        """Return the agent templates declared for *phase* in *plugin_name*.

        Lazy-loads agent templates on first call.

        Parameters
        ----------
        plugin_name:
            Plugin to look up.
        phase:
            Phase name.
        role:
            If not ``None``, checked for :attr:`PluginPermission.EXECUTE_PLUGIN`.
        """
        if role is not None:
            require_permission(role, PluginPermission.EXECUTE_PLUGIN)

        phase_config = self.get_phase_config(plugin_name, phase)
        if phase_config is None:
            return []

        if plugin_name not in self._agent_templates:
            self.load_agent_templates(plugin_name)

        templates = self._agent_templates.get(plugin_name, {})
        return [
            templates[agent_name]
            for agent_name in phase_config.default_agents
            if agent_name in templates
        ]

    def load_agent_templates(
        self,
        plugin_name: str,
        role: Optional[str] = None,
    ) -> Dict[str, ValidatedAgentTemplate]:
        """Load and validate all agent templates from a plugin's ``agents/`` directory.

        Agent files that fail validation or sandbox checks are skipped with a
        warning; remaining agents load normally.

        Parameters
        ----------
        plugin_name:
            Plugin whose agents to load.
        role:
            If not ``None``, checked for :attr:`PluginPermission.LOAD_PLUGIN`.

        Returns
        -------
        Dict[str, ValidatedAgentTemplate]
            Mapping of agent name → validated template.
        """
        if role is not None:
            require_permission(role, PluginPermission.LOAD_PLUGIN)

        agents_dir = self._get_subdir(plugin_name, "agents")
        loaded: Dict[str, ValidatedAgentTemplate] = {}

        if agents_dir is None or not agents_dir.exists():
            self._agent_templates[plugin_name] = loaded
            return loaded

        for md_file in sorted(agents_dir.glob("*.md")):
            try:
                # Path safety: each file must be inside agents_dir.
                validate_file_in_plugin(md_file, agents_dir)
                template = self._parse_agent_md(md_file)
                if template is not None:
                    loaded[template.name] = template
            except PluginSandboxError as exc:
                logger.warning(
                    "Skipping agent template %r — sandbox error: %s", md_file.name, exc
                )
            except PluginValidationError as exc:
                logger.warning(
                    "Skipping agent template %r — validation error: %s", md_file.name, exc
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Skipping agent template %r — unexpected error: %s",
                    md_file.name,
                    exc,
                    exc_info=True,
                )

        self._agent_templates[plugin_name] = loaded
        return loaded

    def _parse_agent_md(self, path: Path) -> Optional[ValidatedAgentTemplate]:
        """Parse an agent ``.md`` file with YAML frontmatter into a validated template.

        Parameters
        ----------
        path:
            Path to the ``.md`` file (already size-checked by :meth:`_sandbox.read_template`).

        Returns
        -------
        ValidatedAgentTemplate or None
            ``None`` if the file lacks proper frontmatter or a required field.

        Raises
        ------
        PluginSandboxError
            If the file is too large.
        PluginValidationError
            If YAML is malformed or the template fails schema validation.
        """
        raw_text = self._sandbox.read_template(path)

        if not raw_text.startswith("---"):
            return None  # No frontmatter — not an agent template file

        parts = raw_text.split("---", 2)
        if len(parts) < 3:
            return None  # Malformed frontmatter delimiter

        frontmatter_text = parts[1].strip()
        prompt_body = parts[2].strip()

        try:
            meta = yaml.safe_load(frontmatter_text)
        except yaml.YAMLError as exc:
            raise PluginValidationError(
                f"Invalid YAML frontmatter in {path.name!r}: {exc}"
            ) from exc

        if not isinstance(meta, dict):
            raise PluginValidationError(
                f"Frontmatter in {path.name!r} must be a YAML mapping"
            )

        if "name" not in meta:
            return None  # Required field missing — skip silently

        # Pass raw tools value; the Pydantic validator handles both
        # comma-string and list forms.
        try:
            return ValidatedAgentTemplate(
                name=meta["name"],
                description=meta.get("description"),
                model=meta.get("model", "sonnet"),
                tools=meta.get("tools", []),
                system_prompt=prompt_body,
                color=meta.get("color"),
            )
        except Exception as exc:
            raise PluginValidationError(
                f"Agent template schema validation failed for {path.name!r}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Directory helpers
    # ------------------------------------------------------------------

    def get_plugin_dir(self, plugin_name: str) -> Optional[Path]:
        """Return the filesystem directory for *plugin_name*, or ``None``."""
        if plugin_name not in self._plugins:
            return None
        for candidate in self._plugins_dir.iterdir():
            if not candidate.is_dir():
                continue
            manifest_path = candidate / "plugin.json"
            if not manifest_path.exists():
                continue
            try:
                raw = json.loads(manifest_path.read_text(encoding="utf-8"))
                if raw.get("name") == plugin_name:
                    return candidate
            except Exception:
                continue
        return None

    def _get_subdir(self, plugin_name: str, subdir: str) -> Optional[Path]:
        plugin_dir = self.get_plugin_dir(plugin_name)
        if plugin_dir is None:
            return None
        target = plugin_dir / subdir
        return target if target.is_dir() else None

    def get_commands_dir(self, plugin_name: str) -> Optional[Path]:
        """Return the ``commands/`` directory for *plugin_name*, or ``None``."""
        return self._get_subdir(plugin_name, "commands")

    def get_skills_dir(self, plugin_name: str) -> Optional[Path]:
        """Return the ``skills/`` directory for *plugin_name*, or ``None``."""
        return self._get_subdir(plugin_name, "skills")

    def get_workflows_dir(self, plugin_name: str) -> Optional[Path]:
        """Return the ``workflows/`` directory for *plugin_name*, or ``None``."""
        return self._get_subdir(plugin_name, "workflows")

    def get_criteria_overrides(
        self,
        plugin_name: str,
        role: Optional[str] = None,
    ) -> Dict[str, Dict]:
        """Return entry/exit criteria overrides in phase-engine format.

        Parameters
        ----------
        plugin_name:
            Plugin to read overrides from.
        role:
            If not ``None``, checked for :attr:`PluginPermission.READ_PLUGIN`.

        Returns
        -------
        Dict[str, Dict]
            ``{phase_name: {"entry": [...], "exit": [...]}}`` — only phases that
            define at least one non-empty list are included.
        """
        plugin = self.get_plugin(plugin_name, role=role)
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

    def get_load_errors(self) -> Dict[str, str]:
        """Return a mapping of failed plugin directory names to error messages.

        Useful for diagnostics after :meth:`discover_plugins`.
        """
        return dict(self._load_errors)
