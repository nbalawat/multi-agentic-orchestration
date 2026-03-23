-- ============================================================================
-- AGENTS TABLE — Allow 'completed' status
-- ============================================================================
-- The cleanup hook sets status to 'completed' but the CHECK constraint
-- only allowed 'complete'. This adds 'completed' as a valid status.

ALTER TABLE agents DROP CONSTRAINT IF EXISTS agents_status_check;
ALTER TABLE agents ADD CONSTRAINT agents_status_check
  CHECK (status IN ('idle', 'executing', 'waiting', 'blocked', 'complete', 'completed'));
