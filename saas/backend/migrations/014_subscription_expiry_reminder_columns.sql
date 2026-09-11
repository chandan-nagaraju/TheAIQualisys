-- Per-local-day reminder slots (morning/evening on last day; morning only after expiry).
ALTER TABLE public.companies
    ADD COLUMN IF NOT EXISTS subscription_expiry_reminder_date DATE NULL;

ALTER TABLE public.companies
    ADD COLUMN IF NOT EXISTS subscription_expiry_reminder_mask INTEGER NOT NULL DEFAULT 0;
