-- Payable UPI amount includes paise after 18% GST (e.g. 6799 * 1.18 = 8022.82).
ALTER TABLE billing_payments
  ALTER COLUMN amount_inr TYPE NUMERIC(14, 2) USING amount_inr::numeric;
