# Railway / Docker: install deps in a separate layer so code-only commits reuse the pip cache.
# Build context = repository root (see railway.toml dockerfilePath).
FROM python:3.11-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY saas/backend/requirements.txt /app/requirements.txt
RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r /app/requirements.txt

COPY saas/backend /app

EXPOSE 8000

# PORT is set by Railway; default for local runs.
CMD ["sh", "-c", "exec gunicorn app.main:app -w 1 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8000}"]
