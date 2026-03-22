-- ============================================================================
-- WORKSPACES TABLE
-- ============================================================================
-- Top-level workspace container for organizing projects
--
-- Dependencies: None
-- Constraints:
--   - name must be unique

CREATE TABLE IF NOT EXISTS workspaces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    root_path TEXT,
    status TEXT CHECK (status IN ('active', 'archived', 'paused')) DEFAULT 'active',
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_workspaces_status ON workspaces(status);
CREATE INDEX IF NOT EXISTS idx_workspaces_name ON workspaces(name);
CREATE INDEX IF NOT EXISTS idx_workspaces_updated_at ON workspaces(updated_at DESC);

-- Trigger function for updated_at
CREATE OR REPLACE FUNCTION update_workspaces_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger
DROP TRIGGER IF EXISTS update_workspaces_updated_at ON workspaces;
CREATE TRIGGER update_workspaces_updated_at
  BEFORE UPDATE ON workspaces
  FOR EACH ROW
  EXECUTE FUNCTION update_workspaces_updated_at();

-- Table and column comments
COMMENT ON TABLE workspaces IS 'Top-level workspace container for organizing projects';
COMMENT ON COLUMN workspaces.id IS 'Unique workspace identifier';
COMMENT ON COLUMN workspaces.name IS 'Unique workspace name';
COMMENT ON COLUMN workspaces.description IS 'Optional workspace description';
COMMENT ON COLUMN workspaces.root_path IS 'Root filesystem path for workspace';
COMMENT ON COLUMN workspaces.status IS 'Workspace status: active, archived, paused';
COMMENT ON COLUMN workspaces.metadata IS 'Workspace configuration (JSONB)';
