-- FIR Intelligence: fir_events schema, business-key event_uid backfill, historical deduplication, unique constraint.
--
-- SAFETY: Take a full database backup first. Test on staging. Intended to run as one transaction (BEGIN/COMMIT below).
-- Requires: pgcrypto (digest). Large tables: single UPDATE still runs in one TX; adjust batching only if you split the TX.
--
-- Business key (before SHA-256): company_id|invoice_number|invoice_date|part_number|quantity
-- Normalization matches app.fir_intelligence_ingest (trim, part uppercase, date ISO, quantity stripped of .0 etc.)

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- 0) Helpers: quantity normalization for UID (mirrors Python Decimal logic)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION migration_fir_normalize_qty_for_uid(p_qty text)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
  s text;
  v numeric;
  t text;
BEGIN
  IF p_qty IS NULL THEN
    RETURN '0';
  END IF;
  s := replace(replace(replace(btrim(p_qty), E'\u2009', ''), E'\u00a0', ''), ',', '');
  IF s = '' THEN
    RETURN '0';
  END IF;
  BEGIN
    v := s::numeric;
  EXCEPTION
    WHEN invalid_text_representation THEN
      s := substring(s from '^([-+]?\d+(?:\.\d+)?)');
      IF s IS NULL OR s = '' THEN
        RETURN '0';
      END IF;
      BEGIN
        v := s::numeric;
      EXCEPTION
        WHEN invalid_text_representation THEN
          RETURN '0';
      END;
  END;
  IF v = trunc(v, 0) THEN
    RETURN trunc(v, 0)::bigint::text;
  END IF;
  t := v::text;
  t := rtrim(rtrim(t, '0'), '.');
  IF t IS NULL OR t = '' OR t = '-' THEN
    RETURN '0';
  END IF;
  RETURN t;
END;
$$;

-- ---------------------------------------------------------------------------
-- 1) Rename legacy table → fir_events
-- ---------------------------------------------------------------------------
DO $rename$
BEGIN
  IF to_regclass('public.fir_report_events') IS NOT NULL AND to_regclass('public.fir_events') IS NULL THEN
    ALTER TABLE fir_report_events RENAME TO fir_events;
  END IF;
END $rename$;

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

-- ---------------------------------------------------------------------------
-- 2) Nullable analytics columns (Step 1 in product spec)
-- ---------------------------------------------------------------------------
ALTER TABLE fir_events ADD COLUMN IF NOT EXISTS event_uid TEXT;
ALTER TABLE fir_events ADD COLUMN IF NOT EXISTS invoice_date DATE;
ALTER TABLE fir_events ADD COLUMN IF NOT EXISTS quantity VARCHAR(64);
ALTER TABLE fir_events ADD COLUMN IF NOT EXISTS source_file VARCHAR(512);
ALTER TABLE fir_events ADD COLUMN IF NOT EXISTS uploaded_at TIMESTAMPTZ;

-- Base fields for every row before hashing
UPDATE fir_events
SET invoice_date = COALESCE(
    invoice_date,
    (created_at AT TIME ZONE 'UTC')::date
)
WHERE invoice_date IS NULL;

UPDATE fir_events
SET quantity = COALESCE(NULLIF(BTRIM(quantity), ''), '0')
WHERE quantity IS NULL OR BTRIM(COALESCE(quantity, '')) = '';

-- ---------------------------------------------------------------------------
-- 3) Backfill event_uid for ALL rows (canonical business key → SHA-256 hex)
-- ---------------------------------------------------------------------------
-- For very large tables (millions of rows), consider splitting this UPDATE into batches
-- on id ranges inside the same transaction to reduce long single-table locks, e.g.:
--   UPDATE fir_events fe SET event_uid = ... WHERE fe.id BETWEEN $lo AND $hi;
DO $backfill$
DECLARE
  v_scanned bigint;
  v_updated bigint;
BEGIN
  SELECT COUNT(*) INTO v_scanned FROM fir_events;

  UPDATE fir_events AS fe
  SET event_uid = encode(
    digest(
      fe.company_id::text || '|'
        || COALESCE(NULLIF(BTRIM(fe.invoice_no), ''), '') || '|'
        || fe.invoice_date::text || '|'
        || upper(BTRIM(fe.part_no)) || '|'
        || migration_fir_normalize_qty_for_uid(COALESCE(fe.quantity::text, '0')),
      'sha256'
    ),
    'hex'
  );

  GET DIAGNOSTICS v_updated = ROW_COUNT;

  RAISE NOTICE 'fir_events migration summary: total existing rows scanned = %', v_scanned;
  RAISE NOTICE 'fir_events migration summary: event_uids generated (rows updated) = %', v_updated;
END $backfill$;

-- ---------------------------------------------------------------------------
-- 4) Remove historical duplicates (keep oldest: created_at, then id)
-- ---------------------------------------------------------------------------
DO $dedupe$
DECLARE
  v_dup_groups bigint;
  v_deleted bigint;
  v_retained bigint;
  v_total_before bigint;
BEGIN
  SELECT COUNT(*) INTO v_total_before FROM fir_events;

  SELECT COUNT(*) INTO v_dup_groups FROM (
    SELECT event_uid
    FROM fir_events
    GROUP BY event_uid
    HAVING COUNT(*) > 1
  ) d;

  WITH ranked AS (
    SELECT
      id,
      ROW_NUMBER() OVER (
        PARTITION BY event_uid
        ORDER BY created_at ASC NULLS LAST, id ASC
      ) AS rn
    FROM fir_events
  ),
  removed AS (
    DELETE FROM fir_events AS f
    USING ranked AS r
    WHERE f.id = r.id AND r.rn > 1
    RETURNING f.id
  )
  SELECT COUNT(*) INTO v_deleted FROM removed;

  SELECT COUNT(*) INTO v_retained FROM fir_events;

  RAISE NOTICE 'fir_events migration summary: duplicate event_uid groups found = %', v_dup_groups;
  RAISE NOTICE 'fir_events migration summary: duplicate rows deleted = %', v_deleted;
  RAISE NOTICE 'fir_events migration summary: unique rows retained after dedupe = %', v_retained;
  RAISE NOTICE 'fir_events migration summary: rows present before dedupe = %', v_total_before;
END $dedupe$;

-- ---------------------------------------------------------------------------
-- 5) Verify: no duplicate event_uid
-- ---------------------------------------------------------------------------
DO $verify$
DECLARE
  v_bad bigint;
BEGIN
  SELECT COUNT(*) INTO v_bad FROM (
    SELECT 1 FROM fir_events GROUP BY event_uid HAVING COUNT(*) > 1
  ) x;
  IF COALESCE(v_bad, 0) > 0 THEN
    RAISE EXCEPTION 'fir_events migration failed: % duplicate event_uid groups remain after cleanup', v_bad;
  END IF;
  RAISE NOTICE 'fir_events migration: verification OK (no duplicate event_uids)';
END $verify$;

-- ---------------------------------------------------------------------------
-- 6) Enforce NOT NULL + UNIQUE (Step 5 in product spec)
-- ---------------------------------------------------------------------------
ALTER TABLE fir_events ALTER COLUMN event_uid SET NOT NULL;
ALTER TABLE fir_events ALTER COLUMN invoice_date SET NOT NULL;
ALTER TABLE fir_events ALTER COLUMN quantity SET NOT NULL;

ALTER TABLE fir_events DROP CONSTRAINT IF EXISTS fir_events_event_uid_unique;
ALTER TABLE fir_events ADD CONSTRAINT fir_events_event_uid_unique UNIQUE (event_uid);

CREATE INDEX IF NOT EXISTS ix_fir_events_invoice_date ON fir_events(invoice_date);

DROP FUNCTION IF EXISTS migration_fir_normalize_qty_for_uid(text);

-- ---------------------------------------------------------------------------
-- 7) Upload audit log table
-- ---------------------------------------------------------------------------
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

DO $final$
DECLARE
  n bigint;
BEGIN
  SELECT COUNT(*) INTO n FROM fir_events;
  RAISE NOTICE 'fir_events migration summary: FINAL unique rows in fir_events = % (constraints applied)', n;
END $final$;

COMMIT;

-- Post-migration manual check (run outside transaction if desired):
-- SELECT event_uid, COUNT(*) FROM fir_events GROUP BY event_uid HAVING COUNT(*) > 1;
