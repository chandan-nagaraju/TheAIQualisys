-- Scope parts by FIR customer (vendor). Requires at least one fir_customers row per company that has parts.

ALTER TABLE parts_v2 ADD COLUMN IF NOT EXISTS customer_id INTEGER REFERENCES fir_customers(id) ON DELETE RESTRICT;

UPDATE parts_v2 p
SET customer_id = c.id
FROM (
  SELECT company_id, MIN(id) AS id
  FROM fir_customers
  GROUP BY company_id
  HAVING COUNT(*) = 1
) AS sub
JOIN fir_customers c ON c.company_id = sub.company_id AND c.id = sub.id
WHERE p.company_id = sub.company_id AND (p.customer_id IS NULL);

UPDATE parts_v2 p
SET customer_id = (
  SELECT fc.id FROM fir_customers fc WHERE fc.company_id = p.company_id ORDER BY fc.id LIMIT 1
)
WHERE p.customer_id IS NULL
  AND EXISTS (SELECT 1 FROM fir_customers fc WHERE fc.company_id = p.company_id);

ALTER TABLE parts_v2 ALTER COLUMN customer_id SET NOT NULL;

ALTER TABLE parts_v2 DROP CONSTRAINT IF EXISTS uq_parts_v2_company_part;

ALTER TABLE parts_v2 ADD CONSTRAINT uq_parts_v2_company_customer_part UNIQUE (company_id, customer_id, part_no);

CREATE INDEX IF NOT EXISTS ix_parts_v2_customer_id ON parts_v2(customer_id);
