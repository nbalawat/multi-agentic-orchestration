# Plan: Plugin-Driven Orchestration System

## Problem Statement

The orchestrator currently has hardcoded phase prompts with `{{PLUGIN_SUPPLEMENT}}` injection. Plugins are supplementary guidance, not the primary driver. We need to invert this: **plugins define HOW each phase works**, the orchestrator decides **WHEN and WHERE** to invoke them.

Multiple plugins (archetypes) should be loadable simultaneously, each project bound to its archetype plugin. The orchestrator should dynamically discover and invoke a plugin's agents, skills, commands, and workflows — not hardcode any archetype-specific logic.

## Architecture Overview

```
┌─────────────────────────────────────┐
│         ORCHESTRATOR AGENT          │
│  (conductor — knows WHEN/WHERE)     │
│                                     │
│  Plugin Registry ← discovers all    │
│  Project Router  ← maps project →   │
│                     plugin          │
│  Phase Dispatcher← invokes plugin   │
│                     assets          │
└──────────┬──────────────────────────┘
           │ creates independent agents with
           │ plugin-provided system prompts
           ▼
┌──────────────────────────────────────┐
│        PLUGIN ASSETS                 │
│                                      │
│  ┌──────────┐  ┌──────────────────┐  │
│  │greenfield│  │data-modernization│  │
│  │  agents/ │  │  agents/         │  │
│  │  skills/ │  │  skills/         │  │
│  │  commands│  │  commands/       │  │
│  │  workflows│ │  workflows/      │  │
│  └──────────┘  └──────────────────┘  │
└──────────────────────────────────────┘
```

## Current State (v0.1.0) vs Target

| Aspect | v0.1.0 | Target |
|--------|--------|--------|
| Plugin role | Supplementary text injection | Primary driver of phase behavior |
| Agent creation | Hardcoded phase prompts + supplement | Plugin agent template IS the prompt |
| Workflow | Appended as guidance text | Orchestrator follows workflow sections |
| Skills/Commands | Not invoked | Orchestrator can invoke via SDK |
| Multi-plugin | Single plugin at a time | Multiple loaded, project-bound |
| Plugin format | Custom `.claude/rapids-plugins/` | SDK-compatible `.claude-plugin/` |
| Discovery | Manual `load_plugin()` | Auto-discovery + manifest scanning |

## Implementation Steps

### Step 1: Plugin Format Migration (SDK-Compatible)
**Goal:** Convert plugins from our custom format to SDK-compatible format.

Current: `.claude/rapids-plugins/greenfield/plugin.json`
Target: `.claude/rapids-plugins/greenfield/.claude-plugin/plugin.json` (SDK standard)

But we ALSO keep our extended `plugin.json` with RAPIDS-specific metadata (phases, entry/exit criteria, default_agents, prompt_supplements). The SDK's `.claude-plugin/plugin.json` is minimal — we extend it.

**Changes:**
- `PluginLoader.discover_plugins()` — Accept both formats (backward compatible)
- Each plugin gets a `rapids-manifest.json` (our extended metadata) alongside the SDK plugin structure
- Agents in `agents/` use SDK-compatible frontmatter format
- Commands in `commands/` → migrate to `skills/<name>/SKILL.md` format

**Files to modify:**
- `orchestrator/backend/modules/plugin_loader.py` — Dual-format discovery
- `.claude/rapids-plugins/greenfield/` — Restructure to SDK format
- New: `.claude/rapids-plugins/greenfield/.claude-plugin/plugin.json`
- Rename: `plugin.json` → `rapids-manifest.json`

### Step 2: Plugin Registry with Multi-Plugin Support
**Goal:** Load multiple plugins simultaneously, bind each project to its plugin.

**New class: `PluginRegistry`** (replaces simple `PluginLoader._plugins` dict)
- `discover_all()` — Scan all plugin directories, load all manifests
- `get_for_project(project_id)` — Return the plugin bound to a project's archetype
- `list_capabilities(plugin_name)` — Enumerate agents, skills, commands, workflows
- `get_agent_template(plugin_name, agent_name)` — Get a specific agent template
- `get_phase_workflow(plugin_name, phase)` — Get workflow for a phase
- `get_phase_skills(plugin_name, phase)` — Get skills available in a phase

**Files to modify:**
- `orchestrator/backend/modules/plugin_loader.py` — Add `PluginRegistry` class
- `orchestrator/backend/modules/workspace_manager.py` — Use registry for project→plugin binding

### Step 3: Plugin-Driven Agent Creation
**Goal:** When creating a phase agent, use the plugin's agent template as the PRIMARY prompt.

**Change `build_phase_agent_prompt()`:**
1. Look up project's plugin via registry
2. Get the plugin's agent template for the phase (e.g., `researcher` for research)
3. Use the agent template's `system_prompt` as the PRIMARY content
4. Inject project context (repo path, phase, existing artifacts)
5. Append workflow guidance from plugin's `workflows/` directory
6. Fall back to generic phase prompts ONLY if plugin has no agent for this phase

**Files to modify:**
- `orchestrator/backend/modules/agent_manager.py` — Update `build_phase_agent_prompt()`

### Step 4: Orchestrator System Prompt — Plugin-Aware
**Goal:** The orchestrator's own system prompt should describe available plugins and their capabilities.

When the orchestrator starts, its system prompt includes:
```
## Available Plugins
### greenfield (v1.0.0)
- Phases: research, analysis, plan, implement, deploy, sustain
- Agents: researcher, architect, planner, feature-builder, tester, deployer, monitor
- Skills: web-research, domain-analysis, solution-design, ...
- Commands: /research, /analyze, /plan, /implement, /deploy, /sustain

### data-modernization (v1.0.0)
- Phases: research, analysis, plan, implement, deploy, sustain
- Agents: data-archeologist, schema-designer, migration-planner, ...
```

This lets the orchestrator intelligently select the right plugin assets.

**Files to modify:**
- `orchestrator/backend/modules/orchestrator_service.py` — Build dynamic system prompt section
- `orchestrator/backend/prompts/orchestrator_agent_system_prompt.md` — Add `{{PLUGIN_CATALOG}}` placeholder

### Step 5: Create 3 Dummy Test Plugins
**Goal:** Test multi-plugin orchestration with different archetypes.

**Plugin 1: `greenfield`** (already exists — restructure only)
- Full RAPIDS lifecycle
- Agents: researcher, architect, planner, feature-builder, deployer, monitor

**Plugin 2: `data-modernization`**
- Focus: Database migration, schema evolution, data pipeline projects
- Agents: data-archeologist (research), schema-designer (analysis), migration-planner (plan), migration-executor (implement)
- Different artifacts: `legacy-schema-analysis.md`, `target-schema-design.md`, `migration-plan.md`

**Plugin 3: `brownfield`**
- Focus: Enhancing/refactoring existing codebases
- Agents: codebase-analyst (research), refactoring-architect (analysis), incremental-planner (plan), refactoring-builder (implement)
- Different artifacts: `codebase-assessment.md`, `tech-debt-register.md`, `refactoring-plan.md`

**Plugin 4: `reverse-engineering`**
- Focus: Understanding and documenting undocumented codebases
- Agents: code-detective (research), system-mapper (analysis), documentation-planner (plan)
- Different artifacts: `system-map.md`, `dependency-graph.md`, `api-surface.md`

**Files to create:**
- `.claude/rapids-plugins/data-modernization/` — Full plugin structure
- `.claude/rapids-plugins/brownfield/` — Full plugin structure
- `.claude/rapids-plugins/reverse-engineering/` — Full plugin structure

### Step 6: Plugin SDK Loading for Independent Agents
**Goal:** When creating an independent agent, load the project's plugin via SDK `plugins` option.

When `AgentManager.create_agent()` creates a `ClaudeSDKClient`:
- Include `plugins=[{"type": "local", "path": plugin_dir}]` in options
- This makes the plugin's agents, skills, and commands available TO the agent
- The agent can invoke `/greenfield:research` or use the researcher agent natively

**Files to modify:**
- `orchestrator/backend/modules/agent_manager.py` — Pass `plugins` to `ClaudeAgentOptions`

### Step 7: MCP Tool — `list_plugin_capabilities`
**Goal:** Give the orchestrator a tool to inspect any plugin's capabilities at runtime.

New MCP tool:
```python
@tool("list_plugin_capabilities",
      "List all agents, skills, commands, and workflows available in a plugin",
      {"plugin_name": str})
```

Returns structured data about what the plugin offers, so the orchestrator can make informed decisions about which assets to invoke.

**Files to modify:**
- `orchestrator/backend/modules/agent_manager.py` — Add new MCP tool

### Step 8: E2E Test Suite
**Goal:** Comprehensive testing across all 4 plugins.

**Test scenarios:**
1. **Multi-plugin discovery:** Load all 4 plugins, verify capabilities enumeration
2. **Project binding:** Create 4 projects, each with different archetype, verify plugin binding
3. **Phase agent creation:** For each plugin, create a research agent and verify it gets the plugin-specific prompt
4. **Workflow guidance:** Verify workflow text is included in agent prompts
5. **Simultaneous projects:** Run 2 projects in different phases simultaneously
6. **Plugin fallback:** Project with unknown archetype falls back to generic prompts
7. **SDK plugin loading:** Verify `plugins` option is passed to `ClaudeAgentOptions`

**Files to create:**
- `tests/test_plugin_registry.py` — Plugin discovery and capability tests
- `tests/test_plugin_agent_creation.py` — Phase agent prompt construction
- `tests/test_multi_plugin_orchestration.py` — Multi-project E2E tests

## Execution Order

1. **Step 1** (Plugin format) + **Step 5** (Dummy plugins) — Can be done in parallel
2. **Step 2** (Plugin registry) — Depends on Step 1
3. **Step 3** (Plugin-driven agents) — Depends on Step 2
4. **Step 4** (Orchestrator prompt) — Depends on Step 2
5. **Step 6** (SDK loading) — Depends on Step 3
6. **Step 7** (MCP tool) — Depends on Step 2
7. **Step 8** (E2E tests) — After all steps, but write tests incrementally

## Risk Mitigation

- **Backward compatibility:** v0.1.0 tagged; all changes additive, not destructive
- **Plugin format:** Support both old and new formats during transition
- **Fallback:** Generic phase prompts always available if plugin has no agent for a phase
- **Testing:** Each step has its own test; E2E suite validates full integration
