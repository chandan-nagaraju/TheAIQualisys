-- Per-local-day reminder tracking; drop legacy column tied to subscription_end only.
ALTER TABLE companies
    ADD COLUMN IF NOT EXISTS subscription_expiry_reminder_date DATE NULL;

ALTER TABLE companies
    DROP COLUMN IF EXISTS subscription_expiry_reminder_sent_for_end;
