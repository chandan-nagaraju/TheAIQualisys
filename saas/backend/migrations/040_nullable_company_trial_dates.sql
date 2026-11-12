-- Allow admin "Mark expired" to clear trial dates (display as nil).
ALTER TABLE companies
  ALTER COLUMN trial_start_date DROP NOT NULL,
  ALTER COLUMN trial_end_date DROP NOT NULL;
