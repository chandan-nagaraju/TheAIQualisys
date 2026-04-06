-- Allow platform admins to block/unblock tenant login accounts.
ALTER TABLE company_users
ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
