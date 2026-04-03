# How to run everything

## One command (Windows)

From the repo root, **double‑click `start-dev.bat`** or run:

```powershell
.\start-dev.ps1
```

That expects **PostgreSQL already running locally** on port **5432** (Windows service — see §1 below), then starts **FastAPI** and **Vite** in **one terminal** with labeled logs — no extra tabs.  
`Ctrl+C` stops the API and UI only.

If you use **Docker** for Postgres instead: `.\start-dev.ps1 -UseDocker`

---

You also have **three** pieces if you prefer manual control:

| What | Port | Purpose |
|------|------|---------|
| **PostgreSQL** | 5432 | Database for the SaaS API (FastAPI) |
| **SaaS API** (FastAPI) | 8000 | Auth, subscriptions, `/api/v2`, admin |
| **SaaS UI** (React) | 5173 | Signup, login, dashboard, pricing |
| **Legacy FIR** (Flask) | 5000 | Your original app (upload, FIR preview, SQLite) — optional |

---

## 1. PostgreSQL (one-time setup)

1. Install PostgreSQL on Windows (see **`POSTGRES_WINDOWS.md`**), or use Docker if you prefer.
2. Start the **PostgreSQL** Windows service (`services.msc` → postgresql → **Running**).
3. Open **SQL Shell (psql)** or pgAdmin, connect as user **`postgres`**, then run the script:

   `saas/database/init_fir_saas_postgres.sql` (repo root: run this file in psql as `postgres`)

   That creates user `fir`, password `fir`, database `fir_saas`.

---

## 2. SaaS backend (FastAPI)

```powershell
cd F:\beta\fir-automation\saas\backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` if you don’t have `.env` yet, then set at least:

```env
DATABASE_URL=postgresql+psycopg2://fir:fir@localhost:5432/fir_saas
```

Start the API:

```powershell
cd F:\beta\fir-automation\saas\backend
.\venv\Scripts\activate
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Check: open **http://127.0.0.1:8000/health** — you should see JSON with `"status":"ok"`.

---

## 3. SaaS frontend (React)

**New terminal** (keep the API running):

```powershell
cd F:\beta\fir-automation\saas\frontend
npm install
npm run dev
```

Open **http://127.0.0.1:5173** — after login, **FIR workspace** at `/workspace/dashboard` mirrors legacy Flask (customers, Excel upload, inspection, parts A–D, settings, FIR preview HTML). On **Inspection results** (`/workspace/inspection/results`), use **Auto-fill all measured values** (same rules as the FIR preview teal button) and then **Download all reports as ZIP**. **Usage & billing** at `/dashboard` is v2 subscription + export/import.

The dev server proxies API calls to port **8000** (see `vite.config.ts`). **FIR preview** URLs always use relative `/api/...` so they stay on the same origin as the SPA (needed for batch autofill / ZIP on inspection results). You can still set `VITE_API_URL` for other API calls if your setup requires it; preview links will not use that host.

---

## 4. Legacy Flask app (optional)

**New terminal:**

```powershell
cd F:\beta\fir-automation\legacy
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000** — original FIR workflow (SQLite).

**Part master → SaaS:** On Flask **http://127.0.0.1:5000/parts**, use **Download all parts (full A–D JSON)** for a bundle, or **Download** on a row / part-detail export for one part. On SaaS **Parts master**, **Import JSON** accepts the same bundle or single-part file. **Download all** / **Import** on either side use the same formats (`fir_part_master_bundle_v1` / `fir_part_master_v1`).

**Pricing inside the legacy app:** visit **http://127.0.0.1:5000/pricing** (also linked from the header and dashboard). Buttons point at the React SaaS URLs. Optional environment variables (same machine defaults shown):

| Variable | Default | Purpose |
|----------|---------|---------|
| `SAAS_APP_URL` | `http://127.0.0.1:5173` | Base URL for SaaS signup / upgrade links |
| `SAAS_UPI_ID` | `yourupi@okaxis` | Shown on `/pricing` |
| `SAAS_MANUAL_PAYMENT_MESSAGE` | (built from UPI) | WhatsApp / UPI line |

This does **not** need PostgreSQL.

---

## 5. Sync SQLite → PostgreSQL (optional)

After you **sign up** a company in the SaaS UI, sync legacy parts from `legacy/database/fir.db`:

```powershell
cd F:\beta\fir-automation\saas\backend
.\venv\Scripts\activate
python scripts/sync_sqlite_to_pg.py --vendor-code YOUR_VENDOR_CODE --sqlite ..\legacy\database\fir.db --dry-run
python scripts/sync_sqlite_to_pg.py --vendor-code YOUR_VENDOR_CODE --sqlite ..\legacy\database\fir.db
```

Use the **vendor code** you chose at signup.

---

## Typical day-to-day

1. PostgreSQL service **Running**
2. Terminal A: `uvicorn` on **8000**
3. Terminal B: `npm run dev` on **5173**
4. (Optional) Terminal C: `cd legacy` → `python app.py` on **5000**

---

## If something fails

| Symptom | Check |
|--------|--------|
| API won’t start / DB error | `DATABASE_URL`, Postgres service, DB `fir_saas` exists |
| UI can’t login / network error | API running on 8000, browser on 5173 |
| `pip` / `python` not found | Use `py -m pip` or activate the correct venv |
| Port in use | Change port in uvicorn (`--port 8001`) and update `vite.config.ts` proxy |

More detail: **`POSTGRES_WINDOWS.md`**, **`README.md`** (SaaS section).
