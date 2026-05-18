-- Tracks which subscription_end date we already sent the expiry reminder for (idempotent daily cron).
ALTER TABLE companies
    ADD COLUMN IF NOT EXISTS subscription_expiry_reminder_sent_for_end DATE NULL;
