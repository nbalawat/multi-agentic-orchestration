-- ============================================================================
-- LINK EXISTING TABLES TO WORKSPACES AND PROJECTS
-- ============================================================================
-- Add workspace_id and project_id columns to existing agent tables
--
-- Dependencies: 9_workspaces.sql, 10_projects.sql, 0_orchestrator_agents.sql, 1_agents.sql
-- Note: Idempotent - uses IF NOT EXISTS pattern for safe re-runs

-- Add workspace_id to orchestrator_agents
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'orchestrator_agents' AND column_name = 'workspace_id'
    ) THEN
        ALTER TABLE orchestrator_agents
            ADD COLUMN workspace_id UUID REFERENCES workspaces(id) ON DELETE SET NULL;
    END IF;
END $$;

-- Add project_id to agents
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'agents' AND column_name = 'project_id'
    ) THEN
        ALTER TABLE agents
            ADD COLUMN project_id UUID REFERENCES projects(id) ON DELETE SET NULL;
    END IF;
END $$;

-- Indexes for the new columns
CREATE INDEX IF NOT EXISTS idx_orchestrator_agents_workspace_id
    ON orchestrator_agents(workspace_id) WHERE workspace_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_agents_project_id
    ON agents(project_id) WHERE project_id IS NOT NULL;

-- Column comments
COMMENT ON COLUMN orchestrator_agents.workspace_id IS 'Workspace this orchestrator is operating in';
COMMENT ON COLUMN agents.project_id IS 'Project this agent is assigned to';
