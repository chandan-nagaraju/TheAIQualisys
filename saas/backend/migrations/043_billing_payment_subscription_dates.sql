-- Persist the paid window on the payment at Admin verification time.
-- verified_at is payment_verified_at. Do not overwrite payment_submitted_at.

ALTER TABLE billing_payments ADD COLUMN IF NOT EXISTS subscription_start_date DATE;
ALTER TABLE billing_payments ADD COLUMN IF NOT EXISTS subscription_end_date DATE;
