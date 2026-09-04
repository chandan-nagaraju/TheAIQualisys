-- Object-key path for custom Quali font when stored in S3 (see CompanySettings.quali_font_path).
ALTER TABLE company_settings ADD COLUMN IF NOT EXISTS quali_font_path VARCHAR(512);
