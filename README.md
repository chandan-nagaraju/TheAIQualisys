# TheAIQualisys — FIR Automation SaaS

**Last updated:** April 2026

## 1. Project title

**FIR Automation (TheAIQualisys)** — a multi-tenant web application for **Final Inspection Report (FIR)** generation in manufacturing: invoice Excel → inspection workflow → printable PDF reports (sections A–D) driven by **part master** data, with **subscriptions**, **admin**, and **module** pricing.

---

## 2. Overview

The repository contains:

| Area | Description |
|------|-------------|
| **`saas/`** | **Production SaaS:** React (Vite) frontend + FastAPI backend + PostgreSQL. |
| **`legacy/`** | **Original single-tenant** Flask + SQLite app (reference / migration source). |
| **`docs/`** | Runbooks for Postgres, part master Excel, pricing notes. |

The SaaS backend owns **FIR HTML templates** (`saas/backend/templates/`) and **static assets** (`saas/backend/static/`) so deployments are self-contained.

---

## 3. Problem it solves

Quality teams need **consistent FIR documents** aligned with **customer drawings** and **invoice lines**, without retyping data. This system:

- Ingests **invoice Excel** (`.xlsx` / `.xls`, including legacy BIFF and XMLSpreadsheet mislabeled as `.xls`).
- Resolves **parts** and **customers** per company.
- Builds **live FIR previews** (editable, auto-fill, PDF export) and **batch ZIP** downloads.
- Optionally enforces **trial / subscription** windows and **usage** caps for invoices + FIR reports.

---

## 4. Features

- **Multi-tenant workspace** — companies, users, customers (vendor codes), JWT-scoped APIs.
- **Invoice upload & parsing** — flexible column mapping; enrichment with draw rev, **sample size** from quantity rules, parameter counts from part master.
- **Inspection pipeline** — row selection → enriched data → FIR preview iframes → auto-fill measured values → PDF per row → ZIP.
- **Part master** — dimensions (A), complaints (B), material (C), surface coating (D); JSON import/export; Excel template and paste-to-table flows.
- **Company FIR settings** — logo, signatures, optional custom **Quali** TTF for measured values; document control block (format no, rev dates).
- **Subscriptions & billing** — feature-flagged (`ENABLE_SUBSCRIPTION`); plan types; manual UPI / WhatsApp upgrade flow; module catalog and admin pricing.
- **Platform admin** — companies, users, pricing, impersonation support in subscription logic.
- **v2 APIs** — extended company/invoice flows where applicable.

---

## 5. Architecture

```text
┌─────────────────┐     HTTPS / JSON      ┌──────────────────┐
│  React SPA      │ ◄──────────────────► │  FastAPI         │
│  (Vite, static) │    Bearer JWT        │  Gunicorn+Uvicorn │
│  Amplify / etc. │                      │  Railway / etc.  │
└─────────────────┘                      └────────┬─────────┘
                                                │
                                         SQLAlchemy
                                                │
                                        ┌───────▼────────┐
                                        │  PostgreSQL    │
                                        │  (e.g. Supabase)│
                                        └────────────────┘
```

- **Frontend** talks to the API via `VITE_API_URL` (or dev proxy to `localhost:8000`). FIR preview URLs use **same-origin** `/api/...` in batch flows so iframes can call `FIR_PREVIEW_API` (see `InspectionResultsPage`, `vite.config.ts`).
- **Backend** serves OpenAPI at `/docs`, health at `/health`, HTML FIR at workspace routes, file uploads under configurable `workspace_upload_dir`.
- **Database** is relational; schema is created via SQLAlchemy `create_all` plus **incremental SQL** in `saas/backend/migrations/`.

---

## 6. Tech stack & rationale

| Layer | Technology | Why (typical) |
|-------|------------|----------------|
| **Frontend** | React 18, TypeScript, Vite, Tailwind, React Router | Fast dev/build, typed UI, component styling, SPA routing. |
| **HTTP client** | `fetch` wrappers in `api.ts` | Simple; JWT in `Authorization`; `VITE_API_URL` for production. |
| **ZIP / QR** | JSZip, qrcode | Client-side batch PDF packaging; UPI QR on upgrade page. |
| **Backend** | FastAPI, Pydantic, Uvicorn, Gunicorn | Async-capable ASGI, automatic OpenAPI, production process model. |
| **ORM** | SQLAlchemy 2 | Mature Postgres mapping, relationships, migrations companion. |
| **Auth** | JWT (`python-jose`), bcrypt | Stateless API auth; password hashing. |
| **Excel** | pandas, openpyxl, xlrd | `.xlsx` and legacy `.xls` / XML spreadsheet handling in `fir_excel.py` / `fir_part_excel.py`. |
| **Templates** | Jinja2 | Server-rendered FIR HTML with injected part/spec data. |
| **PDF (browser)** | html2pdf.js in `fir_preview.html` | No server Chromium dependency; runs in preview iframe. |
| **Database** | PostgreSQL | Multi-tenant relational data; **any** managed Postgres (local, Supabase, RDS) via `DATABASE_URL`. |
| **Deployment** | Railway (`railway.toml`), Amplify/Vercel (frontend), Docker Compose (local Postgres) | Common PaaS split: API + DB + static hosting. |

**Note:** The codebase does **not** use Supabase client SDKs or Realtime; if you use **Supabase**, it is as **managed Postgres** (and egress applies to query/result traffic).

---

## 7. Folder-by-folder

| Path | Role |
|------|------|
| `saas/frontend/` | React app: pages, layouts, `api.ts`, Vite config, `dist/` after build. |
| `saas/backend/app/` | FastAPI app: `main.py`, `models.py`, `deps.py`, `config.py`, `security.py`, `subscription_logic.py`, Excel FIR modules, routers. |
| `saas/backend/templates/` | `fir_preview.html` — FIR UI, autofill, PDF blob export API. |
| `saas/backend/migrations/` | Incremental SQL for existing DBs. |
| `saas/backend/static/` | Shared CSS, font placeholders. |
| `saas/database/` | `init_fir_saas_postgres.sql` — create DB user/db (one-time). |
| `docs/` | QUICKSTART, PART_MASTER_EXCEL, POSTGRES_WINDOWS, PRICING. |
| `legacy/` | Flask app, SQLite schema, old templates (optional). |
| `docker-compose.yml` | Local **Postgres 16** only. |

---

## 8. Important files (file-level)

| File | Purpose |
|------|---------|
| `saas/backend/app/main.py` | App factory, CORS, router mounts, `/health`, lifespan (migrations, pricing seed, bootstrap admin). |
| `saas/backend/app/config.py` | `DATABASE_URL`, JWT secrets, CORS, SMTP, UPI, feature flags. |
| `saas/backend/app/models.py` | SQLAlchemy models: `Company`, `CompanyUser`, `PartV2`, specs/complaints/materials/coatings, `CompanySettings` (incl. blobs), billing-related tables, `ModulePricing`, etc. |
| `saas/backend/app/deps.py` | Auth dependencies, `get_company_for_user` (subscription sync), workspace gates. |
| `saas/backend/app/subscription_logic.py` | Trial/subscription rules, workspace access, invoice/FIR limits, impersonation. |
| `saas/backend/app/fir_excel.py` | Invoice parse, `enrich_rows_with_parts`, `sample_size_for_quantity`. |
| `saas/backend/app/fir_part_excel.py` | Part master Excel parsing, templates, import bundle. |
| `saas/backend/app/routers/workspace.py` | **Largest** router: customers, parts, settings, drawing upload, inspection enrich, FIR preview, quotas, record reports. |
| `saas/backend/app/routers/auth.py` | Signup, login, tokens, password reset. |
| `saas/backend/app/routers/subscription.py` | Public subscription status, plans, upgrade info. |
| `saas/backend/app/routers/admin.py` | Admin APIs. |
| `saas/backend/app/routers/v2/endpoints.py` | v2 JSON APIs. |
| `saas/frontend/src/api.ts` | `apiUrl`, `apiFetch`, `workspaceFetch`, error handling. |
| `saas/frontend/src/App.tsx` | Route table: workspace, dashboard, admin, auth. |
| `saas/frontend/vite.config.ts` | Dev server proxy to FastAPI. |
| `railway.toml` | Railway build/start for `saas/backend`. |

---

## 9. Data flow (simplified)

1. **User** logs in → JWT stored → calls `/subscription/status` or workspace APIs.
2. **Upload** → POST file → `parse_invoice_excel` → rows returned / enriched on inspection POST.
3. **Enrich** → `POST /api/app/inspection/enrich` → part master join → `sample_size`, `num_params`, customer vendor display.
4. **FIR preview** → `GET` HTML with query params + JSON spec/ccp/material/coating from DB → browser renders iframes → `FIR_PREVIEW_API.autoFillMeasuredValues` / `generatePdfBlob`.
5. **ZIP** → client-side JSZip over PDF blobs from each iframe.
6. **Billing** (if enabled) → usage counters, `FirReportEvent` rows, subscription checks in `subscription_logic.py`.

---

## 10. API surface (summary)

Routers (prefixes):

| Prefix | Router file |
|--------|----------------|
| `/auth` | `auth.py` (also mounted under `/api` in `main.py` for legacy paths) |
| `/subscription` | `subscription.py` |
| `/api/pricing` | `pricing_public.py` |
| `/api/billing` | `billing.py` |
| `/api/modules` | `modules.py` |
| `/api/v2` | `v2/endpoints.py` |
| `/api/app` | `workspace.py` (FIR workspace) |
| `/admin` | `admin.py` (also under `/api`) |

**Discovery:** `GET /docs` (OpenAPI) when the API is running.

---

## 11. Database schema

- **Source of truth in code:** `saas/backend/app/models.py` (SQLAlchemy). Tables are **created** at startup via `Base.metadata.create_all` plus **`saas/backend/migrations/*.sql`** for existing deployments.
- **Core entities:** `companies`, `company_users`, `fir_customers`, `parts_v2` (+ `part_specs_v2`, `part_complaints_v2`, `part_materials_v2`, `part_coatings_v2`, `part_revision_history`), `invoices_v2`, `company_settings` (document meta + **binary** logo/signature/font optional), `fir_report_events`, `password_reset_tokens`, `platform_admins`, `module_pricing`, `module_subscriptions`, `module_trials`, …
- **Initial DB user/database:** `saas/database/init_fir_saas_postgres.sql` (creates `fir` / `fir_saas` — adjust for production).

For a **visual** diagram, generate from models or use Alembic if you add it later.

---

## 12. Setup (local)

1. **PostgreSQL** — Docker: `docker compose up -d postgres` **or** install Postgres and run `saas/database/init_fir_saas_postgres.sql` as superuser.
2. **Backend** — `cd saas/backend`, `python -m venv venv`, `pip install -r requirements.txt`, copy `.env.example` → `.env`, set `DATABASE_URL`, `JWT_SECRET`, `ADMIN_JWT_SECRET`, `CORS_ORIGINS`, `PUBLIC_APP_URL`.
3. **Run API** — `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
4. **Frontend** — `cd saas/frontend`, `npm install`, `npm run dev` (port 5173, proxies to 8000).
5. **Backend unit tests (optional)** — from `saas/backend`: `pip install -r requirements-dev.txt`, then `PYTHONPATH=. python -m pytest tests/ -q`.

**One-command Windows:** `.\start-dev.ps1` (see `docs/QUICKSTART.md`).

---

## 13. Deployment (typical)

| Component | Options |
|----------|---------|
| **API** | **Railway** (see `railway.toml`: `gunicorn` + `UvicornWorker` from `saas/backend`). Set env vars to match `.env.example`. |
| **Frontend** | **AWS Amplify**, **Vercel**, or any static host of `npm run build` output (`saas/frontend/dist`). Set `VITE_API_URL` to the **public API URL**. Use SPA **rewrite to index.html** for client routes. |
| **DB** | **Supabase**, RDS, or Railway Postgres — single `DATABASE_URL`. |
| **CORS** | `CORS_ORIGINS` (comma-separated) must include the **exact** SPA origin(s). `PUBLIC_APP_URL` is merged into CORS in `main.py`. |

**Monorepo hosting:** if the app root is `saas/frontend`, configure `amplify.yml` / `AMPLIFY_MONOREPO_APP_ROOT` / `applications:` as documented in your Amplify app (avoid duplicate `cd` into `saas/frontend`).

Do **not** put `DATABASE_URL` in the **frontend** host’s env (unnecessary and risky); only the API service needs it.

---

## 14. Future improvements

- **Observability** — structured logs, request IDs, metrics on hot paths.
- **Pagination** — list endpoints (parts, etc.) for large tenants.
- **Move binary settings** (logo, font) to **object storage** to cut DB egress (relevant for Supabase billing).
- **Server-side or queued PDF** for very large batches; optional headless browser service.
- **OpenAPI-generated client** for the frontend; reduce duplicate path logic.
- **Subscription sync** — avoid writing on every read (`get_company_for_user`); event-driven or cached updates.
- **E2E tests** (Playwright) for login → upload → inspection path.

---

## 15. Documentation index

| Document | Content |
|----------|---------|
| [`docs/QUICKSTART.md`](docs/QUICKSTART.md) | Step-by-step local run, sync script, tips |
| [`docs/POSTGRES_WINDOWS.md`](docs/POSTGRES_WINDOWS.md) | Postgres on Windows |
| [`docs/PART_MASTER_EXCEL.md`](docs/PART_MASTER_EXCEL.md) | Part master Excel format |
| [`docs/PRICING.md`](docs/PRICING.md) | Pricing notes |
| [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md) | Ops limits, config pitfalls, test notes, historical regressions |

---

## 16. License & support

Internal / organizational use unless otherwise specified.

---

## Legacy app

The **`legacy/`** Flask application remains for reference and SQLite-based workflows. See section “Legacy Flask” in older commits or run `python app.py` from `legacy/` for local port 5000.

```bash
cd legacy && pip install -r requirements.txt && python app.py
```

Migrate data with `saas/backend/scripts/sync_sqlite_to_pg.py` (see `docs/QUICKSTART.md`).
