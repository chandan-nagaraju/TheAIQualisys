-- TheAIQualisys Cadence™: Pulse / Season / Horizon / Orbit (1 seat each).
-- Renames legacy ANNUAL_1SEAT → {PREFIX}_ORBIT_1SEAT and adds 30/90/180 day plans.

UPDATE desktop_products
SET description = 'Choose your cadence: Pulse → Season → Horizon → Orbit'
WHERE code IN ('QR_CODE', 'ASN_PDF_PRINTER', 'ASN_AUTO_FILLER');

-- QR: Annual → Orbit
UPDATE desktop_plans pl
SET code = 'QR_ORBIT_1SEAT'
FROM desktop_products p
WHERE pl.product_id = p.id
  AND p.code = 'QR_CODE'
  AND pl.code = 'ANNUAL_1SEAT'
  AND NOT EXISTS (
    SELECT 1 FROM desktop_plans x WHERE x.product_id = p.id AND x.code = 'QR_ORBIT_1SEAT'
  );

UPDATE desktop_plans pl
SET
  name = 'Orbit · 1 seat',
  description = 'Full year around your workflow',
  duration_days = 365,
  seats = 1,
  sort_order = 40,
  price_inr = CASE WHEN pl.price_inr IS NULL OR pl.price_inr <= 0 THEN 4999 ELSE pl.price_inr END
FROM desktop_products p
WHERE pl.product_id = p.id
  AND p.code = 'QR_CODE'
  AND pl.code = 'QR_ORBIT_1SEAT';

INSERT INTO desktop_plans (product_id, code, name, description, price_inr, duration_days, seats, listing_active, sort_order)
SELECT p.id, 'QR_ORBIT_1SEAT', 'Orbit · 1 seat', 'Full year around your workflow', 4999, 365, 1, 1, 40
FROM desktop_products p
WHERE p.code = 'QR_CODE'
ON CONFLICT (product_id, code) DO NOTHING;

INSERT INTO desktop_plans (product_id, code, name, description, price_inr, duration_days, seats, listing_active, sort_order)
SELECT p.id, 'QR_PULSE_1SEAT', 'Pulse · 1 seat', 'Month by month — stay in sync', 499, 30, 1, 1, 10
FROM desktop_products p
WHERE p.code = 'QR_CODE'
ON CONFLICT (product_id, code) DO NOTHING;

INSERT INTO desktop_plans (product_id, code, name, description, price_inr, duration_days, seats, listing_active, sort_order)
SELECT p.id, 'QR_SEASON_1SEAT', 'Season · 1 seat', 'One quarter of uninterrupted use', 1299, 90, 1, 1, 20
FROM desktop_products p
WHERE p.code = 'QR_CODE'
ON CONFLICT (product_id, code) DO NOTHING;

INSERT INTO desktop_plans (product_id, code, name, description, price_inr, duration_days, seats, listing_active, sort_order)
SELECT p.id, 'QR_HORIZON_1SEAT', 'Horizon · 1 seat', 'Six months locked to your machine', 2499, 180, 1, 1, 30
FROM desktop_products p
WHERE p.code = 'QR_CODE'
ON CONFLICT (product_id, code) DO NOTHING;

-- ASN PDF Printer
UPDATE desktop_plans pl
SET code = 'ASN_PDF_ORBIT_1SEAT'
FROM desktop_products p
WHERE pl.product_id = p.id
  AND p.code = 'ASN_PDF_PRINTER'
  AND pl.code = 'ANNUAL_1SEAT'
  AND NOT EXISTS (
    SELECT 1 FROM desktop_plans x WHERE x.product_id = p.id AND x.code = 'ASN_PDF_ORBIT_1SEAT'
  );

UPDATE desktop_plans pl
SET
  name = 'Orbit · 1 seat',
  description = 'Full year around your workflow',
  duration_days = 365,
  seats = 1,
  sort_order = 40,
  price_inr = CASE WHEN pl.price_inr IS NULL OR pl.price_inr <= 0 THEN 4999 ELSE pl.price_inr END
FROM desktop_products p
WHERE pl.product_id = p.id
  AND p.code = 'ASN_PDF_PRINTER'
  AND pl.code = 'ASN_PDF_ORBIT_1SEAT';

INSERT INTO desktop_plans (product_id, code, name, description, price_inr, duration_days, seats, listing_active, sort_order)
SELECT p.id, 'ASN_PDF_ORBIT_1SEAT', 'Orbit · 1 seat', 'Full year around your workflow', 4999, 365, 1, 1, 40
FROM desktop_products p
WHERE p.code = 'ASN_PDF_PRINTER'
ON CONFLICT (product_id, code) DO NOTHING;

INSERT INTO desktop_plans (product_id, code, name, description, price_inr, duration_days, seats, listing_active, sort_order)
SELECT p.id, 'ASN_PDF_PULSE_1SEAT', 'Pulse · 1 seat', 'Month by month — stay in sync', 499, 30, 1, 1, 10
FROM desktop_products p
WHERE p.code = 'ASN_PDF_PRINTER'
ON CONFLICT (product_id, code) DO NOTHING;

INSERT INTO desktop_plans (product_id, code, name, description, price_inr, duration_days, seats, listing_active, sort_order)
SELECT p.id, 'ASN_PDF_SEASON_1SEAT', 'Season · 1 seat', 'One quarter of uninterrupted use', 1299, 90, 1, 1, 20
FROM desktop_products p
WHERE p.code = 'ASN_PDF_PRINTER'
ON CONFLICT (product_id, code) DO NOTHING;

INSERT INTO desktop_plans (product_id, code, name, description, price_inr, duration_days, seats, listing_active, sort_order)
SELECT p.id, 'ASN_PDF_HORIZON_1SEAT', 'Horizon · 1 seat', 'Six months locked to your machine', 2499, 180, 1, 1, 30
FROM desktop_products p
WHERE p.code = 'ASN_PDF_PRINTER'
ON CONFLICT (product_id, code) DO NOTHING;

-- ASN Auto Filler
UPDATE desktop_plans pl
SET code = 'ASN_FILL_ORBIT_1SEAT'
FROM desktop_products p
WHERE pl.product_id = p.id
  AND p.code = 'ASN_AUTO_FILLER'
  AND pl.code = 'ANNUAL_1SEAT'
  AND NOT EXISTS (
    SELECT 1 FROM desktop_plans x WHERE x.product_id = p.id AND x.code = 'ASN_FILL_ORBIT_1SEAT'
  );

UPDATE desktop_plans pl
SET
  name = 'Orbit · 1 seat',
  description = 'Full year around your workflow',
  duration_days = 365,
  seats = 1,
  sort_order = 40,
  price_inr = CASE WHEN pl.price_inr IS NULL OR pl.price_inr <= 0 THEN 4999 ELSE pl.price_inr END
FROM desktop_products p
WHERE pl.product_id = p.id
  AND p.code = 'ASN_AUTO_FILLER'
  AND pl.code = 'ASN_FILL_ORBIT_1SEAT';

INSERT INTO desktop_plans (product_id, code, name, description, price_inr, duration_days, seats, listing_active, sort_order)
SELECT p.id, 'ASN_FILL_ORBIT_1SEAT', 'Orbit · 1 seat', 'Full year around your workflow', 4999, 365, 1, 1, 40
FROM desktop_products p
WHERE p.code = 'ASN_AUTO_FILLER'
ON CONFLICT (product_id, code) DO NOTHING;

INSERT INTO desktop_plans (product_id, code, name, description, price_inr, duration_days, seats, listing_active, sort_order)
SELECT p.id, 'ASN_FILL_PULSE_1SEAT', 'Pulse · 1 seat', 'Month by month — stay in sync', 499, 30, 1, 1, 10
FROM desktop_products p
WHERE p.code = 'ASN_AUTO_FILLER'
ON CONFLICT (product_id, code) DO NOTHING;

INSERT INTO desktop_plans (product_id, code, name, description, price_inr, duration_days, seats, listing_active, sort_order)
SELECT p.id, 'ASN_FILL_SEASON_1SEAT', 'Season · 1 seat', 'One quarter of uninterrupted use', 1299, 90, 1, 1, 20
FROM desktop_products p
WHERE p.code = 'ASN_AUTO_FILLER'
ON CONFLICT (product_id, code) DO NOTHING;

INSERT INTO desktop_plans (product_id, code, name, description, price_inr, duration_days, seats, listing_active, sort_order)
SELECT p.id, 'ASN_FILL_HORIZON_1SEAT', 'Horizon · 1 seat', 'Six months locked to your machine', 2499, 180, 1, 1, 30
FROM desktop_products p
WHERE p.code = 'ASN_AUTO_FILLER'
ON CONFLICT (product_id, code) DO NOTHING;
