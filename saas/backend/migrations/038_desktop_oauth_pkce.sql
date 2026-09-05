-- Phase 9C-B: Desktop OAuth 2.0 Authorization Code + PKCE foundation.
-- Additive only. No production client seed. No licensing/paid data changes.
-- Do NOT apply against production from this agent; report as deploy-time step.

DO $$
BEGIN
  IF to_regclass('public.companies') IS NULL THEN
    RAISE EXCEPTION '038 preflight failed: companies table missing';
  END IF;
  IF to_regclass('public.company_users') IS NULL THEN
    RAISE EXCEPTION '038 preflight failed: company_users table missing';
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS oauth_desktop_clients (
    id SERIAL PRIMARY KEY,
    client_id VARCHAR(64) NOT NULL,
    client_name VARCHAR(255) NOT NULL,
    client_type VARCHAR(32) NOT NULL DEFAULT 'public',
    redirect_uris JSONB NOT NULL DEFAULT '[]'::jsonb,
    allowed_scopes JSONB NOT NULL DEFAULT '["desktop_license"]'::jsonb,
    enabled INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_oauth_desktop_clients_type_public CHECK (client_type = 'public'),
    CONSTRAINT ck_oauth_desktop_clients_enabled CHECK (enabled IN (0, 1))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_oauth_desktop_clients_client_id
    ON oauth_desktop_clients (client_id);

COMMENT ON TABLE oauth_desktop_clients IS
  'Registered native desktop OAuth public clients (no client secret). Staging-only registration; do not seed production here.';

CREATE TABLE IF NOT EXISTS oauth_authorization_codes (
    id SERIAL PRIMARY KEY,
    code_hash VARCHAR(128) NOT NULL,
    user_id INTEGER NOT NULL REFERENCES company_users(id) ON DELETE CASCADE,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    client_id VARCHAR(64) NOT NULL REFERENCES oauth_desktop_clients(client_id) ON DELETE CASCADE,
    redirect_uri TEXT NOT NULL,
    scope VARCHAR(255) NOT NULL,
    code_challenge VARCHAR(128) NOT NULL,
    code_challenge_method VARCHAR(16) NOT NULL DEFAULT 'S256',
    state VARCHAR(255) NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_oauth_authorization_codes_method CHECK (code_challenge_method = 'S256')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_oauth_authorization_codes_hash
    ON oauth_authorization_codes (code_hash);

CREATE INDEX IF NOT EXISTS ix_oauth_authorization_codes_client_exp
    ON oauth_authorization_codes (client_id, expires_at);

COMMENT ON TABLE oauth_authorization_codes IS
  'Single-use OAuth authorization codes. Only SHA-256 hashes are stored; plaintext codes are never persisted.';

CREATE TABLE IF NOT EXISTS oauth_refresh_sessions (
    id SERIAL PRIMARY KEY,
    family_id UUID NOT NULL,
    user_id INTEGER NOT NULL REFERENCES company_users(id) ON DELETE CASCADE,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    client_id VARCHAR(64) NOT NULL REFERENCES oauth_desktop_clients(client_id) ON DELETE CASCADE,
    scope VARCHAR(255) NOT NULL,
    token_hash VARCHAR(128) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ NULL,
    revoke_reason VARCHAR(64) NULL,
    replaced_by_id INTEGER NULL REFERENCES oauth_refresh_sessions(id) ON DELETE SET NULL,
    last_used_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_oauth_refresh_sessions_token_hash
    ON oauth_refresh_sessions (token_hash);

CREATE INDEX IF NOT EXISTS ix_oauth_refresh_sessions_family
    ON oauth_refresh_sessions (family_id);

CREATE INDEX IF NOT EXISTS ix_oauth_refresh_sessions_user
    ON oauth_refresh_sessions (user_id);

CREATE INDEX IF NOT EXISTS ix_oauth_refresh_sessions_client_user
    ON oauth_refresh_sessions (client_id, user_id);

COMMENT ON TABLE oauth_refresh_sessions IS
  'Rotating desktop OAuth refresh tokens (hashed). Replay of a rotated token revokes the entire family.';

CREATE TABLE IF NOT EXISTS oauth_desktop_audit_events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(64) NOT NULL,
    success INTEGER NOT NULL DEFAULT 1,
    user_id INTEGER NULL,
    company_id INTEGER NULL,
    client_id VARCHAR(64) NULL,
    error_code VARCHAR(64) NULL,
    meta JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_oauth_desktop_audit_success CHECK (success IN (0, 1))
);

CREATE INDEX IF NOT EXISTS ix_oauth_desktop_audit_events_type_created
    ON oauth_desktop_audit_events (event_type, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_oauth_desktop_audit_events_user
    ON oauth_desktop_audit_events (user_id);

COMMENT ON TABLE oauth_desktop_audit_events IS
  'Desktop OAuth security audit trail. Must never store access tokens, refresh tokens, auth codes, or PKCE verifiers.';
