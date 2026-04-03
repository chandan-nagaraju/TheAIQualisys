-- Run once as PostgreSQL superuser (e.g. psql -U postgres)
-- Creates role and database matching saas/backend/.env.example defaults.

CREATE USER fir WITH PASSWORD 'fir';

CREATE DATABASE fir_saas OWNER fir;

GRANT ALL PRIVILEGES ON DATABASE fir_saas TO fir;

-- PostgreSQL 15+: schema privileges for the owner are usually enough.
-- If your app connects as fir and creates tables, fir is owner of fir_saas — no extra grants needed.
