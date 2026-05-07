# AGENTS.md

## Cursor Cloud specific instructions

### Architecture

FIR Automation is a manufacturing inspection report platform with two apps:

| Service | Tech | Port | Directory |
|---------|------|------|-----------|
| **SaaS Backend** | FastAPI + PostgreSQL | 8000 | `saas/backend/` |
| **SaaS Frontend** | React 18 + Vite + Tailwind | 5173 | `saas/frontend/` |
| **Legacy App** (optional) | Flask + SQLite | 5000 | `legacy/` |

### Starting services

1. **PostgreSQL**: `docker compose up -d postgres` (from repo root). Docker daemon must be running first — in Cloud VMs run `sudo dockerd &>/tmp/dockerd.log &` then `sudo chmod 666 /var/run/docker.sock` before docker compose.
2. **Backend**: `cd saas/backend && source venv/bin/activate && python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
3. **Frontend**: `cd saas/frontend && npm run dev`

### Key files

- Backend env: `saas/backend/.env` (copy from `.env.example` if missing). Default `DATABASE_URL` connects to the Docker Postgres.
- Vite proxy: `saas/frontend/vite.config.ts` proxies `/api`, `/auth`, `/admin`, `/subscription`, `/health` to port 8000.

### Gotchas

- The login API endpoint uses the field `identifier` (not `email`): `POST /auth/login {"identifier":"…","password":"…"}`.
- Vite dev server binds to `localhost` only (not `0.0.0.0`). Use `http://localhost:5173` for requests, not `http://127.0.0.1:5173`.
- No ESLint or test runner is configured. TypeScript type-checking: `cd saas/frontend && npx tsc --noEmit` (has a few pre-existing type errors).
- Build: `cd saas/frontend && npx vite build`.
- Health check: `GET http://127.0.0.1:8000/health` returns `{"status":"ok",...}`.
- The backend auto-creates all database tables on startup via SQLAlchemy (no manual migration step needed).
