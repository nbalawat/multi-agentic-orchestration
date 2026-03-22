-- ============================================================================
-- FEATURES TABLE
-- ============================================================================
-- Features within a project, with dependency tracking and agent assignment
--
-- Dependencies: 10_projects.sql (projects table), 1_agents.sql (agents table)
-- Constraints:
--   - project_id references projects(id)
--   - assigned_agent_id references agents(id) (optional)
--   - depends_on and acceptance_criteria stored as JSONB arrays

CREATE TABLE IF NOT EXISTS features (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    depends_on JSONB DEFAULT '[]'::jsonb,
    acceptance_criteria JSONB DEFAULT '[]'::jsonb,
    status TEXT CHECK (status IN (
        'planned', 'in_progress', 'complete', 'blocked', 'deferred'
    )) DEFAULT 'planned',
    priority INTEGER DEFAULT 0,
    estimated_complexity TEXT CHECK (estimated_complexity IN ('low', 'medium', 'high')),
    assigned_agent_id UUID REFERENCES agents(id) ON DELETE SET NULL,
    spec_file TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, name)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_features_project_id ON features(project_id);
CREATE INDEX IF NOT EXISTS idx_features_status ON features(status);
CREATE INDEX IF NOT EXISTS idx_features_priority ON features(priority DESC);
CREATE INDEX IF NOT EXISTS idx_features_assigned_agent_id ON features(assigned_agent_id) WHERE assigned_agent_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_features_estimated_complexity ON features(estimated_complexity) WHERE estimated_complexity IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_features_updated_at ON features(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_features_project_status ON features(project_id, status);

-- Trigger function for updated_at
CREATE OR REPLACE FUNCTION update_features_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger
DROP TRIGGER IF EXISTS update_features_updated_at ON features;
CREATE TRIGGER update_features_updated_at
  BEFORE UPDATE ON features
  FOR EACH ROW
  EXECUTE FUNCTION update_features_updated_at();

-- Table and column comments
COMMENT ON TABLE features IS 'Features within a project with dependency tracking and agent assignment';
COMMENT ON COLUMN features.id IS 'Unique feature identifier';
COMMENT ON COLUMN features.project_id IS 'Parent project reference';
COMMENT ON COLUMN features.name IS 'Feature name (unique within project)';
COMMENT ON COLUMN features.description IS 'Feature description';
COMMENT ON COLUMN features.depends_on IS 'List of feature IDs this feature depends on (JSONB array)';
COMMENT ON COLUMN features.acceptance_criteria IS 'List of acceptance criteria (JSONB array of strings)';
COMMENT ON COLUMN features.status IS 'Feature status: planned, in_progress, complete, blocked, deferred';
COMMENT ON COLUMN features.priority IS 'Feature priority (higher = more important)';
COMMENT ON COLUMN features.estimated_complexity IS 'Estimated complexity: low, medium, high';
COMMENT ON COLUMN features.assigned_agent_id IS 'Agent assigned to implement this feature';
COMMENT ON COLUMN features.spec_file IS 'Path to feature specification file';
COMMENT ON COLUMN features.metadata IS 'Feature configuration (JSONB)';
