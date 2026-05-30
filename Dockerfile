# =============================================================================
# Backend — FastAPI (production image)
# =============================================================================
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps — build tools needed for some wheels (bcrypt, cryptography, asyncpg fallback)
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
 && rm -rf /var/lib/apt/lists/*

# Install Python deps first for better layer caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Non-root user
RUN useradd --create-home --shell /bin/bash --uid 1000 appuser \
 && mkdir -p /app/uploads/cv \
 && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# audit_devops F-13: container health probe so docker / k8s know the app is
# actually ready, not just running. Cheap — `/health` does not touch the DB.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# audit_devops F-15: workers=2 spreads requests across the available CPU
# (FastAPI is async but each worker has one event loop). `--proxy-headers`
# + `--forwarded-allow-ips="*"` tells uvicorn to trust the `X-Forwarded-*`
# headers Caddy sets — without them `request.client.host` is always the
# Caddy container IP and rate-limit / audit logs cannot see the real client.
# audit_devops F-04 is the migration race — running `alembic upgrade head`
# in CMD is fine for a single instance but should move to a dedicated
# `migrator` service before `--scale backend=N` is used; tracked in audit
# implementation status.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4 --proxy-headers --forwarded-allow-ips=*"]
