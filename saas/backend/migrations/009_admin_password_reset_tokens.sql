CREATE TABLE IF NOT EXISTS admin_password_reset_tokens (
    id SERIAL PRIMARY KEY,
    admin_id INTEGER NOT NULL REFERENCES platform_admins (id) ON DELETE CASCADE,
    token_hash VARCHAR(128) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_admin_password_reset_tokens_admin_id ON admin_password_reset_tokens (admin_id);
