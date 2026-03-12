# ============================================
# Dockerfile - AI Research Assistant Backend
# Multi-stage build for production (Poetry)
# ============================================

# --- Stage 1: Builder ---
FROM python:3.11-slim AS builder

ENV POETRY_VERSION=1.8.2 \
    POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

# Install Poetry
RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"

WORKDIR /app

# Install system dependencies for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency manifests first (layer caching)
COPY pyproject.toml poetry.lock* ./

# Install production dependencies only
RUN poetry install --only main --no-root --no-directory

# Copy project source and install the project itself
COPY . .
RUN poetry install --only main --no-root


# --- Stage 2: Production ---
FROM python:3.11-slim AS production

# Security: Run as non-root
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# Install runtime dependencies (libatomic1 + nodejs required for Prisma CLI)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    libatomic1 \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY . .

# Put venv on PATH
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PRISMA_BINARY_CACHE_DIR=/app/.prisma-cache

# Create prisma cache dir, generate client, then fix ownership
RUN mkdir -p /app/.prisma-cache && \
    prisma generate && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Run with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--loop", "uvloop", "--http", "httptools"]
