-- ============================================================================
-- EXECUTION RUNS TABLE
-- ============================================================================
-- Tracks the lifecycle of each feature execution: which agent is working
-- on which feature, its status, cost, test results, and files changed.
-- This is the single source of truth for the Implementation Flow UI.
--
-- Dependencies: projects, features tables

CREATE TABLE IF NOT EXISTS execution_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    feature_id UUID NOT NULL REFERENCES features(id) ON DELETE CASCADE,
    feature_name TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    agent_id UUID,
    status TEXT CHECK (status IN ('queued', 'building', 'testing', 'complete', 'failed')) DEFAULT 'queued',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    total_cost DECIMAL(10,4) DEFAULT 0.0000,
    test_results JSONB DEFAULT '{}',
    files_changed JSONB DEFAULT '[]',
    error_message TEXT,
    wave_number INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_execution_runs_project_id ON execution_runs(project_id);
CREATE INDEX IF NOT EXISTS idx_execution_runs_feature_id ON execution_runs(feature_id);
CREATE INDEX IF NOT EXISTS idx_execution_runs_status ON execution_runs(status);
CREATE INDEX IF NOT EXISTS idx_execution_runs_project_status ON execution_runs(project_id, status);

-- Comments
COMMENT ON TABLE execution_runs IS 'Tracks feature execution lifecycle — single source of truth for Implementation Flow UI';
COMMENT ON COLUMN execution_runs.status IS 'queued=waiting, building=agent executing, testing=running tests, complete=done+passed, failed=tests failed or error';
COMMENT ON COLUMN execution_runs.test_results IS 'JSON: {passed: N, failed: N, skipped: N, errors: [...], output: "last 2k chars"}';
COMMENT ON COLUMN execution_runs.files_changed IS 'JSON array: [{path: "src/foo.py", action: "modified"}, ...]';
COMMENT ON COLUMN execution_runs.wave_number IS 'Which parallel execution wave this feature belongs to (0-based)';
