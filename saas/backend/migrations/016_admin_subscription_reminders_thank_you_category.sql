-- Thank-you reminder: category + richer audit fields.
ALTER TABLE admin_subscription_reminders
    ADD COLUMN IF NOT EXISTS thank_you_category VARCHAR(32),
    ADD COLUMN IF NOT EXISTS current_month_report_count INTEGER,
    ADD COLUMN IF NOT EXISTS top_5_parts JSONB,
    ADD COLUMN IF NOT EXISTS total_time_saved_hours DOUBLE PRECISION;
