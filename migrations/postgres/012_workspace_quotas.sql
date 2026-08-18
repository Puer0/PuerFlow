-- Migration: Add workspace quota columns to auth.tenants
-- Purpose: Enable tiered workspace retention and storage limits per tenant

-- Add workspace quota columns with sensible defaults
ALTER TABLE auth.tenants
    ADD COLUMN IF NOT EXISTS workspace_retention_days INTEGER DEFAULT 7,
    ADD COLUMN IF NOT EXISTS workspace_max_size_gb INTEGER DEFAULT 5;

-- Add comments for documentation
COMMENT ON COLUMN auth.tenants.workspace_retention_days IS 'Number of days to retain workspace files before cleanup (default: 7 for free tier)';
COMMENT ON COLUMN auth.tenants.workspace_max_size_gb IS 'Maximum workspace storage in GB, approximated as 1GB per session (default: 5 for free tier)';

-- Update existing tenants based on their plan if applicable
-- (Assumes tenants.plan column exists; if not, this is a no-op)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'auth' AND table_name = 'tenants' AND column_name = 'plan'
    ) THEN
        -- Pro tier: 30 days retention, 50GB max
        UPDATE auth.tenants
        SET workspace_retention_days = 30, workspace_max_size_gb = 50
        WHERE plan = 'pro' AND workspace_retention_days = 7;

        -- Enterprise tier: 90 days retention, 500GB max
        UPDATE auth.tenants
        SET workspace_retention_days = 90, workspace_max_size_gb = 500
        WHERE plan = 'enterprise' AND workspace_retention_days = 7;
    END IF;
END $$;
