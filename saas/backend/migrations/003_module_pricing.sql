-- Configurable module & FIR plan pricing (admin-editable).
CREATE TABLE IF NOT EXISTS module_pricing (
    id SERIAL PRIMARY KEY,
    module_name VARCHAR(64) NOT NULL UNIQUE,
    display_name VARCHAR(255) NOT NULL,
    monthly_price INTEGER NOT NULL DEFAULT 0,
    yearly_price INTEGER,
    trial_days INTEGER NOT NULL DEFAULT 14,
    usage_limit INTEGER NOT NULL DEFAULT 5,
    fir_plan_type VARCHAR(32),
    invoice_min INTEGER,
    invoice_max INTEGER,
    highlight VARCHAR(255),
    sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_module_pricing_fir_plan_type ON module_pricing(fir_plan_type);

INSERT INTO module_pricing (module_name, display_name, monthly_price, yearly_price, trial_days, usage_limit, fir_plan_type, invoice_min, invoice_max, highlight, sort_order)
VALUES
    ('fir_basic', 'Basic', 2799, NULL, 7, 0, 'basic', 0, 1000, NULL, 1),
    ('fir_pro', 'Pro', 4599, NULL, 7, 0, 'pro', 1001, 2000, NULL, 2),
    ('fir_enterprise', 'Enterprise', 6599, NULL, 7, 0, 'enterprise', 2001, NULL, 'Best for growing companies', 3),
    ('drawings_directory', 'Drawings Directory', 1999, NULL, 14, 5, NULL, NULL, NULL, NULL, 10),
    ('rc2a', 'RC2A', 2499, NULL, 14, 5, NULL, NULL, NULL, NULL, 11),
    ('ppap', 'PPAP', 3499, NULL, 14, 5, NULL, NULL, NULL, NULL, 12),
    ('iatf_documentation', 'IATF Documentation', 4999, NULL, 14, 5, NULL, NULL, NULL, NULL, 13)
ON CONFLICT (module_name) DO NOTHING;
