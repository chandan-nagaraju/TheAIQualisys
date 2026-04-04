Place FIR preview font files here for the SaaS backend:
- Quali_1.woff2 (preferred)
- Quali_1.woff
- Quali_1.ttf (fallback)

The FIR preview template will try to inline these files first and fall back to
serving them from /api/app/static/fonts/*. Keep these files in this directory
on every deployment.
