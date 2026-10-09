-- Manual admin-triggered subscription reminder emails (audit trail).
CREATE TABLE IF NOT EXISTS admin_subscription_reminders (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies (id) ON DELETE CASCADE,
    reminder_type VARCHAR(32) NOT NULL,
    reports_generated INTEGER NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    email_status VARCHAR(16) NOT NULL,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS ix_admin_subscription_reminders_company_id ON admin_subscription_reminders (company_id);
CREATE INDEX IF NOT EXISTS ix_admin_subscription_reminders_sent_at ON admin_subscription_reminders (sent_at);
