-- Allow password reset tokens for platform admins (not only company_users).

ALTER TABLE password_reset_tokens ADD COLUMN IF NOT EXISTS platform_admin_id INTEGER REFERENCES platform_admins(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_platform_admin_id ON password_reset_tokens(platform_admin_id);

ALTER TABLE password_reset_tokens ALTER COLUMN user_id DROP NOT NULL;

ALTER TABLE password_reset_tokens DROP CONSTRAINT IF EXISTS password_reset_token_subject_ck;
ALTER TABLE password_reset_tokens ADD CONSTRAINT password_reset_token_subject_ck CHECK (
  (user_id IS NOT NULL AND platform_admin_id IS NULL)
  OR (user_id IS NULL AND platform_admin_id IS NOT NULL)
);
