-- Phase 4: desktop UPI settings + license seat uniqueness for mint idempotency.
-- Prerequisite: 032–034. Does not modify prior migration files.
-- Do NOT run against production from this agent; report as deploy-time step.

CREATE TABLE IF NOT EXISTS desktop_upi_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    upi_id VARCHAR(255) NOT NULL DEFAULT '',
    payee_name VARCHAR(255) NOT NULL DEFAULT '',
    instructions TEXT NULL,
    qr_image_path VARCHAR(1024) NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by_admin_id INTEGER NULL REFERENCES platform_admins(id) ON DELETE SET NULL
);

INSERT INTO desktop_upi_settings (id, upi_id, payee_name, instructions)
VALUES (
  1,
  '',
  '',
  'Pay the order total via UPI, then submit your UTR / UPI reference on the website. An admin will verify before license keys are issued.'
)
ON CONFLICT (id) DO NOTHING;

-- One paid seat index per order (prevents double-mint of the same seat).
CREATE UNIQUE INDEX IF NOT EXISTS uq_desktop_licenses_order_seat
  ON desktop_licenses (order_id, seat_index)
  WHERE order_id IS NOT NULL AND seat_index IS NOT NULL;

-- At most one currently open payment review per order (pending_review).
CREATE UNIQUE INDEX IF NOT EXISTS uq_desktop_payments_one_pending_review_per_order
  ON desktop_payments (order_id)
  WHERE status = 'pending_review';

CREATE INDEX IF NOT EXISTS ix_desktop_payments_status
  ON desktop_payments (status);
