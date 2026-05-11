-- FIR Intelligence: deduplicated fir_events (renamed from fir_report_events), upload log table.
-- Run against PostgreSQL (Supabase). Safe to re-run: uses IF NOT EXISTS / IF NOT NULL guards where possible.

-- 1) Rename legacy table so ORM __tablename__ matches fir_events
DO $$
BEGIN
  IF to_regclass('public.fir_report_events') IS NOT NULL AND to_regclass('public.fir_events') IS NULL THEN
    ALTER TABLE fir_report_events RENAME TO fir_events;
  END IF;
END $$;

-- 2) New installs may rely on SQLAlchemy create_all; ensure base table exists for older DBs that had no ledger yet.
CREATE TABLE IF NOT EXISTS fir_events (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    customer_id INTEGER REFERENCES fir_customers(id) ON DELETE SET NULL,
    part_no VARCHAR(255) NOT NULL,
    invoice_no VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_fir_events_company_id ON fir_events(company_id);
CREATE INDEX IF NOT EXISTS ix_fir_events_created_at ON fir_events(created_at);

-- 3) Analytics / dedup columns
ALTER TABLE fir_events ADD COLUMN IF NOT EXISTS event_uid VARCHAR(64);
ALTER TABLE fir_events ADD COLUMN IF NOT EXISTS invoice_date DATE;
ALTER TABLE fir_events ADD COLUMN IF NOT EXISTS quantity VARCHAR(64);
ALTER TABLE fir_events ADD COLUMN IF NOT EXISTS source_file VARCHAR(512);
ALTER TABLE fir_events ADD COLUMN IF NOT EXISTS uploaded_at TIMESTAMPTZ;

-- 4) Backfill legacy rows before NOT NULL / UNIQUE
UPDATE fir_events
SET invoice_date = COALESCE(
    invoice_date,
    (created_at AT TIME ZONE 'UTC')::date
)
WHERE invoice_date IS NULL;

UPDATE fir_events
SET quantity = COALESCE(NULLIF(BTRIM(quantity), ''), '0')
WHERE quantity IS NULL OR BTRIM(COALESCE(quantity, '')) = '';

CREATE EXTENSION IF NOT EXISTS pgcrypto;

UPDATE fir_events
SET event_uid = encode(
    digest(
        company_id::text || '|'
        || COALESCE(NULLIF(BTRIM(invoice_no), ''), '') || '|'
        || invoice_date::text || '|'
        || upper(BTRIM(part_no)) || '|'
        || BTRIM(quantity) || '|legacy|'
        || id::text,
        'sha256'
    ),
    'hex'
)
WHERE event_uid IS NULL;

ALTER TABLE fir_events ALTER COLUMN event_uid SET NOT NULL;
ALTER TABLE fir_events ALTER COLUMN invoice_date SET NOT NULL;
ALTER TABLE fir_events ALTER COLUMN quantity SET NOT NULL;

ALTER TABLE fir_events DROP CONSTRAINT IF EXISTS fir_events_event_uid_unique;
ALTER TABLE fir_events ADD CONSTRAINT fir_events_event_uid_unique UNIQUE (event_uid);
CREATE INDEX IF NOT EXISTS ix_fir_events_invoice_date ON fir_events(invoice_date);

CREATE TABLE IF NOT EXISTS fir_upload_logs (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    file_name VARCHAR(512),
    rows_processed INTEGER NOT NULL DEFAULT 0,
    new_rows INTEGER NOT NULL DEFAULT 0,
    duplicate_rows INTEGER NOT NULL DEFAULT 0,
    reports_generated INTEGER NOT NULL DEFAULT 0,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_fir_upload_logs_company_id ON fir_upload_logs(company_id);
