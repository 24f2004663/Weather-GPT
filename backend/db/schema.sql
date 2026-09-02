-- ============================================================================
-- WeatherGPT: Alert Subscriptions Schema (Supabase / PostgreSQL)
-- Authoritative persistent store for Emergency Alert preferences and WhatsApp authorization
-- Production Security Model: Server-Side Service Role Access Only
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.alert_subscriptions (
    subscription_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_identifier VARCHAR(64) UNIQUE NOT NULL,
    phone_number VARCHAR(30),
    whatsapp_number VARCHAR(30),
    preferred_language VARCHAR(10) DEFAULT 'en',
    enabled_channels TEXT[] DEFAULT ARRAY['WEB_PUSH']::TEXT[],
    min_severity_threshold VARCHAR(20) DEFAULT 'Severe',
    target_states TEXT[] DEFAULT ARRAY[]::TEXT[],
    target_districts TEXT[] DEFAULT ARRAY[]::TEXT[],
    push_subscription JSONB,
    is_opted_in BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indices for rapid query and authorization lookups
CREATE INDEX IF NOT EXISTS idx_alert_subscriptions_user ON public.alert_subscriptions(user_identifier);
CREATE INDEX IF NOT EXISTS idx_alert_subscriptions_phone ON public.alert_subscriptions(phone_number);
CREATE INDEX IF NOT EXISTS idx_alert_subscriptions_whatsapp ON public.alert_subscriptions(whatsapp_number);
CREATE INDEX IF NOT EXISTS idx_alert_subscriptions_opted_in ON public.alert_subscriptions(is_opted_in);

-- 1. Enable Row Level Security (RLS)
ALTER TABLE public.alert_subscriptions ENABLE ROW LEVEL SECURITY;

-- 2. Grant table & schema permissions ONLY to service_role (server-side Render FastAPI)
GRANT USAGE ON SCHEMA public TO service_role;
GRANT ALL ON TABLE public.alert_subscriptions TO service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role;

-- 3. Explicitly REVOKE all permissions from anon and authenticated roles
REVOKE ALL ON TABLE public.alert_subscriptions FROM anon, authenticated;

-- 4. Clean up any permissive public policies
DROP POLICY IF EXISTS "Allow public read of active subscriber status" ON public.alert_subscriptions;
DROP POLICY IF EXISTS "Allow upsert of alert subscriptions" ON public.alert_subscriptions;
DROP POLICY IF EXISTS "Allow update of alert subscriptions" ON public.alert_subscriptions;
DROP POLICY IF EXISTS "Allow delete of alert subscriptions" ON public.alert_subscriptions;
DROP POLICY IF EXISTS "Service role full access on alert_subscriptions" ON public.alert_subscriptions;

-- 5. Dedicated policy for service_role
CREATE POLICY "Service role full access on alert_subscriptions"
    ON public.alert_subscriptions
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- ============================================================================
-- WeatherGPT: Persistent Alert Deduplication Table (seen_alerts)
-- Tracks processed disaster alerts for deduplication across backend restarts
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.seen_alerts (
    alert_id VARCHAR(128) PRIMARY KEY,
    source VARCHAR(64) NOT NULL,
    severity VARCHAR(30) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    last_seen_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE public.seen_alerts ENABLE ROW LEVEL SECURITY;
GRANT ALL ON TABLE public.seen_alerts TO service_role;
REVOKE ALL ON TABLE public.seen_alerts FROM anon, authenticated;

DROP POLICY IF EXISTS "Service role full access on seen_alerts" ON public.seen_alerts;
CREATE POLICY "Service role full access on seen_alerts"
    ON public.seen_alerts
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);
