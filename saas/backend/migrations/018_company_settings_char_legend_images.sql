-- Legend images for special characteristics (Critical, Safety, Important) on FIR reports.
ALTER TABLE company_settings ADD COLUMN IF NOT EXISTS char_critical_path VARCHAR(512);
ALTER TABLE company_settings ADD COLUMN IF NOT EXISTS char_critical_blob BYTEA;
ALTER TABLE company_settings ADD COLUMN IF NOT EXISTS char_critical_mime VARCHAR(128);

ALTER TABLE company_settings ADD COLUMN IF NOT EXISTS char_safety_path VARCHAR(512);
ALTER TABLE company_settings ADD COLUMN IF NOT EXISTS char_safety_blob BYTEA;
ALTER TABLE company_settings ADD COLUMN IF NOT EXISTS char_safety_mime VARCHAR(128);

ALTER TABLE company_settings ADD COLUMN IF NOT EXISTS char_important_path VARCHAR(512);
ALTER TABLE company_settings ADD COLUMN IF NOT EXISTS char_important_blob BYTEA;
ALTER TABLE company_settings ADD COLUMN IF NOT EXISTS char_important_mime VARCHAR(128);
