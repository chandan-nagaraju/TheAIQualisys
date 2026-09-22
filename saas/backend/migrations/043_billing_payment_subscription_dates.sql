-- Persist subscription window on the payment at Admin verification time.
-- payment_submitted_at is unchanged; verified_at is the subscription start clock.

ALTER TABLE billing_payments ADD COLUMN IF NOT EXISTS subscription_start DATE;
ALTER TABLE billing_payments ADD COLUMN IF NOT EXISTS subscription_end DATE;
