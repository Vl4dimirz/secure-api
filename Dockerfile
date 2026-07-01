# syntax=docker/dockerfile:1
#
# Multi-stage build: compile deps in a fat "builder", then copy only what's
# needed into a slim final image. Result = smaller, faster-to-ship, less to attack.

# ---- Stage 1: builder — install deps into an isolated prefix ----
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install runtime deps only (no pytest/httpx) into /install so we can copy just
# that layer forward. Copying requirements first keeps this layer cached until
# the deps actually change.
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Stage 2: runtime — minimal image, non-root, only the app + its deps ----
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # bind to all interfaces inside the container; the host maps the port
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app

# Bring over the installed packages from the builder (no build toolchain left behind).
COPY --from=builder /install /usr/local

# Copy only the application code. .dockerignore keeps out .venv, app.db, tests, .env.
COPY app ./app

# Security: run as an unprivileged user, never root. If the app is ever popped,
# the attacker lands as a nobody with no write access to the code.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Container-native health signal so orchestrators (compose, k8s, Fly, etc.) know
# when the API is actually ready, not just when the process started.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
