-- Track last update of customer-complaint rows so FIR can drop them after 90 days.
ALTER TABLE part_complaints_v2
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE INDEX IF NOT EXISTS ix_part_complaints_v2_updated_at ON part_complaints_v2 (updated_at);
