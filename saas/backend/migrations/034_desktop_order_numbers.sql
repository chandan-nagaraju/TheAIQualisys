-- Phase 3: customer desktop orders — order numbers + price/catalog snapshots.
-- Prerequisite: 032_desktop_licensing.sql (desktop_orders exists).
-- Safe for empty or existing rows: adds nullable columns then backfills/constraints.

CREATE TABLE IF NOT EXISTS desktop_order_number_counters (
    year INTEGER PRIMARY KEY,
    last_value INTEGER NOT NULL DEFAULT 0
);

ALTER TABLE desktop_orders
  ADD COLUMN IF NOT EXISTS order_number VARCHAR(32);

ALTER TABLE desktop_orders
  ADD COLUMN IF NOT EXISTS product_code VARCHAR(64);

ALTER TABLE desktop_orders
  ADD COLUMN IF NOT EXISTS product_name VARCHAR(255);

ALTER TABLE desktop_orders
  ADD COLUMN IF NOT EXISTS plan_code VARCHAR(64);

ALTER TABLE desktop_orders
  ADD COLUMN IF NOT EXISTS plan_name VARCHAR(255);

ALTER TABLE desktop_orders
  ADD COLUMN IF NOT EXISTS duration_days INTEGER;

-- Backfill any pre-Phase-3 rows (dev only; production expected empty) so NOT NULL can apply.
UPDATE desktop_orders o
SET
  order_number = COALESCE(
    o.order_number,
    'TAQ-' || TO_CHAR(COALESCE(o.created_at, NOW()), 'YYYY') || '-' || LPAD(o.id::TEXT, 6, '0')
  ),
  product_code = COALESCE(o.product_code, p.code, 'UNKNOWN'),
  product_name = COALESCE(o.product_name, p.name, 'Unknown product'),
  plan_code = COALESCE(o.plan_code, pl.code, 'UNKNOWN'),
  plan_name = COALESCE(o.plan_name, pl.name, 'Unknown plan'),
  duration_days = COALESCE(o.duration_days, pl.duration_days, 365)
FROM desktop_products p, desktop_plans pl
WHERE o.product_id = p.id
  AND o.plan_id = pl.id
  AND (
    o.order_number IS NULL
    OR o.product_code IS NULL
    OR o.product_name IS NULL
    OR o.plan_code IS NULL
    OR o.plan_name IS NULL
    OR o.duration_days IS NULL
  );

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM desktop_orders WHERE order_number IS NULL OR product_code IS NULL OR plan_code IS NULL
  ) THEN
    RAISE EXCEPTION
      '034_desktop_order_numbers: cannot enforce NOT NULL — unresolved null snapshot/order_number rows remain';
  END IF;
END $$;

ALTER TABLE desktop_orders ALTER COLUMN order_number SET NOT NULL;
ALTER TABLE desktop_orders ALTER COLUMN product_code SET NOT NULL;
ALTER TABLE desktop_orders ALTER COLUMN product_name SET NOT NULL;
ALTER TABLE desktop_orders ALTER COLUMN plan_code SET NOT NULL;
ALTER TABLE desktop_orders ALTER COLUMN plan_name SET NOT NULL;
ALTER TABLE desktop_orders ALTER COLUMN duration_days SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_desktop_orders_order_number
  ON desktop_orders (order_number);

CREATE INDEX IF NOT EXISTS ix_desktop_orders_order_number
  ON desktop_orders (order_number);
