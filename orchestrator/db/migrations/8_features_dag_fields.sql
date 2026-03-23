-- ============================================================================
-- FEATURES TABLE — DAG FIELDS
-- ============================================================================
-- Add columns needed for database-primary DAG storage.
-- Previously these fields only existed in the feature_dag.json file.
--
-- Dependencies: features table from 4_features.sql
-- Note: Idempotent — ADD COLUMN IF NOT EXISTS allows safe re-runs

ALTER TABLE features ADD COLUMN IF NOT EXISTS category TEXT;
ALTER TABLE features ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;
ALTER TABLE features ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;
ALTER TABLE features ADD COLUMN IF NOT EXISTS assigned_agent TEXT;

COMMENT ON COLUMN features.category IS 'Feature category (e.g., backend, frontend, infra)';
COMMENT ON COLUMN features.started_at IS 'Timestamp when feature moved to in_progress';
COMMENT ON COLUMN features.completed_at IS 'Timestamp when feature moved to complete';
COMMENT ON COLUMN features.assigned_agent IS 'Name of the agent assigned to implement this feature';
