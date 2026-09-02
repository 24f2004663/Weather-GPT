-- ============================================================================
-- WeatherGPT Migration: 20260902_seen_alerts.sql
-- Persistent Deduplication Table for Emergency Alert Ingestion Engine
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.seen_alerts (
    alert_id VARCHAR(128) PRIMARY KEY,
    source VARCHAR(64) NOT NULL,
    severity VARCHAR(32),
    is_active BOOLEAN DEFAULT TRUE,
    first_seen_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_seen_alerts_source ON public.seen_alerts(source);
CREATE INDEX IF NOT EXISTS idx_seen_alerts_active ON public.seen_alerts(is_active);

-- Enable Row Level Security (RLS) - Server-side service_role only
ALTER TABLE public.seen_alerts ENABLE ROW LEVEL SECURITY;

GRANT USAGE ON SCHEMA public TO service_role;
GRANT ALL ON TABLE public.seen_alerts TO service_role;

REVOKE ALL ON TABLE public.seen_alerts FROM anon, authenticated;

DROP POLICY IF EXISTS "Service role full access on seen_alerts" ON public.seen_alerts;
CREATE POLICY "Service role full access on seen_alerts"
    ON public.seen_alerts
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);
