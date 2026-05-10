# teacher-comments backend image (per ARCH-001 §5.1)
# Two-stage build: deps installed via uv (fast, deterministic), runtime uses slim base.

# ── Builder stage ──────────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Install uv (pin version for reproducibility)
RUN pip install --no-cache-dir uv==0.11.7

WORKDIR /build

# Copy lockfile-relevant inputs first to maximise Docker layer cache
COPY pyproject.toml uv.lock* ./

# `--no-install-project` installs only deps; project itself copied in next layer
RUN uv sync --frozen --no-install-project --no-dev

# Now copy the project source and install (links app into the venv)
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN uv sync --frozen --no-dev

# ── Runtime stage ──────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Create non-root user; data + tmp owned by appuser
RUN useradd --create-home --uid 1000 appuser && \
    mkdir -p /app/data /app/tmp && \
    chown -R appuser:appuser /app

WORKDIR /app
COPY --from=builder --chown=appuser:appuser /build/.venv /app/.venv
COPY --from=builder --chown=appuser:appuser /build/app /app/app
COPY --from=builder --chown=appuser:appuser /build/alembic /app/alembic
COPY --from=builder --chown=appuser:appuser /build/alembic.ini /app/alembic.ini

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1

# Migrations run on container start; app fails fast if DB is unreachable
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
