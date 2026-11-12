-- Pending company signups: email must be verified before password and tenant creation.
CREATE TABLE IF NOT EXISTS public.pending_signups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_name TEXT NOT NULL,
    email TEXT NOT NULL,
    vendor_code TEXT NOT NULL,
    verification_token TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    verified_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pending_signups_email_unique UNIQUE (email),
    CONSTRAINT pending_signups_vendor_code_unique UNIQUE (vendor_code),
    CONSTRAINT pending_signups_verification_token_unique UNIQUE (verification_token)
);
