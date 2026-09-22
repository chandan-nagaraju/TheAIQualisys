-- Tenant-facing QMS module cards: when false, dashboard shows "stay tuned" (no trial/pricing teaser).
ALTER TABLE module_pricing
ADD COLUMN IF NOT EXISTS listing_active BOOLEAN NOT NULL DEFAULT false;
