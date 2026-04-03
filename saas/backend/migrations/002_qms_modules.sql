-- QMS module subscriptions & trials (TheAIQualisys — non-FIR modules).
-- Apply with: python scripts/apply_schema_extensions.py

CREATE TABLE IF NOT EXISTS module_subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES company_users(id) ON DELETE CASCADE,
    module_name VARCHAR(64) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_module_subscriptions_user_module UNIQUE (user_id, module_name)
);
CREATE INDEX IF NOT EXISTS ix_module_subscriptions_user_id ON module_subscriptions(user_id);

CREATE TABLE IF NOT EXISTS module_trials (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES company_users(id) ON DELETE CASCADE,
    module_name VARCHAR(64) NOT NULL,
    trial_start DATE NOT NULL,
    trial_end DATE NOT NULL,
    usage_limit INTEGER NOT NULL DEFAULT 5,
    actions_used INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_module_trials_user_module UNIQUE (user_id, module_name)
);
CREATE INDEX IF NOT EXISTS ix_module_trials_user_id ON module_trials(user_id);

-- Example paid access (adjust user_id, dates, module_name):
-- INSERT INTO module_subscriptions (user_id, module_name, status, start_date, end_date)
-- VALUES (1, 'drawings_directory', 'active', CURRENT_DATE, CURRENT_DATE + INTERVAL '365 days');
