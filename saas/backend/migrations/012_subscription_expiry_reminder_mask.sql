-- Bitmask: bit0 = 9:00 slot sent, bit1 = 17:00 slot (subscription reminder on last day).
ALTER TABLE companies
    ADD COLUMN IF NOT EXISTS subscription_expiry_reminder_mask INTEGER NOT NULL DEFAULT 0;

-- Upgrade from single-send behaviour: treat "fully done" for current period so we do not resend immediately.
UPDATE companies
SET subscription_expiry_reminder_mask = 3
WHERE subscription_expiry_reminder_sent_for_end IS NOT NULL
  AND subscription_end IS NOT NULL
  AND subscription_expiry_reminder_sent_for_end = subscription_end;
