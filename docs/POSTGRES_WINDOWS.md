# Install PostgreSQL on Windows (no Docker)

Use this if Docker is not available on your PC. The SaaS API expects a database URL like:

`postgresql+psycopg2://USER:PASSWORD@localhost:5432/fir_saas`

---

## Option A — winget (fastest)

Open **PowerShell** or **Command Prompt** as Administrator (recommended) and run:

```powershell
winget install PostgreSQL.PostgreSQL.17 --accept-package-agreements --accept-source-agreements
```

Follow any installer prompts. Note:

- **Port:** default `5432` (keep this unless you have a conflict).
- **Superuser password:** you set a password for the built-in `postgres` user — **save it**; you need it once to create the app database.

After install, confirm the service is running:

1. Press `Win + R`, type `services.msc`, Enter.
2. Find **postgresql-x64-17** (or similar) → Status should be **Running**. If not, right-click → **Start**.

Add PostgreSQL `bin` to your PATH (adjust version if yours differs):

- Typical path: `C:\Program Files\PostgreSQL\17\bin`
- Settings → System → About → Advanced system settings → Environment Variables → edit **Path** → New → add that folder.

Open a **new** terminal and check:

```powershell
psql --version
```

---

## Option B — Official installer (EDB)

1. Download: [PostgreSQL Windows downloads](https://www.postgresql.org/download/windows/) → use the **EDB Installer**.
2. Run the wizard: choose components (PostgreSQL Server, Command Line Tools; pgAdmin optional), port **5432**, set **postgres** user password.
3. Ensure the Windows service for PostgreSQL is **Running** (`services.msc`).

---

## Create database and user for FIR SaaS

The project defaults to user `fir`, password `fir`, database `fir_saas`. You can use different values — then update `DATABASE_URL` in `saas/backend/.env`.

### Using psql (command line)

1. Open **SQL Shell (psql)** from the Start menu, or in PowerShell:

   ```powershell
   & "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -h localhost
   ```

   Enter the **postgres** superuser password you set during install.

2. Run:

   ```sql
   CREATE USER fir WITH PASSWORD 'fir';
   CREATE DATABASE fir_saas OWNER fir;
   GRANT ALL PRIVILEGES ON DATABASE fir_saas TO fir;
   \q
   ```

### Using pgAdmin

1. Open **pgAdmin**, connect to the local server (password = postgres superuser).
2. Right-click **Login/Group Roles** → Create → Role: name `fir`, password `fir`, Privileges: **Can login**.
3. Right-click **Databases** → Create → Database: name `fir_saas`, Owner `fir`.

---

## Configure `saas/backend/.env`

Match your actual password and port:

```env
DATABASE_URL=postgresql+psycopg2://fir:fir@localhost:5432/fir_saas
```

If you use the `postgres` user instead:

```env
DATABASE_URL=postgresql+psycopg2://postgres:YOUR_POSTGRES_PASSWORD@localhost:5432/fir_saas
```

Start the API from `saas/backend`; tables are created automatically on first run (`create_all`).

---

## Troubleshooting

| Issue | What to try |
|--------|-------------|
| `psql` not found | Add `C:\Program Files\PostgreSQL\17\bin` to PATH, new terminal. |
| Connection refused | Service not running → `services.msc` → start PostgreSQL. |
| Password authentication failed | Wrong user/password in `DATABASE_URL`; reset role password in psql: `ALTER USER fir PASSWORD 'newsecret';` |
| Port in use | Another app uses 5432 → change PostgreSQL port in install or stop the other service; update `DATABASE_URL` port. |

---

## Uninstall

Windows **Settings → Apps**, or winget:

```powershell
winget uninstall PostgreSQL.PostgreSQL.17
```
