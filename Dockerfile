# =============================================================================
# Stage 1: Base image with uv and system dependencies
# =============================================================================
FROM python:3.12-slim-bookworm AS base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app/src" \
    PATH="/app/.venv/bin:$PATH"

# Install system dependencies and uv
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv

# Create non-root user
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

# Set working directory
WORKDIR /app

# =============================================================================
# Stage 2: Dependencies installation
# =============================================================================
FROM base AS deps

# Copy dependency files
COPY pyproject.toml uv.lock README.md ./

# Install dependencies with uv (frozen lockfile, no project install yet)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

# =============================================================================
# Stage 3: Production image
# =============================================================================
FROM deps AS production

# Copy application code
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser alembic.ini ./
COPY --chown=appuser:appuser tools/ ./tools/
COPY --chown=appuser:appuser scripts/entrypoint.sh /app/entrypoint.sh

# Make entrypoint executable
RUN chmod +x /app/entrypoint.sh

# Install project itself
RUN uv sync --frozen --no-dev

# Create necessary directories
RUN mkdir -p /app/logs && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]

# Default command
CMD ["uvicorn", "payments_service.main:app", "--host", "0.0.0.0", "--port", "8000"]

# =============================================================================
# Stage 4: Development image
# =============================================================================
FROM deps AS development

# Install all dependencies including dev
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

# Copy application code
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser alembic.ini ./
COPY --chown=appuser:appuser tests/ ./tests/
COPY --chown=appuser:appuser docs/ ./docs/
COPY --chown=appuser:appuser Makefile ./
COPY --chown=appuser:appuser scripts/entrypoint.sh /app/entrypoint.sh

# Make entrypoint executable (already done in production stage, but let's be safe for dev-only builds)
USER root
RUN chmod +x /app/entrypoint.sh
USER appuser

# Create necessary directories
RUN mkdir -p /app/logs /app/htmlcov && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Default entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]

# Default command for development
CMD ["uvicorn", "payments_service.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# =============================================================================
# Stage 5: Testing image
# =============================================================================
FROM development AS testing

# Default command for testing
CMD ["pytest", "tests/", "-v", "--cov=src", "--cov-report=html", "--cov-report=term"]
