-- Extra TheAIQualisys seller profile columns on the existing billing_settings singleton.
-- Invoice prefix / GST rates stay on this table but are not edited from Billing Settings UI.

ALTER TABLE billing_settings ADD COLUMN IF NOT EXISTS legal_business_name VARCHAR(255);
ALTER TABLE billing_settings ADD COLUMN IF NOT EXISTS address_line1 VARCHAR(255);
ALTER TABLE billing_settings ADD COLUMN IF NOT EXISTS address_line2 VARCHAR(255);
ALTER TABLE billing_settings ADD COLUMN IF NOT EXISTS city VARCHAR(128);
ALTER TABLE billing_settings ADD COLUMN IF NOT EXISTS pincode VARCHAR(16);
ALTER TABLE billing_settings ADD COLUMN IF NOT EXISTS country VARCHAR(64);
ALTER TABLE billing_settings ADD COLUMN IF NOT EXISTS website VARCHAR(255);
ALTER TABLE billing_settings ADD COLUMN IF NOT EXISTS pan VARCHAR(16);

UPDATE billing_settings
SET country = COALESCE(NULLIF(TRIM(country), ''), 'India')
WHERE id = 1;
