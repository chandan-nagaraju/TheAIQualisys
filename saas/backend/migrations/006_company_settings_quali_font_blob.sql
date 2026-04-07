-- Optional per-company FIR font (TrueType); embedded in FIR preview when set.
ALTER TABLE company_settings ADD COLUMN IF NOT EXISTS quali_font_blob BYTEA;
ALTER TABLE company_settings ADD COLUMN IF NOT EXISTS quali_font_mime VARCHAR(128);
