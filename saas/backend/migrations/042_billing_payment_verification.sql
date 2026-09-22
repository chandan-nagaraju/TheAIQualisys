-- Extend billing_payments for Payment Done + Admin verify/reject.
-- Adds Admin in-app notifications (none existed).

ALTER TABLE billing_payments ADD COLUMN IF NOT EXISTS module_key VARCHAR(64);
ALTER TABLE billing_payments ADD COLUMN IF NOT EXISTS module_label VARCHAR(255);
ALTER TABLE billing_payments ADD COLUMN IF NOT EXISTS plan_type VARCHAR(64);
ALTER TABLE billing_payments ADD COLUMN IF NOT EXISTS billing_period VARCHAR(32);
ALTER TABLE billing_payments ADD COLUMN IF NOT EXISTS subscription_duration VARCHAR(64);
ALTER TABLE billing_payments ADD COLUMN IF NOT EXISTS currency VARCHAR(8) NOT NULL DEFAULT 'INR';
ALTER TABLE billing_payments ADD COLUMN IF NOT EXISTS pricing_snapshot JSONB;
ALTER TABLE billing_payments ADD COLUMN IF NOT EXISTS payment_code VARCHAR(32);
ALTER TABLE billing_payments ADD COLUMN IF NOT EXISTS payment_submitted_at TIMESTAMPTZ;
ALTER TABLE billing_payments ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE billing_payments ADD COLUMN IF NOT EXISTS verified_by_admin_id INTEGER NULL REFERENCES platform_admins(id) ON DELETE SET NULL;
ALTER TABLE billing_payments ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ;
ALTER TABLE billing_payments ADD COLUMN IF NOT EXISTS rejected_by_admin_id INTEGER NULL REFERENCES platform_admins(id) ON DELETE SET NULL;
ALTER TABLE billing_payments ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMPTZ;
ALTER TABLE billing_payments ADD COLUMN IF NOT EXISTS rejection_reason VARCHAR(64);
ALTER TABLE billing_payments ADD COLUMN IF NOT EXISTS rejection_note TEXT;
ALTER TABLE billing_payments ADD COLUMN IF NOT EXISTS customer_name_snapshot VARCHAR(255);
ALTER TABLE billing_payments ADD COLUMN IF NOT EXISTS company_name_snapshot VARCHAR(255);
ALTER TABLE billing_payments ADD COLUMN IF NOT EXISTS email_snapshot VARCHAR(255);

UPDATE billing_payments SET status = 'pending_verification' WHERE status = 'pending';
UPDATE billing_payments SET payment_submitted_at = COALESCE(payment_submitted_at, payment_date, created_at)
  WHERE payment_submitted_at IS NULL;
UPDATE billing_payments SET module_key = COALESCE(module_key, 'fir');
UPDATE billing_payments SET module_label = COALESCE(module_label, 'FIR');
UPDATE billing_payments SET plan_type = COALESCE(plan_type, plan_name);
UPDATE billing_payments SET billing_period = COALESCE(billing_period, 'MONTHLY');
UPDATE billing_payments SET subscription_duration = COALESCE(subscription_duration, '1 Month');
UPDATE billing_payments SET payment_code = 'PAY-' || LPAD(id::text, 5, '0') WHERE payment_code IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_billing_payments_one_pending_per_selection
  ON billing_payments (company_id, module_key, plan_type, billing_period)
  WHERE status = 'pending_verification';

CREATE TABLE IF NOT EXISTS admin_notifications (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    link_path VARCHAR(512) NOT NULL,
    payment_id INTEGER NULL REFERENCES billing_payments(id) ON DELETE SET NULL,
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_admin_notifications_created_at ON admin_notifications (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_admin_notifications_is_read ON admin_notifications (is_read);
