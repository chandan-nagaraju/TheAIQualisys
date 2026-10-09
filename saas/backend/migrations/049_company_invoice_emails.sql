-- Per-company accounts inbox for subscription tax invoices (To + CC).

ALTER TABLE companies ADD COLUMN IF NOT EXISTS invoice_accounts_email VARCHAR(255);
ALTER TABLE companies ADD COLUMN IF NOT EXISTS invoice_cc_emails JSONB;
