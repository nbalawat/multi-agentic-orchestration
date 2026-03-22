-- ============================================================================
-- PROJECTS TABLE
-- ============================================================================
-- Software projects within a workspace, tracking lifecycle phases
--
-- Dependencies: 9_workspaces.sql (workspaces table)
-- Constraints:
--   - workspace_id references workspaces(id)
--   - archetype must be a known project type
--   - current_phase must be a valid RAPIDS phase
--   - phase_status must be a valid status

CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    repo_path TEXT NOT NULL,
    repo_url TEXT,
    archetype TEXT NOT NULL CHECK (archetype IN (
        'greenfield', 'brownfield', 'enhancement', 'bugfix',
        'data-modernization', 'agentic-ai', 'reverse-engineering'
    )),
    current_phase TEXT CHECK (current_phase IN (
        'research', 'analysis', 'plan', 'implement', 'deploy', 'sustain'
    )) DEFAULT 'research',
    phase_status TEXT CHECK (phase_status IN (
        'not_started', 'in_progress', 'blocked', 'review', 'complete'
    )) DEFAULT 'not_started',
    plugin_id TEXT,
    priority INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}'::jsonb,
    archived BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (workspace_id, name)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_projects_workspace_id ON projects(workspace_id);
CREATE INDEX IF NOT EXISTS idx_projects_archetype ON projects(archetype);
CREATE INDEX IF NOT EXISTS idx_projects_current_phase ON projects(current_phase);
CREATE INDEX IF NOT EXISTS idx_projects_phase_status ON projects(phase_status);
CREATE INDEX IF NOT EXISTS idx_projects_priority ON projects(priority DESC);
CREATE INDEX IF NOT EXISTS idx_projects_archived ON projects(archived);
CREATE INDEX IF NOT EXISTS idx_projects_updated_at ON projects(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_projects_plugin_id ON projects(plugin_id) WHERE plugin_id IS NOT NULL;

-- Trigger function for updated_at
CREATE OR REPLACE FUNCTION update_projects_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger
DROP TRIGGER IF EXISTS update_projects_updated_at ON projects;
CREATE TRIGGER update_projects_updated_at
  BEFORE UPDATE ON projects
  FOR EACH ROW
  EXECUTE FUNCTION update_projects_updated_at();

-- Table and column comments
COMMENT ON TABLE projects IS 'Software projects within a workspace with RAPIDS lifecycle tracking';
COMMENT ON COLUMN projects.id IS 'Unique project identifier';
COMMENT ON COLUMN projects.workspace_id IS 'Parent workspace reference';
COMMENT ON COLUMN projects.name IS 'Project name (unique within workspace)';
COMMENT ON COLUMN projects.repo_path IS 'Local repository filesystem path';
COMMENT ON COLUMN projects.repo_url IS 'Remote repository URL (e.g., GitHub)';
COMMENT ON COLUMN projects.archetype IS 'Project type: greenfield, brownfield, enhancement, bugfix, data-modernization, agentic-ai, reverse-engineering';
COMMENT ON COLUMN projects.current_phase IS 'Current RAPIDS phase: research, analysis, plan, implement, deploy, sustain';
COMMENT ON COLUMN projects.phase_status IS 'Status of current phase: not_started, in_progress, blocked, review, complete';
COMMENT ON COLUMN projects.plugin_id IS 'Optional plugin identifier for archetype-specific behavior';
COMMENT ON COLUMN projects.priority IS 'Project priority (higher = more important)';
COMMENT ON COLUMN projects.archived IS 'Soft delete flag';
COMMENT ON COLUMN projects.metadata IS 'Project configuration (JSONB)';
