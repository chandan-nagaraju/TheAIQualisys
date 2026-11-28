-- One-time: already-verified payments that stored a window on billing_payments
-- but never wrote companies.subscription_start/end (Sri Balaji 12-Sep card).
-- Does not use payment_submitted_at.

UPDATE billing_payments
SET
  subscription_start_date = (verified_at AT TIME ZONE 'UTC')::date,
  subscription_end_date = ((verified_at AT TIME ZONE 'UTC')::date + (
    CASE billing_period
      WHEN 'QUARTERLY' THEN 90
      WHEN 'HALF_YEARLY' THEN 180
      WHEN 'YEARLY' THEN 365
      ELSE 30
    END
  ))
WHERE status = 'verified'
  AND verified_at IS NOT NULL
  AND subscription_start_date IS NULL
  AND subscription_end_date IS NULL;

UPDATE companies c
SET
  subscription_start = p.subscription_start_date,
  subscription_end = p.subscription_end_date,
  subscription_status = 'active'
FROM (
  SELECT DISTINCT ON (company_id)
    company_id,
    subscription_start_date,
    subscription_end_date
  FROM billing_payments
  WHERE status = 'verified'
    AND subscription_start_date IS NOT NULL
    AND subscription_end_date IS NOT NULL
  ORDER BY company_id, verified_at DESC NULLS LAST, id DESC
) p
WHERE c.id = p.company_id;
