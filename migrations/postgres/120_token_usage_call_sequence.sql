-- Migration 120: Add call_sequence for per-LLM-call ordering within agent execution
-- Enables time-series analysis of cache behavior (e.g., "call 1 writes cache, call 2 hits, call 3 breaks")
ALTER TABLE token_usage ADD COLUMN IF NOT EXISTS call_sequence INTEGER DEFAULT 0;

-- Index for efficient per-task call ordering queries
CREATE INDEX IF NOT EXISTS idx_token_usage_task_call_seq ON token_usage(task_id, call_sequence);
