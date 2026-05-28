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

# Run migrations, then launch the API
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
