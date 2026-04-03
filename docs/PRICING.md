# Where to change SaaS pricing

Plan amounts, tier names, and invoice bands shown in the app and API are defined in more than one place today. Keep these in sync when you change prices.

| What to change | File |
|----------------|------|
| **₹ prices**, plan names, min/max invoice bands (`GET /subscription/plans`) | [`saas/backend/app/routers/subscription.py`](../saas/backend/app/routers/subscription.py) |
| **Monthly usage caps** per plan (must match the bands above) | [`saas/backend/app/subscription_logic.py`](../saas/backend/app/subscription_logic.py) — `plan_invoice_limit()` |
| **UPI ID**, WhatsApp number, payment message template | Environment variables / [`saas/backend/app/config.py`](../saas/backend/app/config.py) — `upi_id`, `whatsapp_number`, `whatsapp_message_template` |
| **Marketing / workspace pricing page copy** | [`saas/frontend/src/pages/PricingPage.tsx`](../saas/frontend/src/pages/PricingPage.tsx) |

**Subscription enforcement:** Trial and workspace gating use `ENABLE_SUBSCRIPTION` / `enable_subscription` in config (`true` in production when you want post-trial workspace blocking).

For existing PostgreSQL databases after pulling new models (part PDF columns, revision history, password reset tokens), run the SQL in [`saas/backend/migrations/001_workspace_features.sql`](../saas/backend/migrations/001_workspace_features.sql) if `create_all` did not add columns automatically.

Runtime now also applies SQL files from `saas/backend/migrations/*.sql` at startup and records them in a `schema_migrations` table. This helps hosted DBs (Render/Supabase/Neon) stay in sync when a deploy happens without a manual migration step.
