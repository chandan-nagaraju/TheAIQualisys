# Railway: set service "Root Directory" to `saas/backend` so build context is this folder.
# Local build: docker build -f Dockerfile .
# (run from saas/backend), or: docker build -f saas/backend/Dockerfile saas/backend
FROM python:3.11-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Read PORT via Python so exec-form overrides (Railway UI / startCommand) cannot leave a literal \"$PORT\".
CMD ["python", "run_gunicorn.py"]
