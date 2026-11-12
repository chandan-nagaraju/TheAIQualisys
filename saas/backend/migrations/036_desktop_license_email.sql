-- Phase 5: license email delivery tracking (My Licenses / reveal / resend).
-- Prerequisite: 032–035. Does not modify prior migration files.
-- Do NOT run against production from this agent; report as deploy-time step.

CREATE TABLE IF NOT EXISTS desktop_license_email_deliveries (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL UNIQUE REFERENCES desktop_orders(id) ON DELETE CASCADE,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES company_users(id) ON DELETE CASCADE,
    to_email VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_attempted_at TIMESTAMPTZ NULL,
    sent_at TIMESTAMPTZ NULL,
    last_error TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_desktop_license_email_user
  ON desktop_license_email_deliveries (user_id);

CREATE INDEX IF NOT EXISTS ix_desktop_license_email_status
  ON desktop_license_email_deliveries (status);

COMMENT ON TABLE desktop_license_email_deliveries IS
  'One license-email delivery record per order. Email failure must not roll back minted licenses.';
