# Known issues & operational limits

This document tracks **recurring pitfalls**, **design constraints**, and **things that look like bugs but are intentional**. It is not a substitute for GitHub Issues—use that for one-off bugs with repro steps.

## Deployment & configuration

- **`VITE_API_URL` (frontend)** must match the public Railway (or other) API URL. Wrong values cause login/workspace failures or CORS errors that look like “network glitches.”
- **`CORS_ORIGINS` / `PUBLIC_APP_URL` (backend)** must include every SPA origin (`https://theaiqualisys.com`, `https://www…`, Amplify preview URLs if used).
- **`ENABLE_SUBSCRIPTION`**: When `false`, **monthly invoice/FIR cap enforcement** is relaxed in API logic; **FIR workspace** still requires a valid **trial or paid** window. Production should normally use `true`.
- **SQL migrations** run **before** `create_all` on startup. If migrations fail or an old DB has a stranded table name (e.g. legacy `fir_report_events` vs `fir_events`), analytics can look empty until DB is aligned with `saas/backend/app/models.py` and `migrations/`.

## Auth & tenants

- **Password reset** uses **FastAPI + SMTP** (`EMAIL_FROM`, `SMTP_*`), not Supabase Auth. The SPA calls `/auth/forgot-password` and `/auth/reset-password`.
- **Deleting a tenant user** removes only `company_users`; **companies** and **FIR customers** remain until **Delete tenant** (admin) or manual DB cleanup.
- **`fir_token` vs `fir_admin_token`**: Some UI checks only company token; platform admins use a separate session.

## Payments & billing

- **UPI QR + WhatsApp** is **manual**: there is **no automatic bank/gateway webhook** to confirm payment or issue GST invoices. Activation is operational (admin or future automation).
- **Plan prices** on the marketing/upgrade UI come from **`/subscription/plans`** and admin pricing modules; keep them in sync with what you communicate to customers.

## Data & storage

- **Admin** “Delete tenant” removes related **Postgres** rows for that company; **S3** objects (e.g. logos under `company/{id}/…`) may remain unless cleaned separately.
- **Batch FIR PDF** in the browser depends on **iframe rendering**, device performance, and network; very large batches can still stress weak clients.

## Testing

Automated tests are **minimal** (see `saas/backend/tests/`). They do **not** spin up Postgres or the full FastAPI app by default.

```bash
cd saas/backend
pip install -r requirements-dev.txt
pytest tests/ -q
```

Add **integration tests** (with a test DB) and/or **Playwright** for critical UI paths as a follow-up.

## Historical regressions (fixed on active branches)

These were addressed in development; redeploy old builds and you may still see them:

- Workspace **Buy** linked to a **dead Vercel** host → use same-app `/upgrade`.
- Landing **Start with FIR** always sent users to **`/signup`** even when logged in → route to **`/workspace/dashboard`** when `fir_token` exists.
- **Parts export-all** `422` from route/param ordering → static `/parts/...` routes must stay before `/parts/{part_id}`.
- Railway **startup** / **`immutabledict`** errors from migration + SQLAlchemy result handling → fixed in migration runner and queries.

If something matches the above after deploy, confirm **branch**, **env vars**, and **migration logs** first.
