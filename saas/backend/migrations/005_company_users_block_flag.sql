-- Add admin-controllable block flag for tenant login users.
ALTER TABLE company_users
ADD COLUMN IF NOT EXISTS is_blocked INTEGER NOT NULL DEFAULT 0;
