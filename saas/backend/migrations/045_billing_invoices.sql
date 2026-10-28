-- SaaS subscription invoices (not tenant FIR invoices_v2) plus seller billing settings.
-- Customer GST/address lives on companies (existing tenant), seller GST on billing_settings.

ALTER TABLE companies ADD COLUMN IF NOT EXISTS billing_address TEXT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS billing_city VARCHAR(128);
ALTER TABLE companies ADD COLUMN IF NOT EXISTS billing_state VARCHAR(128);
ALTER TABLE companies ADD COLUMN IF NOT EXISTS billing_state_code VARCHAR(8);
ALTER TABLE companies ADD COLUMN IF NOT EXISTS billing_pincode VARCHAR(16);
ALTER TABLE companies ADD COLUMN IF NOT EXISTS gstin VARCHAR(32);
ALTER TABLE companies ADD COLUMN IF NOT EXISTS phone VARCHAR(32);

CREATE TABLE IF NOT EXISTS billing_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    business_name VARCHAR(255),
    business_address TEXT,
    gstin VARCHAR(32),
    state VARCHAR(128),
    state_code VARCHAR(8),
    email VARCHAR(255),
    phone VARCHAR(32),
    logo_path VARCHAR(1024),
    invoice_prefix VARCHAR(16) NOT NULL DEFAULT 'INV-',
    cgst_rate NUMERIC(6, 3) NOT NULL DEFAULT 9,
    sgst_rate NUMERIC(6, 3) NOT NULL DEFAULT 9,
    igst_rate NUMERIC(6, 3) NOT NULL DEFAULT 18,
    terms_notes TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO billing_settings (id, invoice_prefix, cgst_rate, sgst_rate, igst_rate)
VALUES (1, 'INV-', 9, 9, 18)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS billing_invoices (
    id SERIAL PRIMARY KEY,
    invoice_number VARCHAR(32) NOT NULL UNIQUE,
    payment_id INTEGER NOT NULL REFERENCES billing_payments (id) ON DELETE RESTRICT,
    company_id INTEGER NOT NULL REFERENCES companies (id) ON DELETE CASCADE,
    user_id INTEGER NULL REFERENCES company_users (id) ON DELETE SET NULL,
    module_key VARCHAR(64),
    module_name VARCHAR(255),
    plan_name VARCHAR(64) NOT NULL,
    billing_period VARCHAR(32),
    invoice_date DATE NOT NULL,
    subscription_start_date DATE,
    subscription_end_date DATE,
    subtotal NUMERIC(14, 2) NOT NULL,
    taxable_amount NUMERIC(14, 2) NOT NULL,
    cgst NUMERIC(14, 2) NOT NULL DEFAULT 0,
    sgst NUMERIC(14, 2) NOT NULL DEFAULT 0,
    igst NUMERIC(14, 2) NOT NULL DEFAULT 0,
    total_tax NUMERIC(14, 2) NOT NULL DEFAULT 0,
    grand_total NUMERIC(14, 2) NOT NULL,
    currency VARCHAR(8) NOT NULL DEFAULT 'INR',
    tax_mode VARCHAR(16) NOT NULL,
    cgst_rate NUMERIC(6, 3),
    sgst_rate NUMERIC(6, 3),
    igst_rate NUMERIC(6, 3),
    status VARCHAR(32) NOT NULL DEFAULT 'generated',
    pdf_path VARCHAR(1024),
    line_description TEXT,
    snapshot JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_billing_invoices_one_generated_per_payment
  ON billing_invoices (payment_id)
  WHERE status = 'generated';

CREATE INDEX IF NOT EXISTS ix_billing_invoices_company_id ON billing_invoices (company_id);
CREATE INDEX IF NOT EXISTS ix_billing_invoices_status ON billing_invoices (status);
CREATE INDEX IF NOT EXISTS ix_billing_invoices_invoice_date ON billing_invoices (invoice_date);
