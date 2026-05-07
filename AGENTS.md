# AGENTS.md

## Cursor Cloud specific instructions

### Architecture overview

This is a two-app repo: a **SaaS** stack (FastAPI backend + React/Vite frontend + PostgreSQL) and an **optional legacy** Flask/SQLite app. See `README.md` for the full layout.

### Required services

| Service | Port | Start command |
|---------|------|---------------|
| PostgreSQL 16 | 5432 | `sudo docker compose up -d postgres` (from repo root) |
| FastAPI backend | 8000 | `cd saas/backend && source venv/bin/activate && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` |
| Vite frontend | 5173 | `cd saas/frontend && npm run dev` |

### Startup notes

- **Docker must be running** before starting PostgreSQL. In Cloud Agent VMs, Docker requires `fuse-overlayfs` storage driver and `iptables-legacy`. The daemon is started with `sudo dockerd`.
- The backend `.env` is created by copying `saas/backend/.env.example` → `saas/backend/.env`. The defaults match `docker-compose.yml` (user `fir`, password `fir`, database `fir_saas`).
- The backend auto-creates all DB tables and applies SQL migrations on startup (`Base.metadata.create_all` + `apply_sql_migrations`), so no manual schema initialization is needed beyond having the database exist.
- The Vite dev server proxies `/api`, `/auth`, `/admin`, `/subscription`, `/health` to the backend on port 8000 (see `saas/frontend/vite.config.ts`). The frontend binds to `localhost` only by default; use `--host` if external access is needed.

### Lint / type-check / build

- **TypeScript check**: `cd saas/frontend && npx tsc --noEmit` — note: there are 3 pre-existing type errors (missing `@types/qrcode`, a `Window.FIR_PREVIEW_API` augmentation) that do not affect the build.
- **Frontend build**: `cd saas/frontend && npm run build`
- No ESLint, pytest, or other lint/test framework is currently configured in this repo.

### Gotchas

- The `package-lock.json` exists for the frontend, so use `npm` (not pnpm/yarn).
- Python venv lives at `saas/backend/venv/`. Always activate it before running backend commands.
- SMTP env vars are optional; password-reset emails won't send without them but the app works fine.
