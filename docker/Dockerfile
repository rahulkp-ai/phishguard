# =============================================================================
# PhishGuard — Multi-stage Dockerfile
# =============================================================================
#
# Stage 1 — builder
#   Full Python image with build tools.  Installs all Python dependencies
#   into an isolated prefix (/install) so nothing bleeds into the runtime stage.
#   This stage is discarded after the build — it never ships.
#
# Stage 2 — runtime
#   Slim Python image.  Copies only the installed packages and application code.
#   Runs as a non-root user (phishguard, uid=1001).
#
# Why multi-stage?
#   - Build tools (gcc, pip, setuptools wheel build) are only needed during
#     installation, not at runtime.  Stripping them reduces the final image by
#     ~200 MB and eliminates an entire class of CVEs.
#   - The builder stage is cache-friendly: the `pip install` layer is
#     invalidated only when pyproject.toml changes, not when source code changes.
#
# Build:
#   docker build -f docker/Dockerfile -t phishguard:latest .
#
# Run (development — no model baked in, mount your models/ dir):
#   docker run -p 5000:5000 \
#     -e SECRET_KEY=dev-only \
#     -v $(pwd)/models:/app/models \
#     phishguard:latest
#
# Run (production — with a pre-trained model in models/):
#   docker run -p 5000:5000 \
#     -e SECRET_KEY=$(python scripts/generate_secret_key.py) \
#     -v $(pwd)/models:/app/models \
#     phishguard:latest
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1 — builder
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS builder

# Prevents Python from writing .pyc files and enables unbuffered stdout/stderr
# (important for log aggregators that read stdout).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Copy dependency manifest first — Docker caches this layer until
# pyproject.toml changes, so re-builds after source edits are fast.
COPY pyproject.toml .
COPY src/ src/

# Install all runtime dependencies into /install.
# --prefix=/install puts everything into a single directory that we copy
# wholesale into the runtime stage, keeping it completely self-contained.
RUN pip install --prefix=/install .


# -----------------------------------------------------------------------------
# Stage 2 — runtime
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Tell Python where to find the packages installed by the builder stage
    PYTHONPATH=/app/src

# Security: install only what's needed at runtime.
# curl is required for the Docker health check (HEALTHCHECK CMD).
# ca-certificates is required for HTTPS requests to phishing feeds.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Non-root user — running as root inside a container is a security risk.
# Even if an attacker breaks out of the app, they get uid=1001, not root.
# RUN groupadd --gid 1001 phishguard \
#     && useradd --uid 1001 --gid 1001 --no-create-home --shell /bin/false phishguard

RUN groupadd --gid 1001 phishguard \
    && useradd --uid 1001 --gid 1001 -m --shell /bin/false phishguard

WORKDIR /app

# Copy installed Python packages from the builder stage
COPY --from=builder /install /usr/local

# Copy application source — ordered from least-to-most volatile so Docker
# can cache the layers efficiently.
# 1. Package source (changes when features/models change)
COPY src/ src/
# 2. Flask application
COPY app/ app/
# 3. Gunicorn configuration
COPY docker/gunicorn.conf.py gunicorn.conf.py
# 4. Entry point
COPY run.py .

# Create the models directory and set ownership.
# The models/ dir is intentionally empty in the image — mount a volume or
# run the training pipeline to populate it (see docker-compose.yml).
RUN mkdir -p models data/processed \
    && chown -R phishguard:phishguard /app

# Switch to non-root user for all subsequent commands
USER phishguard

# Expose the port gunicorn will listen on.
# The actual binding is controlled by PORT env var in gunicorn.conf.py.
EXPOSE 5005

# Health check — Docker and Kubernetes use this to know when the container
# is ready to receive traffic.  Checks the /api/health endpoint every 30s.
# --fail makes curl exit non-zero on HTTP error responses (4xx, 5xx).
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl --fail --silent http://localhost:5005/api/health || exit 1

# Default command — runs gunicorn using the config file.
# Override with `docker run ... python run.py` for the dev server.
CMD ["gunicorn", "--config", "gunicorn.conf.py", "run:app"]
