-- Phase 1 corrective: enforce at most ONE active activation per license.
-- Status model (desktop_activations.status): 'active' | 'deactivated'
-- Historical/deactivated rows are preserved; only one row may be status='active'.
--
-- SAFETY: Does NOT delete data. If conflicting active rows already exist, this
-- migration FAILS with an explicit list of license_id values. Resolve manually
-- (deactivate extras / admin device reset) before re-running in production.
--
-- Prerequisite: 032_desktop_licensing.sql applied (desktop_activations exists).

DO $$
DECLARE
  conflict_count INTEGER;
  conflict_ids TEXT;
BEGIN
  IF to_regclass('public.desktop_activations') IS NULL THEN
    RAISE EXCEPTION
      '033_desktop_licensing_one_active_device: table desktop_activations missing — apply 032 first';
  END IF;

  SELECT COUNT(*)::INTEGER, COALESCE_agg(license_id::TEXT ORDER BY license_id)
  INTO conflict_count, conflict_ids
  FROM (
    SELECT license_id
    FROM desktop_activations
    WHERE status = 'active'
    GROUP BY license_id
    HAVING COUNT(*) > 1
  ) dupes;

  IF conflict_count > 0 THEN
    RAISE EXCEPTION
      '033_desktop_licensing_one_active_device: cannot create unique active-device index — % license(s) have multiple active activations. license_id list: %. Deactivate extras manually (set status=deactivated, clear licenses.bound_device_id as needed), then re-run migration. No rows were deleted.',
      conflict_count,
      conflict_ids;
  END IF;
END $$;

-- One license → at most one active activation (hence one active device).
CREATE UNIQUE INDEX IF NOT EXISTS uq_desktop_activations_one_active_per_license
  ON desktop_activations (license_id)
  WHERE status = 'active';
