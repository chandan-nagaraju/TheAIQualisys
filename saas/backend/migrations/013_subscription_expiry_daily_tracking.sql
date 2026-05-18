ALTER TABLE public.companies
ADD COLUMN IF NOT EXISTS subscription_expiry_reminder_date DATE;

ALTER TABLE public.companies
DROP COLUMN IF EXISTS subscription_expiry_reminder_sent_for_end;
