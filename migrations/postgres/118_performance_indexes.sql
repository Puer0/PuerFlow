-- Performance indexes for large tables.
-- MUST be run outside a transaction (CONCURRENTLY cannot run inside BEGIN/COMMIT).
-- Run manually via psql during low-traffic window:
--   psql -h <host> -U postgres -d shannon -f 118_performance_indexes.sql

-- task_executions: webhook catchup loop (every 60s)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_task_executions_completed_at
    ON task_executions(completed_at DESC)
    WHERE status IN ('COMPLETED', 'FAILED');

-- task_executions: ListTasks dashboard query
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_task_executions_tenant_user_created
    ON task_executions(tenant_id, user_id, created_at DESC);

-- token_usage: GetTaskStatus model_breakdown
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_token_usage_task_provider_model
    ON token_usage(task_id, provider, model);

-- sessions: ListSessions page load
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sessions_user_tenant_created
    ON sessions(user_id, tenant_id, created_at DESC)
    WHERE deleted_at IS NULL;
