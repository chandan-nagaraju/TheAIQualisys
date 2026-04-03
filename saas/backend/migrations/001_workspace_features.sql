-- Run against existing PostgreSQL DBs when SQLAlchemy create_all does not alter existing tables.
-- Adjust schema name if you use a non-default search_path.

ALTER TABLE parts_v2 ADD COLUMN IF NOT EXISTS drawing_pdf_filename VARCHAR(512);
ALTER TABLE parts_v2 ADD COLUMN IF NOT EXISTS drawing_pdf_mime VARCHAR(128);
ALTER TABLE parts_v2 ADD COLUMN IF NOT EXISTS drawing_updated_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS part_revision_history (
    id SERIAL PRIMARY KEY,
    part_id INTEGER NOT NULL REFERENCES parts_v2(id) ON DELETE CASCADE,
    previous_rev VARCHAR(128),
    new_rev VARCHAR(128),
    reason TEXT NOT NULL,
    changed_by_user_id INTEGER REFERENCES company_users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_part_revision_history_part_id ON part_revision_history(part_id);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES company_users(id) ON DELETE CASCADE,
    token_hash VARCHAR(128) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_password_reset_tokens_user_id ON password_reset_tokens(user_id);
