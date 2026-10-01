-- Phase 7A: desktop software trials (one trial ever per user + product).
-- Prerequisite: 032–036. Does not modify prior migration files.
-- Do NOT run against production from this agent; report as deploy-time step.
-- No backfill. No deletes. Paid uniqueness (035) unchanged.

-- Authoritative concurrency / eligibility boundary (B1):
-- once any trial row exists for (licensed_user_id, product_id), another cannot be inserted
-- regardless of status (expired / revoked / suspended / deactivated).
CREATE UNIQUE INDEX IF NOT EXISTS uq_desktop_licenses_one_trial_per_user_product
  ON desktop_licenses (licensed_user_id, product_id)
  WHERE entitlement_type = 'trial';

-- License-scoped trial email delivery (do NOT reuse order-scoped desktop_license_email_deliveries).
CREATE TABLE IF NOT EXISTS desktop_trial_email_deliveries (
    id SERIAL PRIMARY KEY,
    license_id INTEGER NOT NULL UNIQUE REFERENCES desktop_licenses(id) ON DELETE CASCADE,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES company_users(id) ON DELETE CASCADE,
    to_email VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_attempted_at TIMESTAMPTZ NULL,
    sent_at TIMESTAMPTZ NULL,
    last_error TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_desktop_trial_email_deliveries_status
  ON desktop_trial_email_deliveries (status);

CREATE INDEX IF NOT EXISTS ix_desktop_trial_email_deliveries_user
  ON desktop_trial_email_deliveries (user_id);

COMMENT ON TABLE desktop_trial_email_deliveries IS
  'One trial-email delivery record per trial license. Email failure must not roll back the minted trial.';

COMMENT ON INDEX uq_desktop_licenses_one_trial_per_user_product IS
  'Phase 7A: at most one trial entitlement per (licensed_user_id, product_id).';
