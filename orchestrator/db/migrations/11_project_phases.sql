-- ============================================================================
-- PROJECT_PHASES TABLE
-- ============================================================================
-- Phase history and transition tracking for projects
--
-- Dependencies: 10_projects.sql (projects table)
-- Constraints:
--   - project_id references projects(id)
--   - Each project can have at most one record per phase

CREATE TABLE IF NOT EXISTS project_phases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    phase TEXT NOT NULL CHECK (phase IN (
        'research', 'analysis', 'plan', 'implement', 'deploy', 'sustain'
    )),
    status TEXT CHECK (status IN (
        'not_started', 'in_progress', 'blocked', 'review', 'complete', 'skipped'
    )) DEFAULT 'not_started',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    entry_criteria_met BOOLEAN DEFAULT false,
    exit_criteria_met BOOLEAN DEFAULT false,
    artifacts JSONB DEFAULT '{}'::jsonb,
    notes TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, phase)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_project_phases_project_id ON project_phases(project_id);
CREATE INDEX IF NOT EXISTS idx_project_phases_phase ON project_phases(phase);
CREATE INDEX IF NOT EXISTS idx_project_phases_status ON project_phases(status);
CREATE INDEX IF NOT EXISTS idx_project_phases_project_phase ON project_phases(project_id, phase);
CREATE INDEX IF NOT EXISTS idx_project_phases_updated_at ON project_phases(updated_at DESC);

-- Trigger function for updated_at
CREATE OR REPLACE FUNCTION update_project_phases_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger
DROP TRIGGER IF EXISTS update_project_phases_updated_at ON project_phases;
CREATE TRIGGER update_project_phases_updated_at
  BEFORE UPDATE ON project_phases
  FOR EACH ROW
  EXECUTE FUNCTION update_project_phases_updated_at();

-- Table and column comments
COMMENT ON TABLE project_phases IS 'Phase history and transition tracking for RAPIDS lifecycle';
COMMENT ON COLUMN project_phases.id IS 'Unique phase record identifier';
COMMENT ON COLUMN project_phases.project_id IS 'Parent project reference';
COMMENT ON COLUMN project_phases.phase IS 'RAPIDS phase: research, analysis, plan, implement, deploy, sustain';
COMMENT ON COLUMN project_phases.status IS 'Phase status: not_started, in_progress, blocked, review, complete, skipped';
COMMENT ON COLUMN project_phases.started_at IS 'When work on this phase began';
COMMENT ON COLUMN project_phases.completed_at IS 'When this phase was completed';
COMMENT ON COLUMN project_phases.entry_criteria_met IS 'Whether entry criteria have been satisfied';
COMMENT ON COLUMN project_phases.exit_criteria_met IS 'Whether exit criteria have been satisfied';
COMMENT ON COLUMN project_phases.artifacts IS 'Phase artifacts and deliverables (JSONB)';
COMMENT ON COLUMN project_phases.notes IS 'Free-form notes about the phase';
COMMENT ON COLUMN project_phases.metadata IS 'Phase configuration (JSONB)';
