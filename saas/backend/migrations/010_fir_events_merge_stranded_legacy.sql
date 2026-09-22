-- Recover FIR intelligence rows left in fir_report_events when SQLAlchemy create_all
-- created an empty `fir_events` table BEFORE migration 009 could rename the legacy table.
-- Safe to re-run: only runs when fir_report_events exists.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $merge$
BEGIN
  IF to_regclass('public.fir_report_events') IS NULL THEN
    RAISE NOTICE '010_fir_events_merge: no fir_report_events table; skip';
    RETURN;
  END IF;

  INSERT INTO fir_events (
    company_id,
    customer_id,
    part_no,
    invoice_no,
    event_uid,
    invoice_date,
    quantity,
    source_file,
    uploaded_at,
    created_at
  )
  SELECT
    fr.company_id,
    fr.customer_id,
    fr.part_no,
    fr.invoice_no,
    encode(
      digest(
        fr.company_id::text || '|'
          || COALESCE(NULLIF(BTRIM(fr.invoice_no), ''), '') || '|'
          || (fr.created_at AT TIME ZONE 'UTC')::date::text || '|'
          || upper(BTRIM(fr.part_no)) || '|'
          || '0',
        'sha256'
      ),
      'hex'
    ),
    (fr.created_at AT TIME ZONE 'UTC')::date,
    '0',
    NULL,
    NULL,
    fr.created_at
  FROM fir_report_events fr
  ON CONFLICT (event_uid) DO NOTHING;

  DROP TABLE fir_report_events;
  RAISE NOTICE '010_fir_events_merge: merged legacy fir_report_events into fir_events and dropped legacy table';
END $merge$;
