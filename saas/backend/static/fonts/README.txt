Place FIR preview font files here for the SaaS backend:
- Quali_1.woff2 (preferred)
- Quali_1.woff
- Quali_1.ttf (fallback)

The FIR preview template will try to inline these files first and fall back to
serving them from /api/app/static/fonts/*. Keep these files in this directory
on every deployment.

Important: this README is only an instruction file. You must add the actual
font binaries (Quali_1.woff2 / Quali_1.woff / Quali_1.ttf) into this folder
in your repository or deployment bundle, otherwise the custom Quali font
cannot render and the preview will use fallback fonts.
