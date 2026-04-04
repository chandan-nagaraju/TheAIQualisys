-- Store Settings images in DB so they are available across machines/instances.
ALTER TABLE company_settings ADD COLUMN IF NOT EXISTS logo_blob BYTEA;
ALTER TABLE company_settings ADD COLUMN IF NOT EXISTS logo_mime VARCHAR(128);
ALTER TABLE company_settings ADD COLUMN IF NOT EXISTS inspector_signature_blob BYTEA;
ALTER TABLE company_settings ADD COLUMN IF NOT EXISTS inspector_signature_mime VARCHAR(128);
ALTER TABLE company_settings ADD COLUMN IF NOT EXISTS quality_signature_blob BYTEA;
ALTER TABLE company_settings ADD COLUMN IF NOT EXISTS quality_signature_mime VARCHAR(128);
