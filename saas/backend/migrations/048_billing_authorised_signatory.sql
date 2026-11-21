-- Authorised signatory on tax invoices (name + optional image path).

ALTER TABLE billing_settings ADD COLUMN IF NOT EXISTS authorised_signatory_name VARCHAR(255);
ALTER TABLE billing_settings ADD COLUMN IF NOT EXISTS authorised_signatory_path VARCHAR(1024);
