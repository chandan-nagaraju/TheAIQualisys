-- Desktop product licensing foundation (additive; separate from FIR/QMS plans).
-- Products: QR_CODE, ASN_PDF_PRINTER, ASN_AUTO_FILLER
-- Rule: 1 license key = 1 website user + 1 physical device + 1 product.
-- Feature flag: ENABLE_DESKTOP_LICENSING (application-level; this schema is safe to apply dark).

CREATE TABLE IF NOT EXISTS desktop_products (
    id SERIAL PRIMARY KEY,
    code VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    description TEXT NULL,
    listing_active INTEGER NOT NULL DEFAULT 1,
    trial_enabled INTEGER NOT NULL DEFAULT 1,
    trial_duration_days INTEGER NOT NULL DEFAULT 7,
    sort_order INTEGER NOT NULL DEFAULT 0,
    buy_url_path VARCHAR(255) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS desktop_plans (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES desktop_products(id) ON DELETE CASCADE,
    code VARCHAR(64) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT NULL,
    price_inr INTEGER NOT NULL,
    duration_days INTEGER NOT NULL DEFAULT 365,
    -- Unit size for catalog display only. Checkout always mints N independent keys
    -- (never shared max_devices). Prefer seats=1 plans; order.seats is the seat count.
    seats INTEGER NOT NULL DEFAULT 1,
    listing_active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (product_id, code)
);

CREATE TABLE IF NOT EXISTS desktop_orders (
    id SERIAL PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES company_users(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES desktop_products(id) ON DELETE RESTRICT,
    plan_id INTEGER NOT NULL REFERENCES desktop_plans(id) ON DELETE RESTRICT,
    seats INTEGER NOT NULL DEFAULT 1 CHECK (seats >= 1),
    unit_price_inr INTEGER NOT NULL,
    total_price_inr INTEGER NOT NULL,
    currency VARCHAR(8) NOT NULL DEFAULT 'INR',
    -- pending_payment | payment_submitted | approved | rejected | cancelled
    status VARCHAR(32) NOT NULL DEFAULT 'pending_payment',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_desktop_orders_user ON desktop_orders(user_id);
CREATE INDEX IF NOT EXISTS ix_desktop_orders_company ON desktop_orders(company_id);
CREATE INDEX IF NOT EXISTS ix_desktop_orders_status ON desktop_orders(status);

CREATE TABLE IF NOT EXISTS desktop_payments (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES desktop_orders(id) ON DELETE CASCADE,
    upi_id VARCHAR(255) NULL,
    amount_inr INTEGER NOT NULL,
    -- Customer UTR / UPI reference (manual payment model; never auto-mark paid)
    reference_note TEXT NULL,
    screenshot_path VARCHAR(1024) NULL,
    screenshot_mime VARCHAR(128) NULL,
    -- submitted | approved | rejected
    status VARCHAR(32) NOT NULL DEFAULT 'submitted',
    reviewed_by_admin_id INTEGER NULL REFERENCES platform_admins(id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ NULL,
    review_note TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_desktop_payments_order ON desktop_payments(order_id);

-- Devices before licenses.bound_device_id FK (created below after both tables exist)
CREATE TABLE IF NOT EXISTS desktop_devices (
    id SERIAL PRIMARY KEY,
    fingerprint_hash VARCHAR(128) NOT NULL,
    fingerprint_raw_hint VARCHAR(64) NULL,
    label VARCHAR(255) NULL,
    os_meta TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NULL,
    UNIQUE (fingerprint_hash)
);

CREATE TABLE IF NOT EXISTS desktop_licenses (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES desktop_products(id) ON DELETE RESTRICT,
    plan_id INTEGER NULL REFERENCES desktop_plans(id) ON DELETE SET NULL,
    order_id INTEGER NULL REFERENCES desktop_orders(id) ON DELETE SET NULL,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    -- Bound website user: key is NEVER usable by another website user
    licensed_user_id INTEGER NOT NULL REFERENCES company_users(id) ON DELETE CASCADE,
    -- paid | trial (trial unique index deferred to Phase 7A migration)
    entitlement_type VARCHAR(16) NOT NULL DEFAULT 'paid',
    -- Display ordinal within an order (Seat 1, Seat 2, …); NULL for trials / admin grants
    seat_index INTEGER NULL,
    key_prefix VARCHAR(64) NOT NULL,
    key_last4 VARCHAR(8) NOT NULL,
    -- SHA-256 hex of normalized plaintext (lookup); plaintext not stored
    key_hash VARCHAR(128) NOT NULL UNIQUE,
    -- Fernet ciphertext for authorized reveal; NULL if encryption secret unset at mint
    key_encrypted TEXT NULL,
    -- issued | active | expired | revoked | suspended
    status VARCHAR(32) NOT NULL DEFAULT 'issued',
    issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NULL,
    activated_at TIMESTAMPTZ NULL,
    -- Exactly one physical device when set; admin reset clears this (no customer reassignment)
    bound_device_id INTEGER NULL,
    created_by_admin_id INTEGER NULL REFERENCES platform_admins(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_desktop_licenses_user ON desktop_licenses(licensed_user_id);
CREATE INDEX IF NOT EXISTS ix_desktop_licenses_company ON desktop_licenses(company_id);
CREATE INDEX IF NOT EXISTS ix_desktop_licenses_product ON desktop_licenses(product_id);
CREATE INDEX IF NOT EXISTS ix_desktop_licenses_status ON desktop_licenses(status);
CREATE INDEX IF NOT EXISTS ix_desktop_licenses_type ON desktop_licenses(entitlement_type);
CREATE INDEX IF NOT EXISTS ix_desktop_licenses_order ON desktop_licenses(order_id);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'fk_desktop_licenses_bound_device'
  ) THEN
    ALTER TABLE desktop_licenses
      ADD CONSTRAINT fk_desktop_licenses_bound_device
      FOREIGN KEY (bound_device_id) REFERENCES desktop_devices(id) ON DELETE SET NULL;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS desktop_activations (
    id SERIAL PRIMARY KEY,
    license_id INTEGER NOT NULL REFERENCES desktop_licenses(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES company_users(id) ON DELETE CASCADE,
    device_id INTEGER NOT NULL REFERENCES desktop_devices(id) ON DELETE CASCADE,
    -- active | deactivated
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    activated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_validated_at TIMESTAMPTZ NULL,
    deactivated_at TIMESTAMPTZ NULL,
    app_version VARCHAR(64) NULL,
    UNIQUE (license_id, device_id)
);
CREATE INDEX IF NOT EXISTS ix_desktop_activations_license ON desktop_activations(license_id);

CREATE TABLE IF NOT EXISTS desktop_license_events (
    id SERIAL PRIMARY KEY,
    license_id INTEGER NULL REFERENCES desktop_licenses(id) ON DELETE SET NULL,
    actor_type VARCHAR(32) NOT NULL,
    actor_id INTEGER NULL,
    event_type VARCHAR(64) NOT NULL,
    meta_json TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_desktop_license_events_license ON desktop_license_events(license_id, created_at DESC);

CREATE TABLE IF NOT EXISTS desktop_installers (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES desktop_products(id) ON DELETE CASCADE,
    version VARCHAR(64) NOT NULL,
    -- current | recommended | mandatory | archived
    release_channel VARCHAR(32) NOT NULL DEFAULT 'current',
    min_supported_version VARCHAR(64) NULL,
    min_windows_version VARCHAR(64) NULL,
    storage_key VARCHAR(1024) NULL,
    -- Internal object URL only — never permanent public installer links (Phase 6 uses tokens)
    storage_url VARCHAR(2048) NULL,
    file_name VARCHAR(255) NULL,
    file_sha256 VARCHAR(128) NULL,
    file_size_bytes BIGINT NULL,
    release_date DATE NULL,
    release_notes TEXT NULL,
    listing_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (product_id, version)
);

CREATE TABLE IF NOT EXISTS desktop_download_tokens (
    id SERIAL PRIMARY KEY,
    token_hash VARCHAR(128) NOT NULL UNIQUE,
    user_id INTEGER NOT NULL REFERENCES company_users(id) ON DELETE CASCADE,
    installer_id INTEGER NOT NULL REFERENCES desktop_installers(id) ON DELETE CASCADE,
    license_id INTEGER NULL REFERENCES desktop_licenses(id) ON DELETE SET NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_desktop_download_tokens_user ON desktop_download_tokens(user_id);

INSERT INTO desktop_products (code, name, description, listing_active, trial_enabled, trial_duration_days, sort_order, buy_url_path)
VALUES
  ('QR_CODE', 'QR Code Software', 'Windows QR label / code generation application', 1, 1, 7, 10, '/software/qr-code'),
  ('ASN_PDF_PRINTER', 'ASN PDF Printer', 'Windows ASN PDF printing application', 1, 1, 7, 20, '/software/asn-pdf-printer'),
  ('ASN_AUTO_FILLER', 'ASN Auto Filler', 'Windows ASN auto-fill application', 1, 1, 7, 30, '/software/asn-auto-filler')
ON CONFLICT (code) DO NOTHING;

-- Seed one annual per-seat plan per product (price placeholders; admin can adjust in Phase 2).
INSERT INTO desktop_plans (product_id, code, name, description, price_inr, duration_days, seats, listing_active, sort_order)
SELECT p.id, 'ANNUAL_1SEAT', 'Annual — 1 seat', 'One year license for one Windows PC (one key = one device)', 4999, 365, 1, 1, 10
FROM desktop_products p
WHERE p.code = 'QR_CODE'
ON CONFLICT (product_id, code) DO NOTHING;

INSERT INTO desktop_plans (product_id, code, name, description, price_inr, duration_days, seats, listing_active, sort_order)
SELECT p.id, 'ANNUAL_1SEAT', 'Annual — 1 seat', 'One year license for one Windows PC (one key = one device)', 4999, 365, 1, 1, 10
FROM desktop_products p
WHERE p.code = 'ASN_PDF_PRINTER'
ON CONFLICT (product_id, code) DO NOTHING;

INSERT INTO desktop_plans (product_id, code, name, description, price_inr, duration_days, seats, listing_active, sort_order)
SELECT p.id, 'ANNUAL_1SEAT', 'Annual — 1 seat', 'One year license for one Windows PC (one key = one device)', 4999, 365, 1, 1, 10
FROM desktop_products p
WHERE p.code = 'ASN_AUTO_FILLER'
ON CONFLICT (product_id, code) DO NOTHING;
