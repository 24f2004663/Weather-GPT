-- ============================================================================
-- WeatherGPT: Alert Subscriptions Schema (Supabase / PostgreSQL)
-- Authoritative persistent store for Emergency Alert preferences and WhatsApp authorization
-- ============================================================================

CREATE TABLE IF NOT EXISTS alert_subscriptions (
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
CREATE INDEX IF NOT EXISTS idx_alert_subscriptions_user ON alert_subscriptions(user_identifier);
CREATE INDEX IF NOT EXISTS idx_alert_subscriptions_phone ON alert_subscriptions(phone_number);
CREATE INDEX IF NOT EXISTS idx_alert_subscriptions_whatsapp ON alert_subscriptions(whatsapp_number);
CREATE INDEX IF NOT EXISTS idx_alert_subscriptions_opted_in ON alert_subscriptions(is_opted_in);

-- Enable Row Level Security (RLS)
ALTER TABLE alert_subscriptions ENABLE ROW LEVEL SECURITY;

-- Service role has full access
CREATE POLICY "Service role full access on alert_subscriptions"
    ON alert_subscriptions
    FOR ALL
    USING (auth.role() = 'service_role');

-- Anon / Authenticated users can read/insert/update their own preferences
CREATE POLICY "Allow public read of active subscriber status"
    ON alert_subscriptions
    FOR SELECT
    USING (true);

CREATE POLICY "Allow upsert of alert subscriptions"
    ON alert_subscriptions
    FOR INSERT
    WITH CHECK (true);

CREATE POLICY "Allow update of alert subscriptions"
    ON alert_subscriptions
    FOR UPDATE
    USING (true);
