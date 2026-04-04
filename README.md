# FIR Automation

**Final Inspection Report (FIR) automation** for manufacturing: invoice Excel → part selection → inspection → printable FIR (A–D sections from part master data).

**Last updated:** March 2025

---

## Repository layout (two apps)

| Folder | App | Tech |
|--------|-----|------|
| **`legacy/`** | Original single-tenant FIR (Flask, SQLite) | Flask · Jinja · `legacy/database/fir.db` |
| **`saas/backend/`** | Multi-tenant API (FastAPI, PostgreSQL) | FastAPI · SQLAlchemy · JWT |
| **`saas/frontend/`** | Web UI (workspace, dashboard, admin) | React 18 · Vite · TypeScript · Tailwind |

The SaaS API serves FIR HTML using **SaaS-owned templates/static assets** (`saas/backend/templates/`, `saas/backend/static/`), so SaaS deployments stay independent from the legacy app.

---

## Features

- **Customers** — vendor codes; select customer before upload when there are multiple.
- **Invoice upload** — `.xlsx` / `.xls`; flexible column mapping (part number, description, quantity, invoice no, date).
- **Inspection** — choose rows → results → FIR preview (HTML) with sections **A**–**D**.
- **Part master** — JSON import/export (`fir_part_master_bundle_v1` / `fir_part_master_v1`).
- **Part master from Excel (SaaS)** — template → upload → review → save. See [`docs/PART_MASTER_EXCEL.md`](docs/PART_MASTER_EXCEL.md).
- **FIR preview** — editable tables, auto-fill, PDF / batch ZIP (workspace).
- **SaaS extras** — subscriptions (feature-flagged), company dashboard, v2 invoices, admin, UPI/pricing.

---

## Quick start (Windows — recommended)

1. **PostgreSQL** on `localhost:5432` with DB/user from [`saas/database/init_fir_saas_postgres.sql`](saas/database/init_fir_saas_postgres.sql), **or** Docker: `docker compose up -d postgres`.
2. Copy [`saas/backend/.env.example`](saas/backend/.env.example) → `saas/backend/.env` and set `DATABASE_URL`, `JWT_SECRET`, `ADMIN_JWT_SECRET` (and change bootstrap admin credentials if set).
3. From repo root:

```powershell
.\start-dev.ps1
# or: .\start-dev.ps1 -UseDocker   # if Postgres is only in Docker
```

Starts **FastAPI** (port **8000**) and **Vite** (port **5173**). **`Ctrl+C`** stops both.

**Details:** [`docs/QUICKSTART.md`](docs/QUICKSTART.md)

| URL | Purpose |
|-----|---------|
| http://127.0.0.1:5173 | React app |
| http://127.0.0.1:5173/workspace/dashboard | FIR workspace |
| http://127.0.0.1:8000/health | API liveness |
| http://127.0.0.1:8000/docs | OpenAPI |

---

## Manual run (any OS)

**Database**

```bash
docker compose up -d postgres
```

**API**

```bash
cd saas/backend
python -m venv venv
# Windows: venv\Scripts\activate  |  Unix: source venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend**

```bash
cd saas/frontend
npm install
npm run dev
```

**Production build**

```bash
cd saas/frontend
npm run build
# output: saas/frontend/dist — serve behind nginx/Caddy; proxy /api to FastAPI
```

---

## Tree (abbreviated)

```
fir-automation/
├── legacy/
│   ├── app.py                 # Flask entry
│   ├── requirements.txt
│   ├── database/              # SQLite schema + fir.db
│   ├── templates/
│   ├── static/
│   └── uploads/
├── saas/
│   ├── backend/               # FastAPI (venv here; owns SaaS FIR templates/static)
│   ├── frontend/              # Vite + React
│   └── database/
│       └── init_fir_saas_postgres.sql
├── docker-compose.yml
├── start-dev.ps1 / start-dev.bat
└── docs/
```

---

## SaaS API

- **Workspace** — `/api/app/...` — customers, upload, inspection, parts, settings, FIR HTML, part master JSON/Excel.
- **Config** — see `saas/backend/.env.example` (`ENABLE_SUBSCRIPTION`, `LEGACY_SQLITE_PATH`, etc.).

---

## Legacy Flask (optional)

```bash
cd legacy
python -m venv venv
venv\Scripts\activate          # or: source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000** — SQLite at **`legacy/database/fir.db`**. No PostgreSQL required.

**Part master → SaaS:** Export JSON from Flask **Parts**; **Import JSON** on SaaS **Parts master** (same formats).

---

## SQLite → PostgreSQL sync

```bash
cd saas/backend
python scripts/sync_sqlite_to_pg.py --vendor-code YOUR_VENDOR_CODE --sqlite ./data/legacy_fir.db --dry-run
python scripts/sync_sqlite_to_pg.py --vendor-code YOUR_VENDOR_CODE --sqlite ./data/legacy_fir.db
```

See [`docs/QUICKSTART.md`](docs/QUICKSTART.md).

---

## Operations (short)

Production: Gunicorn+Uvicorn workers, nginx/Caddy + HTTPS, Postgres backups, restart policies, monitor `/health`.

---

## Documentation

| Doc | Content |
|-----|---------|
| [`docs/QUICKSTART.md`](docs/QUICKSTART.md) | Full runbook, sync, troubleshooting |
| [`docs/POSTGRES_WINDOWS.md`](docs/POSTGRES_WINDOWS.md) | PostgreSQL on Windows |
| [`docs/PART_MASTER_EXCEL.md`](docs/PART_MASTER_EXCEL.md) | Part master Excel |

Implementation reference: **`legacy/app.py`**, **`legacy/database/schema.sql`**.

---

## License & support

Internal / organizational use.
