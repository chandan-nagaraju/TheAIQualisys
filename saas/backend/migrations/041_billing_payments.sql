-- SaaS subscription payment records for Platform Admin Payment Verification.
-- Desktop UPI payments remain in desktop_payments (Desktop Apps). This table is FIR/QMS billing only.
-- Verify/reject workflow is not implemented in this migration.

CREATE TABLE IF NOT EXISTS billing_payments (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies (id) ON DELETE CASCADE,
    user_id INTEGER NULL REFERENCES company_users (id) ON DELETE SET NULL,
    plan_name VARCHAR(64) NOT NULL,
    amount_inr INTEGER NOT NULL,
    payment_method VARCHAR(64) NOT NULL DEFAULT 'UPI',
    reference_note TEXT NULL,
    payment_date TIMESTAMPTZ NOT NULL DEFAULT now(),
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    proof_path VARCHAR(1024) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_billing_payments_company_id ON billing_payments (company_id);
CREATE INDEX IF NOT EXISTS ix_billing_payments_status ON billing_payments (status);
CREATE INDEX IF NOT EXISTS ix_billing_payments_payment_date ON billing_payments (payment_date);
